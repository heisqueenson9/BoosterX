"""
provider_client.py

ProviderAdapter for BoostX's fulfillment provider (boostcenter2.com/api/v2 —
a standard SMM-panel API: POST, JSON, action-based).

Design rules this file follows (per BoostX spec):
  - The provider API key NEVER leaves the backend.
  - Every provider call is wrapped, timed out, and retried safely.
  - Raw provider errors are never shown to customers — callers should
    catch ProviderError and translate it into a friendly message.
  - This adapter knows nothing about GHS pricing or the ledger. It only
    speaks the provider's native currency (USD) and native units.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

logger = logging.getLogger("boostx.provider")


class ProviderError(Exception):
    """Raised for any provider failure: network, timeout, or API-level error."""

    def __init__(self, message: str, *, action: str, raw: Any = None):
        super().__init__(message)
        self.action = action
        self.raw = raw


@dataclass(frozen=True)
class ProviderService:
    service_id: int
    name: str
    type: str
    category: str
    rate_usd_per_1000: float  # provider's cost, per 1000 units, in USD
    min_qty: int
    max_qty: int
    description: str
    refill_available: bool

    @classmethod
    def from_api(cls, row: dict) -> "ProviderService":
        return cls(
            service_id=int(row["service"]),
            name=row.get("name", ""),
            type=row.get("type", ""),
            category=row.get("category", ""),
            rate_usd_per_1000=float(row.get("rate", 0) or 0),
            min_qty=int(row.get("min", 0) or 0),
            max_qty=int(row.get("max", 0) or 0),
            description=row.get("desc", "") or "",
            refill_available=bool(row.get("refill", False)),
        )


@dataclass(frozen=True)
class ProviderOrderStatus:
    charge_usd: float
    start_count: int
    status: str
    remains: int
    currency: str


class ProviderAdapter:
    """
    Thin, defensive wrapper around the provider's /api/v2 endpoint.

    Usage:
        provider = ProviderAdapter(api_url=settings.PROVIDER_API_URL,
                                    api_key=settings.PROVIDER_API_KEY)
        services = provider.get_services()
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 1.5,
    ):
        if not api_url or not api_key:
            raise ValueError("ProviderAdapter requires api_url and api_key")
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff_seconds
        self._session = requests.Session()

    # ------------------------------------------------------------------ #
    # Low-level request handling
    # ------------------------------------------------------------------ #

    def _post(self, action: str, **params: Any) -> Any:
        """
        POST to the provider with the given action + params.
        Retries transient network/timeout errors for idempotent reads ONLY.
        NON-IDEMPOTENT actions ('add', 'cancel', 'refill') MUST NEVER BE RETRIED.
        """
        payload = {"key": self._api_key, "action": action, **params}
        
        # State-changing actions must never retry on network timeouts
        retries_allowed = 0 if action in ("add", "cancel", "refill") else self._max_retries

        last_exc: Optional[Exception] = None
        for attempt in range(retries_allowed + 1):
            try:
                resp = self._session.post(
                    self._api_url, data=payload, timeout=self._timeout
                )
                # Read the body before raise_for_status(): providers return
                # business errors (bad key, user_inactive, low balance) as 4xx
                # JSON, and those must surface as-is instead of being masked as
                # a generic "unreachable" transport failure.
                if resp.status_code < 500:
                    try:
                        body = resp.json()
                    except ValueError:
                        body = None
                    if isinstance(body, dict) and "error" in body:
                        raise ProviderError(
                            str(body["error"]), action=action, raw=body
                        )
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
                logger.warning(
                    "provider request failed (action=%s, attempt=%s/%s): %s",
                    action, attempt + 1, retries_allowed + 1, exc,
                )
                if attempt < retries_allowed:
                    time.sleep(self._retry_backoff * (attempt + 1))
                    continue
                raise ProviderError(
                    f"Provider unreachable for action '{action}'",
                    action=action,
                ) from exc

            # Provider-level error (business error, not transport error)
            if isinstance(data, dict) and "error" in data:
                raise ProviderError(
                    str(data["error"]), action=action, raw=data
                )
            return data

        raise ProviderError(
            f"Provider request failed for action '{action}'",
            action=action,
        ) from last_exc

    # ------------------------------------------------------------------ #
    # Public API — one method per provider action
    # ------------------------------------------------------------------ #

    def get_services(self) -> list[ProviderService]:
        """Fetch the full service catalog. Used by the sync worker, not per-request."""
        data = self._post("services")
        if not isinstance(data, list):
            raise ProviderError("Unexpected services response shape", action="services", raw=data)
        return [ProviderService.from_api(row) for row in data]

    def create_order(
        self,
        *,
        service_id: int,
        link: str,
        quantity: int,
        runs: Optional[int] = None,
        interval: Optional[int] = None,
    ) -> int:
        """Submit an order to the provider. Returns the provider_order_id."""
        params: dict[str, Any] = {
            "service": service_id,
            "link": link,
            "quantity": quantity,
        }
        if runs is not None:
            params["runs"] = runs
        if interval is not None:
            params["interval"] = interval

        data = self._post("add", **params)
        try:
            return int(data["order"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("No order id in provider response", action="add", raw=data) from exc

    def get_order_status(self, provider_order_id: int) -> ProviderOrderStatus:
        data = self._post("status", order=provider_order_id)
        return self._parse_status(data)

    def get_multiple_order_status(
        self, provider_order_ids: list[int]
    ) -> dict[int, ProviderOrderStatus | ProviderError]:
        """
        Bulk status check. Provider returns a per-order dict where individual
        orders may themselves contain an "error" key — we surface those as
        ProviderError instances rather than raising, since one bad ID
        shouldn't fail the whole batch.
        """
        ids_csv = ",".join(str(i) for i in provider_order_ids)
        data = self._post("status", orders=ids_csv)

        results: dict[int, ProviderOrderStatus | ProviderError] = {}
        if not isinstance(data, dict):
            raise ProviderError("Unexpected multi-status response shape", action="status", raw=data)

        for order_id_str, row in data.items():
            order_id = int(order_id_str)
            if isinstance(row, dict) and "error" in row:
                results[order_id] = ProviderError(str(row["error"]), action="status", raw=row)
            else:
                results[order_id] = self._parse_status(row)
        return results

    def request_refill(self, provider_order_id: int) -> str:
        """Returns the provider's refill id."""
        data = self._post("refill", order=provider_order_id)
        if "refill" not in data:
            raise ProviderError("No refill id in provider response", action="refill", raw=data)
        return str(data["refill"])

    def get_refill_status(self, refill_id: str) -> str:
        data = self._post("refill_status", refill=refill_id)
        if "status" not in data:
            raise ProviderError("No status in refill_status response", action="refill_status", raw=data)
        return str(data["status"])

    def cancel_order(self, provider_order_id: int) -> bool:
        data = self._post("cancel", order=provider_order_id)
        return bool(data.get("cancel"))

    def get_provider_balance(self) -> tuple[float, str]:
        """Returns (balance, currency) — BoostX's own balance held WITH the provider."""
        data = self._post("balance")
        try:
            return float(data["balance"]), str(data.get("currency", "USD"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Unexpected balance response", action="balance", raw=data) from exc

    def get_username(self) -> str:
        data = self._post("get-username")
        return str(data.get("username", ""))

    def test_provider_connection(self) -> dict[str, Any]:
        """
        Tests API connection, authentication, balance, and services fetch.
        Never exposes the API key in output or logs.
        """
        try:
            bal, curr = self.get_provider_balance()
            services = self.get_services()
            return {
                "status": "Connected",
                "connected": True,
                "balance": bal,
                "currency": curr,
                "service_count": len(services),
                "error": None
            }
        except Exception as exc:
            return {
                "status": "Connection Failed",
                "connected": False,
                "balance": 0.0,
                "currency": "USD",
                "service_count": 0,
                "error": str(exc)
            }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_status(data: dict) -> ProviderOrderStatus:
        try:
            return ProviderOrderStatus(
                charge_usd=float(data["charge"]),
                start_count=int(data["start_count"]),
                status=str(data["status"]),
                remains=int(data["remains"]),
                currency=str(data.get("currency", "USD")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Unexpected order-status response shape", action="status", raw=data) from exc
