from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Optional, Tuple
from flask import current_app
from backend.app.db import db
from backend.app.models import Order, OrderStatus, OrderEvent, Service, Platform, LedgerTransaction, LedgerStatus, LedgerType, User, Notification, Setting, Refund, Refill
from backend.app.pricing.pricing_service import PricingService, PricingSettings, PricingError
from backend.app.services.ledger_service import get_owner_balance
from backend.app.providers.factory import get_provider_client
from backend.app.providers.provider_client import ProviderError

logger = logging.getLogger("boostx.order_service")

class OrderExecutionError(Exception):
    def __init__(self, message: str, code: int = 400, details: dict = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

def get_pricing_engine() -> PricingService:
    rate_setting = Setting.query.filter_by(key="usd_to_ghs_rate").first()
    markup_setting = Setting.query.filter_by(key="flat_markup_ghs").first()

    usd_rate = Decimal(rate_setting.value) if rate_setting else current_app.config["DEFAULT_USD_TO_GHS"]
    flat_markup = Decimal(markup_setting.value) if markup_setting else current_app.config["DEFAULT_FLAT_MARKUP_GHS"]

    settings = PricingSettings(usd_to_ghs_rate=usd_rate, flat_markup_ghs=flat_markup)
    return PricingService(settings)

def create_and_submit_order(*, user_id: int, service_id: int, target: str, quantity: int, idempotency_key: Optional[str] = None) -> Order:
    """
    Implements the 7-step order execution algorithm per spec Section 11 & Prompt Section 7.
    """
    # Check Idempotency Key first
    if idempotency_key:
        existing_order = Order.query.filter_by(user_id=user_id, idempotency_key=idempotency_key).first()
        if existing_order:
            logger.info(f"Idempotent order request matched existing order {existing_order.public_order_id}")
            return existing_order

    # Step 1: Validate Service & Target
    service = db.session.get(Service, service_id)
    if not service or not service.enabled:
        raise OrderExecutionError("Service is unavailable or disabled.")

    plat = Platform.query.filter_by(name=service.platform, active=True).first()
    if not plat:
        raise OrderExecutionError(f"Platform '{service.platform}' is currently disabled.")

    if not target or len(target.strip()) < 3:
        raise OrderExecutionError("Please provide a valid target URL or handle.")

    if quantity < service.min_qty or quantity > service.max_qty:
        raise OrderExecutionError(f"Quantity must be between {service.min_qty} and {service.max_qty}.")

    # Step 2: Calculate Price Server-Side
    pricing = get_pricing_engine()
    try:
        quote = pricing.quote_service(
            service_id=service.id,
            provider_rate_usd_per_1000=Decimal(str(service.rate_usd_per_1000)),
            quantity=quantity,
            min_qty=service.min_qty,
            max_qty=service.max_qty
        )
    except PricingError as exc:
        raise OrderExecutionError(str(exc))

    charge_ghs = quote.customer_price_ghs

    # Step 3: TX1 - Lock Owner, Reserve Balance, Create Pending Order
    with db.session.begin_nested():
        db.session.query(User).filter_by(id=user_id).with_for_update().first()

        available_balance = get_owner_balance(user_id)
        if available_balance < charge_ghs:
            raise OrderExecutionError(
                "Insufficient wallet balance to place this order.",
                code=402,
                details={"available": f"{available_balance:.2f}", "required": f"{charge_ghs:.2f}"}
            )

        balance_before = available_balance
        balance_after = balance_before - charge_ghs

        order = Order(
            public_order_id=Order.new_public_id(),
            user_id=user_id,
            idempotency_key=idempotency_key,
            platform=service.platform,
            service_id=service.id,
            service_name=service.name,
            target=target.strip(),
            quantity=quantity,
            charge_ghs=charge_ghs,
            status=OrderStatus.PENDING,
            remains=quantity,
            start_count=0
        )
        db.session.add(order)
        db.session.flush()

        # Reserve order debit
        ledger_debit = LedgerTransaction(
            user_id=user_id,
            type=LedgerType.ORDER_DEBIT,
            amount_ghs=charge_ghs,
            status=LedgerStatus.RESERVED,
            reference=order.public_order_id,
            description=f"Order {order.public_order_id} ({service.platform} {service.name})",
            balance_before=balance_before,
            balance_after=balance_after
        )
        db.session.add(ledger_debit)

        # Record Events
        db.session.add(OrderEvent(order_id=order.id, event_type="ORDER_CREATED", description="Order created in Pending status"))
        db.session.add(OrderEvent(order_id=order.id, event_type="PAYMENT_RESERVED", description=f"Reserved GHS {charge_ghs:.2f} balance"))

    db.session.commit()

    # Step 4: Call Provider `add` OUTSIDE DB Lock
    provider = get_provider_client()
    try:
        provider_order_id = provider.create_order(
            service_id=service.provider_service_id,
            link=target.strip(),
            quantity=quantity
        )
    except ProviderError as exc:
        logger.warning(f"Provider submission error for order {order.public_order_id}: {exc}")
        # Check if error is ambiguous timeout/5xx vs definite refusal
        is_ambiguous = "unreachable" in str(exc).lower() or "timeout" in str(exc).lower()
        if is_ambiguous:
            _handle_ambiguous_provider_failure(order.id)
            return order
        else:
            _handle_definite_provider_failure(order.id, str(exc))
            raise OrderExecutionError(f"Fulfillment provider declined order: {exc}")
    except Exception as exc:
        logger.error(f"Unexpected provider error for order {order.public_order_id}: {exc}")
        _handle_ambiguous_provider_failure(order.id)
        return order

    # Step 5: Success — Post Ledger, Update Status to Processing
    with db.session.begin_nested():
        ord_obj = db.session.get(Order, order.id)
        ord_obj.provider_order_id = provider_order_id
        ord_obj.status = OrderStatus.PROCESSING
        ord_obj.provider_status_raw = "In Progress"

        ledger_row = LedgerTransaction.query.filter_by(reference=ord_obj.public_order_id, type=LedgerType.ORDER_DEBIT).first()
        if ledger_row:
            ledger_row.status = LedgerStatus.POSTED

        db.session.add(OrderEvent(order_id=ord_obj.id, event_type="PROVIDER_SUBMITTED", description=f"Submitted to provider (ID: {provider_order_id})"))
        db.session.add(OrderEvent(order_id=ord_obj.id, event_type="PROVIDER_ACCEPTED", description="Provider accepted order and marked In Progress"))

        db.session.add(Notification(
            user_id=ord_obj.user_id,
            title="Order Processing",
            message=f"Order {ord_obj.public_order_id} for {ord_obj.platform} {ord_obj.service_name} is now processing."
        ))

    db.session.commit()
    return order


def _handle_definite_provider_failure(order_id: int, reason: str):
    with db.session.begin_nested():
        ord_obj = db.session.get(Order, order_id)
        ord_obj.status = OrderStatus.FAILED
        ord_obj.provider_status_raw = "Failed"

        # Release reserved debit -> restores balance fully
        ledger_row = LedgerTransaction.query.filter_by(reference=ord_obj.public_order_id, type=LedgerType.ORDER_DEBIT).first()
        if ledger_row:
            ledger_row.status = LedgerStatus.RELEASED

        db.session.add(OrderEvent(order_id=ord_obj.id, event_type="PROVIDER_ORDER_FAILED", description=f"Provider rejected order: {reason}. Balance restored."))

    db.session.commit()


def _handle_ambiguous_provider_failure(order_id: int):
    """
    Ambiguous failure (timeout/5xx after send): keep funds reserved, set needs_attention=True.
    NEVER release or retry add automatically.
    """
    with db.session.begin_nested():
        ord_obj = db.session.get(Order, order_id)
        ord_obj.needs_attention = True
        ord_obj.provider_status_raw = "Timeout / Ambiguous"

        db.session.add(OrderEvent(order_id=ord_obj.id, event_type="PROVIDER_TIMEOUT_AMBIGUOUS", description="Provider request timed out. Order flagged for admin attention. Funds reserved."))

    db.session.commit()


def refund_order(order: Order, refund_type: str, reason: str) -> Decimal:
    """
    Calculates and processes refunds:
      - Failed: 100% refund
      - Cancelled before start: 100% refund
      - Partial: charge_ghs * remains / quantity (half-up rounding)
    Inserts posted refund_credit ledger row.
    """
    if order.status in (OrderStatus.REFUNDED, OrderStatus.FAILED):
        # Prevent double refund
        return Decimal("0.00")

    charge = Decimal(str(order.charge_ghs))
    remains = Decimal(str(order.remains if order.remains is not None else order.quantity))
    total_qty = Decimal(str(order.quantity if order.quantity > 0 else 1))

    if refund_type in ("Failed", "Canceled_Full"):
        refund_amount = charge
    elif refund_type == "Partial":
        refund_amount = (charge * remains / total_qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        refund_amount = min(refund_amount, charge)  # Never above original charge
    else:
        refund_amount = Decimal("0.00")

    if refund_amount <= 0:
        return Decimal("0.00")

    with db.session.begin_nested():
        user_id = order.user_id
        db.session.query(User).filter_by(id=user_id).with_for_update().first()

        bal_before = get_owner_balance(user_id)
        bal_after = bal_before + refund_amount

        ref_record = Refund(
            order_id=order.id,
            amount_ghs=refund_amount,
            reason=reason
        )
        db.session.add(ref_record)

        ledger_refund = LedgerTransaction(
            user_id=user_id,
            type=LedgerType.REFUND_CREDIT,
            amount_ghs=refund_amount,
            status=LedgerStatus.POSTED,
            reference=order.public_order_id,
            description=f"Refund for order {order.public_order_id} ({reason})",
            balance_before=bal_before,
            balance_after=bal_after
        )
        db.session.add(ledger_refund)

        db.session.add(OrderEvent(order_id=order.id, event_type="ORDER_REFUNDED", description=f"Refunded GHS {refund_amount:.2f} ({reason})"))

    db.session.commit()
    return refund_amount
