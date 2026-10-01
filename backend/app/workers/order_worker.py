from datetime import datetime, timezone, timedelta
import logging
from typing import Optional, List, Dict
from backend.app.db import db
from backend.app.models import Order, OrderStatus, OrderEvent, Payment, PaymentStatus, Notification
from backend.app.orders.order_service import refund_order
from backend.app.providers.factory import get_provider_client
from backend.app.providers.provider_client import ProviderError

logger = logging.getLogger("boostx.order_worker")

def check_pending_orders(app=None) -> dict:
    """
    Background worker: checks status of active processing/pending orders with provider.
    Updates progress/status and handles partial or full refunds.
    """
    if app:
        with app.app_context():
            return _do_check_pending_orders()
    else:
        return _do_check_pending_orders()


def _do_check_pending_orders() -> dict:
    active_orders = Order.query.filter(
        Order.status.in_([OrderStatus.PENDING, OrderStatus.PROCESSING]),
        Order.provider_order_id != None,
        Order.needs_attention == False
    ).all()

    if not active_orders:
        return {"checked": 0, "updated": 0}

    provider = get_provider_client()
    provider_ids = [o.provider_order_id for o in active_orders]

    try:
        statuses_map = provider.get_multiple_order_status(provider_ids)
    except Exception as exc:
        logger.warning(f"Batch status fetch failed, falling back to individual calls: {exc}")
        statuses_map = {}
        for o in active_orders:
            try:
                st = provider.get_order_status(o.provider_order_id)
                statuses_map[o.provider_order_id] = st
            except Exception as e:
                logger.error(f"Failed to fetch status for provider order {o.provider_order_id}: {e}")

    updated_count = 0
    now_utc = datetime.now(timezone.utc)

    for order in active_orders:
        st_info = statuses_map.get(order.provider_order_id)
        if not st_info:
            continue

        raw_status = (st_info.status or "").strip()
        order.provider_status_raw = raw_status
        if st_info.start_count is not None:
            order.start_count = st_info.start_count
        if st_info.remains is not None:
            order.remains = st_info.remains

        norm_status = raw_status.lower()

        if norm_status in ("completed", "finished"):
            if order.status != OrderStatus.COMPLETED:
                order.status = OrderStatus.COMPLETED
                order.remains = 0
                order.completed_at = now_utc
                db.session.add(OrderEvent(order_id=order.id, event_type="ORDER_COMPLETED", description="Provider marked order as Completed"))
                db.session.add(Notification(
                    user_id=order.user_id,
                    title="Order Completed",
                    message=f"Order {order.public_order_id} for {order.platform} {order.service_name} has completed."
                ))
                updated_count += 1

        elif norm_status == "partial":
            if order.status != OrderStatus.PARTIAL:
                order.status = OrderStatus.PARTIAL
                refund_amt = refund_order(order, "Partial", "Partial delivery refund from provider")
                db.session.add(OrderEvent(order_id=order.id, event_type="ORDER_PARTIAL", description=f"Provider marked Partial. Refunded GHS {refund_amt:.2f}"))
                db.session.add(Notification(
                    user_id=order.user_id,
                    title="Order Partial Refund",
                    message=f"Order {order.public_order_id} was partially completed. GHS {refund_amt:.2f} refunded to wallet."
                ))
                updated_count += 1

        elif norm_status in ("canceled", "cancelled"):
            if order.status != OrderStatus.CANCELLED:
                order.status = OrderStatus.CANCELLED
                refund_amt = refund_order(order, "Canceled_Full", "Order cancelled by provider")
                db.session.add(OrderEvent(order_id=order.id, event_type="ORDER_CANCELLED", description=f"Provider cancelled order. Refunded GHS {refund_amt:.2f}"))
                db.session.add(Notification(
                    user_id=order.user_id,
                    title="Order Cancelled",
                    message=f"Order {order.public_order_id} was cancelled by provider. Full refund issued."
                ))
                updated_count += 1

        elif norm_status == "failed":
            if order.status != OrderStatus.FAILED:
                order.status = OrderStatus.FAILED
                refund_amt = refund_order(order, "Failed", "Order failed at provider")
                db.session.add(OrderEvent(order_id=order.id, event_type="ORDER_FAILED", description=f"Provider marked Failed. Refunded GHS {refund_amt:.2f}"))
                db.session.add(Notification(
                    user_id=order.user_id,
                    title="Order Failed",
                    message=f"Order {order.public_order_id} failed at provider. Full refund issued."
                ))
                updated_count += 1

    db.session.commit()
    return {"checked": len(active_orders), "updated": updated_count}


def expire_payments(app=None) -> dict:
    """
    Background worker: expires payments past their 30-minute window.
    """
    if app:
        with app.app_context():
            return _do_expire_payments()
    else:
        return _do_expire_payments()


def _do_expire_payments() -> dict:
    now_utc = datetime.now(timezone.utc)
    expired_payments = Payment.query.filter(
        Payment.status.in_([PaymentStatus.IDLE, PaymentStatus.VERIFYING]),
        Payment.expires_at < now_utc
    ).all()

    count = 0
    for p in expired_payments:
        p.status = PaymentStatus.EXPIRED
        count += 1

    db.session.commit()
    logger.info(f"Expired {count} unverified payments past expiration window.")
    return {"expired": count}
