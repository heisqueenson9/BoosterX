from datetime import datetime, timezone, timedelta
from decimal import Decimal
from flask import Blueprint, jsonify, request, current_app
from backend.app.db import db
from backend.app.models import (
    User, UserRole, UserStatus, Payment, PaymentStatus, PaymentVerification,
    Order, OrderStatus, OrderEvent, LedgerTransaction, LedgerStatus, LedgerType,
    Service, Platform, Setting, FraudFlag, AdminAction
)
from backend.app.middleware import admin_required
from backend.app.auth.session import get_current_user
from backend.app.services.ledger_service import get_owner_balance
from backend.app.payments.decision_engine import process_payment_verification
from backend.app.orders.order_service import refund_order
from backend.app.providers.factory import get_provider_client
from backend.app.providers.provider_client import ProviderError
from backend.app.workers.sync_services import sync_services_worker

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@admin_bp.before_request
@admin_required
def admin_security_guard():
    """
    Enforces admin role check on all /api/admin/* endpoints.
    Returns generic 404 for non-admins to hide route existence.
    """
    pass


def _log_admin_action(action: str, target_type: str, target_id: str, old_val: str = None, new_val: str = None):
    admin_user = get_current_user()
    action_rec = AdminAction(
        admin_id=admin_user.id if admin_user else 1,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        old_value=str(old_val) if old_val is not None else None,
        new_value=str(new_val) if new_val is not None else None
    )
    db.session.add(action_rec)


@admin_bp.get("/overview")
def get_dashboard_overview():
    now_utc = datetime.now(timezone.utc)
    day_ago = now_utc - timedelta(hours=24)

    # 24h Revenue (posted order debits in last 24h)
    rev_query = db.session.query(db.func.sum(LedgerTransaction.amount_ghs)).filter(
        LedgerTransaction.type == LedgerType.ORDER_DEBIT,
        LedgerTransaction.status == LedgerStatus.POSTED,
        LedgerTransaction.created_at >= day_ago
    )
    revenue_24h = Decimal(str(rev_query.scalar() or 0))

    active_orders = Order.query.filter(Order.status.in_([OrderStatus.PENDING, OrderStatus.PROCESSING])).count()
    pending_reviews = Payment.query.filter(Payment.status.in_([PaymentStatus.VERIFYING, PaymentStatus.REVIEW_REQUIRED])).count()
    total_users = User.query.filter_by(role=UserRole.CUSTOMER).count()
    failed_orders = Order.query.filter_by(status=OrderStatus.FAILED).count()
    total_orders = Order.query.count()

    active_services_count = Service.query.filter_by(enabled=True).count()

    # Most recent service sync timestamp
    latest_sync_srv = Service.query.filter(Service.last_synced_at.isnot(None)).order_by(Service.last_synced_at.desc()).first()
    last_sync_timestamp = latest_sync_srv.last_synced_at.isoformat() if latest_sync_srv and latest_sync_srv.last_synced_at else "Never"

    # Order count breakdown by status
    status_counts_rows = db.session.query(Order.status, db.func.count(Order.id)).group_by(Order.status).all()
    orders_by_status = {st: count for st, count in status_counts_rows}

    # Provider status and balance
    try:
        provider = get_provider_client()
        conn_test = provider.test_provider_connection()
        provider_conn_status = conn_test.get("status", "Connected") if conn_test.get("connected") else "Connection Failed"
        provider_bal_str = f"{conn_test.get('balance', 0.0):.2f} {conn_test.get('currency', 'USD')}"
    except Exception:
        provider_conn_status = "Connection Failed"
        provider_bal_str = "Unavailable"

    return jsonify({
        "revenue_24h_ghs": f"{revenue_24h:.2f}",
        "active_orders": active_orders,
        "pending_payment_reviews": pending_reviews,
        "total_users": total_users,
        "failed_orders": failed_orders,
        "total_orders": total_orders,
        "provider_balance": provider_bal_str,
        "provider_connection_status": provider_conn_status,
        "active_services_count": active_services_count,
        "last_sync_timestamp": last_sync_timestamp,
        "orders_by_status": orders_by_status
    }), 200


@admin_bp.route("/provider/test", methods=["GET", "POST"])
def test_provider_connection_admin():
    provider = get_provider_client()
    res = provider.test_provider_connection()
    return jsonify(res), 200


