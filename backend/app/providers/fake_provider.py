from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, List, Union, Any
from backend.app.providers.provider_client import ProviderService, ProviderOrderStatus, ProviderError

class FakeProvider:
    def __init__(self, balance: float = 12450.80, currency: str = "USD"):
        self.balance = balance
        self.currency = currency
        self.orders: Dict[int, dict] = {}
        self._next_order_id = 10001
        self.fail_next_add = False
        self.add_call_count = 0

    def get_services(self) -> List[ProviderService]:
        return [
            ProviderService(101, "Instagram Followers High Quality", "Default", "Instagram Followers", 1.40, 100, 100000, "High quality Instagram followers", True),
            ProviderService(102, "TikTok Video Views Instant", "Default", "TikTok Views", 0.33, 1000, 1000000, "Instant TikTok video views", False),
            ProviderService(103, "Facebook Page Followers", "Default", "Facebook Followers", 1.70, 100, 100000, "Page followers for public pages", True),
            ProviderService(104, "X Post Likes Instant", "Default", "X Likes", 1.70, 50, 50000, "Likes for public posts", True),
            ProviderService(105, "Telegram Channel Members", "Default", "Telegram Members", 2.50, 100, 100000, "Members for public channels", True),
        ]

    def create_order(
        self,
        *,
        service_id: int,
        link: str,
        quantity: int,
        runs: Optional[int] = None,
        interval: Optional[int] = None,
    ) -> int:
        self.add_call_count += 1
        if self.fail_next_add:
            self.fail_next_add = False
            raise ProviderError("Provider submission failed: API error", action="add")
            
        order_id = self._next_order_id
        self._next_order_id += 1
        self.orders[order_id] = {
            "service_id": service_id,
            "link": link,
            "quantity": quantity,
            "charge_usd": (quantity / 1000.0) * 1.50,
            "status": "In Progress",
            "remains": int(quantity * 0.28),
            "start_count": 18430
        }
        return order_id

    def get_order_status(self, provider_order_id: int) -> ProviderOrderStatus:
        ord_data = self.orders.get(provider_order_id)
        if not ord_data:
            return ProviderOrderStatus(charge_usd=0.0, start_count=0, status="Completed", remains=0, currency=self.currency)
        return ProviderOrderStatus(
            charge_usd=ord_data["charge_usd"],
            start_count=ord_data["start_count"],
            status=ord_data["status"],
            remains=ord_data["remains"],
            currency=self.currency
        )

    def get_multiple_order_status(
        self, provider_order_ids: List[int]
    ) -> Dict[int, Union[ProviderOrderStatus, ProviderError]]:
        res = {}
        for oid in provider_order_ids:
            res[oid] = self.get_order_status(oid)
        return res

    def request_refill(self, provider_order_id: int) -> str:
        return f"RF-{provider_order_id}-01"

    def get_refill_status(self, refill_id: str) -> str:
        return "Completed"

    def cancel_order(self, provider_order_id: int) -> bool:
        if provider_order_id in self.orders:
            self.orders[provider_order_id]["status"] = "Canceled"
            return True
        return False

    def get_provider_balance(self) -> Tuple[float, str]:
        return self.balance, self.currency

    def test_provider_connection(self) -> Dict[str, Any]:
        return {
            "status": "Connected",
            "connected": True,
            "balance": self.balance,
            "currency": self.currency,
            "service_count": len(self.get_services()),
            "error": None
        }

    def check_provider_health(self) -> Dict[str, Any]:
        return {
            "provider": "SMM Africa",
            "status": "CONNECTED",
            "apiReachable": True,
            "authenticated": True,
            "lastChecked": datetime.now(timezone.utc).isoformat(),
            "servicesSync": "Healthy",
            "providerBalance": f"Available ({self.balance:.2f} {self.currency})",
            "reason": None
        }