@admin_bp.get("/payments")
def list_payments_admin():
    status_filter = request.args.get("status")
    search_q = request.args.get("search")

    query = Payment.query

    if status_filter:
        query = query.filter(Payment.status == status_filter)

    if search_q:
        q_like = f"%{search_q.strip()}%"
        query = query.filter(
            (Payment.payment_id.ilike(q_like)) |
            (Payment.transaction_reference.ilike(q_like))
        )

    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    except ValueError:
        page = 1
        per_page = 20

    total = query.count()
    payments = query.order_by(Payment.id.desc()).offset((page - 1) * per_page).limit(per_page).all()

    items = []
    for p in payments:
        pv = PaymentVerification.query.filter_by(payment_id=p.id).order_by(PaymentVerification.id.desc()).first()
        raw_ai = pv.raw_ai_json if pv else {}
        items.append({
            "id": p.id,
            "payment_id": p.payment_id,
            "network": p.network,
            "amount_ghs": f"{p.amount_ghs:.2f}",
            "status": p.status,
            "reference": p.transaction_reference or raw_ai.get("reference"),
            "detected_amount_ghs": f"{raw_ai.get('amount'):.2f}" if raw_ai and raw_ai.get("amount") is not None else None,
            "screenshot_filename": p.screenshot_filename,
            "attempt_count": p.attempt_count,
            "rejection_reason": p.rejection_reason,
            "created_at": p.created_at.isoformat() if p.created_at else None
        })

    return jsonify({
        "payments": items,
        "total": total,
        "page": page,
        "per_page": per_page
    }), 200


@admin_bp.post("/payments/<payment_id>/verify")
def manual_verify_payment(payment_id: str):
    payment = Payment.query.filter_by(payment_id=payment_id).first()
    if not payment:
        return jsonify({"error": "Payment not found"}), 404

    data = request.get_json(silent=True) or {}
    ref_input = data.get("reference") or payment.transaction_reference or f"MANUAL-{payment.payment_id}"

    if payment.status == PaymentStatus.VERIFIED:
        return jsonify({"error": "Payment is already verified"}), 400

    # Double-spend check on reference
    existing_tx = LedgerTransaction.query.filter_by(reference=ref_input, status=LedgerStatus.POSTED).first()
    if existing_tx and existing_tx.payment_id != payment.id:
        return jsonify({"error": f"Transaction reference '{ref_input}' already used in ledger"}), 400

    if not payment.user_id:
        return jsonify({"error": "This payment has no owning account and cannot be credited"}), 400

    bal_before = get_owner_balance(payment.user_id)
    bal_after = bal_before + Decimal(str(payment.amount_ghs))

    old_status = payment.status
    payment.status = PaymentStatus.VERIFIED
    payment.transaction_reference = ref_input

    # Insert posted credit
    tx = LedgerTransaction(
        user_id=payment.user_id,
        type=LedgerType.PAYMENT_CREDIT,
        amount_ghs=payment.amount_ghs,
        status=LedgerStatus.POSTED,
        reference=ref_input,
        description=f"Manual Admin verification for {payment.payment_id} ({payment.network})",
        balance_before=bal_before,
        balance_after=bal_after
    )
    db.session.add(tx)

    _log_admin_action("VERIFY_PAYMENT", "payment", payment.payment_id, old_val=old_status, new_val=PaymentStatus.VERIFIED)
    db.session.commit()

    return jsonify({"message": f"Payment {payment.payment_id} verified successfully. GHS {payment.amount_ghs:.2f} credited."}), 200


@admin_bp.post("/payments/<payment_id>/reject")
def manual_reject_payment(payment_id: str):
    payment = Payment.query.filter_by(payment_id=payment_id).first()
    if not payment:
        return jsonify({"error": "Payment not found"}), 404

    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "Rejected by administrator review.")

    old_status = payment.status
    payment.status = PaymentStatus.REJECTED
    payment.rejection_reason = reason

    _log_admin_action("REJECT_PAYMENT", "payment", payment.payment_id, old_val=old_status, new_val=PaymentStatus.REJECTED)
    db.session.commit()

    return jsonify({"message": f"Payment {payment.payment_id} marked as rejected."}), 200


@admin_bp.get("/orders")
def list_orders_admin():
    status_filter = request.args.get("status")
    platform_filter = request.args.get("platform")
    needs_attn = request.args.get("needs_attention")
    search_q = request.args.get("search")

    query = Order.query

    if status_filter:
        query = query.filter(Order.status == status_filter)

    if platform_filter:
        query = query.filter(Order.platform == platform_filter)

    if needs_attn is not None:
        val = str(needs_attn).lower() in ("true", "1")
        query = query.filter(Order.needs_attention == val)

    if search_q:
        q_like = f"%{search_q.strip()}%"
        query = query.filter(
            (Order.public_order_id.ilike(q_like)) |
            (Order.target.ilike(q_like)) |
            (Order.service_name.ilike(q_like))
        )

    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    except ValueError:
        page = 1
        per_page = 20

    total = query.count()
    orders = query.order_by(Order.id.desc()).offset((page - 1) * per_page).limit(per_page).all()

    items = []
    for o in orders:
        items.append({
            "id": o.id,
            "public_order_id": o.public_order_id,
            "platform": o.platform,
            "service_id": o.service_id,
            "service_name": o.service_name,
            "target": o.target,
            "quantity": o.quantity,
            "charge_ghs": f"{o.charge_ghs:.2f}",
            "status": o.status,
            "provider_order_id": o.provider_order_id,
            "provider_status_raw": o.provider_status_raw,
            "needs_attention": o.needs_attention,
            "start_count": o.start_count,
            "remains": o.remains,
            "created_at": o.created_at.isoformat() if o.created_at else None
        })

    return jsonify({
        "orders": items,
        "total": total,
        "page": page,
        "per_page": per_page
    }), 200


@admin_bp.post("/orders/<public_id>/action")
def admin_order_action(public_id: str):
    order = Order.query.filter_by(public_order_id=public_id).first()
    if not order:
        return jsonify({"error": "Order not found"}), 404

    data = request.get_json(silent=True) or {}
    action_type = data.get("action")

    if action_type == "clear-attention":
        order.needs_attention = False
        _log_admin_action("CLEAR_ORDER_ATTENTION", "order", order.public_order_id)
        db.session.commit()
        return jsonify({"message": "Cleared needs_attention flag"}), 200

    elif action_type == "mark-submitted":
        prov_id = data.get("provider_order_id") or order.provider_order_id
        if prov_id:
            try:
                order.provider_order_id = int(prov_id)
            except ValueError:
                pass
        order.status = OrderStatus.PROCESSING
        order.needs_attention = False
        ledger_row = LedgerTransaction.query.filter_by(reference=order.public_order_id, type=LedgerType.ORDER_DEBIT).first()
        if ledger_row:
            ledger_row.status = LedgerStatus.POSTED
        _log_admin_action("MARK_ORDER_SUBMITTED", "order", order.public_order_id, new_val=str(prov_id))
        db.session.commit()
        return jsonify({"message": "Order marked as Processing/Submitted"}), 200

    elif action_type == "cancel":
        refund_type = data.get("refund_type", "Canceled_Full")
        reason = data.get("reason", "Cancelled by administrator")
        order.status = OrderStatus.CANCELLED
        order.needs_attention = False
        ref_amt = refund_order(order, refund_type, reason)
        _log_admin_action("CANCEL_ORDER", "order", order.public_order_id, new_val=f"Refund GHS {ref_amt:.2f}")
        db.session.commit()
        return jsonify({"message": f"Order cancelled. Refunded GHS {ref_amt:.2f}"}), 200

    elif action_type == "refill":
        if not order.provider_order_id:
            return jsonify({"error": "Order has no provider_order_id"}), 400
        provider = get_provider_client()
        try:
            ref_id = provider.refill_order(order.provider_order_id)
        except ProviderError as exc:
            return jsonify({"error": f"Provider refill failed: {exc}"}), 400
        _log_admin_action("REFILL_ORDER", "order", order.public_order_id, new_val=str(ref_id))
        return jsonify({"message": "Refill requested", "refill_id": ref_id}), 200

    elif action_type == "release":
        ledger_row = LedgerTransaction.query.filter_by(reference=order.public_order_id, type=LedgerType.ORDER_DEBIT).first()
        if ledger_row and ledger_row.status == LedgerStatus.RESERVED:
            ledger_row.status = LedgerStatus.RELEASED
            order.status = OrderStatus.FAILED
            order.needs_attention = False
            _log_admin_action("RELEASE_FUNDS", "order", order.public_order_id)
            db.session.commit()
            return jsonify({"message": "Released reserved funds and marked order as Failed"}), 200

    return jsonify({"error": f"Unknown admin action '{action_type}'"}), 400


@admin_bp.get("/services")
def list_services_admin():
    services = Service.query.order_by(Service.platform.asc(), Service.id.asc()).all()
    return jsonify({
        "services": [{
            "id": s.id,
            "provider_service_id": s.provider_service_id,
            "platform": s.platform,
            "category": s.category,
            "name": s.name,
            "type": s.type,
            "rate_usd_per_1000": f"{s.rate_usd_per_1000:.4f}",
            "min_qty": s.min_qty,
            "max_qty": s.max_qty,
            "enabled": s.enabled,
            "refill_available": s.refill_available,
            "description": s.description
        } for s in services]
    }), 200


@admin_bp.patch("/services/<int:service_id>")
def update_service_admin(service_id: int):
    service = db.session.get(Service, service_id)
    if not service:
        return jsonify({"error": "Service not found"}), 404

    data = request.get_json(silent=True) or {}
    old_enabled = service.enabled

    if "enabled" in data:
        service.enabled = bool(data["enabled"])
    if "min_qty" in data:
        service.min_qty = int(data["min_qty"])
    if "max_qty" in data:
        service.max_qty = int(data["max_qty"])
    if "rate_usd_per_1000" in data:
        service.rate_usd_per_1000 = Decimal(str(data["rate_usd_per_1000"]))

    _log_admin_action("UPDATE_SERVICE", "service", service.id, old_val=f"enabled={old_enabled}", new_val=f"enabled={service.enabled}")
    db.session.commit()
    return jsonify({"message": "Service updated successfully"}), 200


@admin_bp.post("/services/sync")
def sync_services_admin():
    res = sync_services_worker(current_app)
    _log_admin_action("SYNC_SERVICES", "system", "catalog", new_val=str(res))
    return jsonify(res), 200


@admin_bp.get("/platforms")
def list_platforms_admin():
    platforms = Platform.query.all()
    return jsonify({
        "platforms": [{"id": p.id, "name": p.name, "active": p.active} for p in platforms]
    }), 200


@admin_bp.patch("/platforms/<int:platform_id>")
def update_platform_admin(platform_id: int):
    plat = db.session.get(Platform, platform_id)
    if not plat:
        return jsonify({"error": "Platform not found"}), 404

    data = request.get_json(silent=True) or {}
    old_active = plat.active
    if "active" in data:
        plat.active = bool(data["active"])

    _log_admin_action("UPDATE_PLATFORM", "platform", plat.name, old_val=f"active={old_active}", new_val=f"active={plat.active}")
    db.session.commit()
    return jsonify({"message": f"Platform {plat.name} updated successfully"}), 200


@admin_bp.get("/users")
def list_users_admin():
    search_q = request.args.get("search")
    status_q = request.args.get("status")

    query = User.query

    if status_q:
        query = query.filter(User.status == status_q)

    if search_q:
        q_like = f"%{search_q.strip()}%"
        query = query.filter(
            (User.full_name.ilike(q_like)) |
            (User.email.ilike(q_like)) |
            (User.phone.ilike(q_like)) |
            (User.public_user_id.ilike(q_like))
        )

    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    except ValueError:
        page = 1
        per_page = 20

    total = query.count()
    users = query.order_by(User.id.desc()).offset((page - 1) * per_page).limit(per_page).all()

    items = []
    for u in users:
        bal = get_owner_balance(u.id)
        items.append({
            "id": u.id,
            "public_user_id": u.public_user_id,
            "full_name": u.full_name,
            "email": u.email,
            "username": u.full_name or u.email or u.public_user_id,
            "phone": u.phone,
            "role": u.role,
            "status": u.status,
            "balance_ghs": f"{bal:.2f}",
            "created_at": u.created_at.isoformat() if u.created_at else None
        })

    return jsonify({
        "users": items,
        "total": total,
        "page": page,
        "per_page": per_page
    }), 200


@admin_bp.patch("/users/<int:user_id>")
def update_user_admin(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.role == UserRole.ADMIN:
        return jsonify({"error": "Administrator accounts are managed through server configuration"}), 403

    data = request.get_json(silent=True) or {}
    old_status = user.status

    if "status" in data:
        new_st = data["status"]
        if new_st in (UserStatus.ACTIVE, UserStatus.SUSPENDED):
            user.status = new_st

    _log_admin_action("UPDATE_USER", "user", user.id, old_val=f"status={old_status}", new_val=f"status={user.status}")
    db.session.commit()
    user_display = user.full_name or user.email or user.public_user_id
    return jsonify({"message": f"User {user_display} status updated to {user.status}"}), 200


@admin_bp.get("/transactions")
def list_all_transactions_admin():
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    except ValueError:
        page = 1
        per_page = 20

    query = LedgerTransaction.query
    total = query.count()
    txs = query.order_by(LedgerTransaction.id.desc()).offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        "transactions": [{
            "id": t.id,
            "user_id": t.user_id,
            "type": t.type,
            "amount_ghs": f"{t.amount_ghs:.2f}",
            "status": t.status,
            "reference": t.reference,
            "description": t.description,
            "balance_before": f"{t.balance_before:.2f}",
            "balance_after": f"{t.balance_after:.2f}",
            "created_at": t.created_at.isoformat() if t.created_at else None
        } for t in txs],
        "total": total,
        "page": page,
        "per_page": per_page
    }), 200


@admin_bp.get("/pricing")
def get_pricing_settings():
    rate_s = Setting.query.filter_by(key="usd_to_ghs_rate").first()
    markup_s = Setting.query.filter_by(key="flat_markup_ghs").first()

    rate_val = Decimal(rate_s.value) if rate_s else current_app.config["DEFAULT_USD_TO_GHS"]
    markup_val = Decimal(markup_s.value) if markup_s else current_app.config["DEFAULT_FLAT_MARKUP_GHS"]

    return jsonify({
        "usd_to_ghs_rate": f"{rate_val:.2f}",
        "flat_markup_ghs": f"{markup_val:.2f}"
    }), 200


@admin_bp.post("/pricing")
def update_pricing_settings():
    data = request.get_json(silent=True) or {}
    rate_raw = data.get("usd_to_ghs_rate")
    markup_raw = data.get("flat_markup_ghs")

    if rate_raw is not None:
        try:
            r_val = Decimal(str(rate_raw))
            setting = Setting.query.filter_by(key="usd_to_ghs_rate").first()
            if not setting:
                setting = Setting(key="usd_to_ghs_rate", value=str(r_val))
                db.session.add(setting)
            else:
                setting.value = str(r_val)
            _log_admin_action("UPDATE_PRICING_RATE", "setting", "usd_to_ghs_rate", new_val=str(r_val))
        except Exception:
            return jsonify({"error": "Invalid USD to GHS exchange rate"}), 400

    if markup_raw is not None:
        try:
            m_val = Decimal(str(markup_raw))
            setting = Setting.query.filter_by(key="flat_markup_ghs").first()
            if not setting:
                setting = Setting(key="flat_markup_ghs", value=str(m_val))
                db.session.add(setting)
            else:
                setting.value = str(m_val)
            _log_admin_action("UPDATE_PRICING_MARKUP", "setting", "flat_markup_ghs", new_val=str(m_val))
        except Exception:
            return jsonify({"error": "Invalid flat markup GHS"}), 400

    db.session.commit()
    return jsonify({"message": "Pricing settings updated successfully"}), 200


@admin_bp.get("/provider/balance")
def get_provider_balance_admin():
    provider = get_provider_client()
    try:
        bal, curr = provider.get_provider_balance()
        return jsonify({"balance": f"{bal:.2f}", "currency": curr}), 200
    except ProviderError as exc:
        return jsonify({"error": f"Failed to fetch provider balance: {exc}"}), 500


@admin_bp.get("/system/health")
def get_system_health():
    db_ok = True
    db_err = None
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_err = str(exc)

    prov_ok = True
    prov_err = None
    try:
        get_provider_client().get_provider_balance()
    except Exception as exc:
        prov_ok = False
        prov_err = str(exc)

    status_str = "HEALTHY" if (db_ok and prov_ok) else "DEGRADED"

    return jsonify({
        "status": status_str,
        "database": {"status": "ok" if db_ok else "error", "message": db_err},
        "provider": {"status": "ok" if prov_ok else "error", "message": prov_err},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200


@admin_bp.get("/audit-logs")
def list_audit_logs():
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    except ValueError:
        page = 1
        per_page = 20

    query = AdminAction.query
    total = query.count()
    actions = query.order_by(AdminAction.id.desc()).offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        "audit_logs": [{
            "id": a.id,
            "admin_id": a.admin_id,
            "action": a.action,
            "target_type": a.target_type,
            "target_id": a.target_id,
            "old_value": a.old_value,
            "new_value": a.new_value,
            "created_at": a.created_at.isoformat() if a.created_at else None
        } for a in actions],
        "total": total,
        "page": page,
        "per_page": per_page
    }), 200
