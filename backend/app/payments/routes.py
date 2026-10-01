from datetime import datetime, timezone
from decimal import Decimal
from flask import Blueprint, jsonify, request, current_app, make_response
from backend.app.db import db
from backend.app.models import Payment, PaymentStatus, PaymentVerification, Setting
from backend.app.auth.session import require_user
from backend.app.payments.upload import validate_and_save_screenshot, UploadError
from backend.app.ai.payment_ai import PaymentAI
from backend.app.payments.decision_engine import process_payment_verification

from backend.app.middleware import limiter

payments_bp = Blueprint("payments", __name__, url_prefix="/api/payments")


@payments_bp.post("")
@limiter.limit("10 per minute")
def create_payment():
    user = require_user()
    data = request.get_json(silent=True) or {}
    amount_raw = data.get("amount_ghs") or data.get("amount")
    network = data.get("network", "Telecel")

    if amount_raw is None:
        return jsonify({"error": "amount_ghs is required"}), 400

    try:
        amount_ghs = Decimal(str(amount_raw))
    except Exception:
        return jsonify({"error": "Invalid payment amount"}), 400

    min_setting = Setting.query.filter_by(key="min_payment_ghs").first()
    max_setting = Setting.query.filter_by(key="max_payment_ghs").first()

    min_amt = Decimal(min_setting.value) if min_setting else Decimal("1.00")
    max_amt = Decimal(max_setting.value) if max_setting else Decimal("10000.00")

    if amount_ghs < min_amt or amount_ghs > max_amt:
        return jsonify({"error": f"Payment amount must be between GHS {min_amt:.2f} and GHS {max_amt:.2f}"}), 400

    payment = Payment(
        payment_id=Payment.new_payment_id(),
        user_id=user.id,
        network=network,
        amount_ghs=amount_ghs,
        status=PaymentStatus.IDLE
    )
    db.session.add(payment)
    db.session.commit()

    return jsonify({
        "payment_id": payment.payment_id,
        "amount_ghs": f"{payment.amount_ghs:.2f}",
        "network": payment.network,
        "status": payment.status,
        "expires_at": payment.expires_at.isoformat()
    }), 201


@payments_bp.post("/<payment_id>/screenshot")
@limiter.limit("10 per minute")
def upload_screenshot(payment_id: str):
    user = require_user()
    payment = Payment.query.filter_by(payment_id=payment_id).first()
    if not payment or payment.user_id != user.id:
        return jsonify({"error": "Payment not found"}), 404

    if "file" not in request.files:
        return jsonify({"error": "No screenshot file provided"}), 400

    file_storage = request.files["file"]
    
    try:
        saved_filename = validate_and_save_screenshot(payment, file_storage)
    except UploadError as exc:
        return jsonify({"error": str(exc)}), 400

    payment.attempt_count += 1
    payment.screenshot_filename = saved_filename
    payment.status = PaymentStatus.VERIFYING
    db.session.commit()

    # Trigger AI Extraction & Decision Engine
    saved_path = f"{current_app.config['UPLOAD_FOLDER']}/{saved_filename}"
    ai_result = PaymentAI.extract(saved_path, original_filename=file_storage.filename)

    decision = process_payment_verification(payment, ai_result)

    pv = PaymentVerification.query.filter_by(payment_id=payment.id).order_by(PaymentVerification.id.desc()).first()

    resp = make_response(jsonify({
        "payment_id": payment.payment_id,
        "status": decision,
        "expected_amount_ghs": f"{payment.amount_ghs:.2f}",
        "detected_amount_ghs": f"{ai_result.amount:.2f}" if ai_result.amount is not None else None,
        "recipient": ai_result.recipient_name or "BOOSTX",
        "reference": payment.transaction_reference,
        "rejection_reason": payment.rejection_reason,
    }), 200)

    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@payments_bp.get("/<payment_id>")
def get_payment(payment_id: str):
    user = require_user()
    payment = Payment.query.filter_by(payment_id=payment_id).first()
    if not payment or payment.user_id != user.id:
        return jsonify({"error": "Payment not found"}), 404

    pv = PaymentVerification.query.filter_by(payment_id=payment.id).order_by(PaymentVerification.id.desc()).first()
    raw_ai = pv.raw_ai_json if pv else {}

    resp = make_response(jsonify({
        "payment_id": payment.payment_id,
        "status": payment.status,
        "expected_amount_ghs": f"{payment.amount_ghs:.2f}",
        "detected_amount_ghs": f"{raw_ai.get('amount'):.2f}" if raw_ai.get("amount") is not None else None,
        "recipient": raw_ai.get("recipient_name") or "BOOSTX",
        "reference": payment.transaction_reference or raw_ai.get("reference"),
        "rejection_reason": payment.rejection_reason,
        "created_at": payment.created_at.isoformat()
    }), 200)

    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@payments_bp.get("")
def list_payments():
    user = require_user()
    payments = Payment.query.filter_by(user_id=user.id).order_by(Payment.id.desc()).all()
    return jsonify({
        "payments": [{
            "payment_id": p.payment_id,
            "network": p.network,
            "amount_ghs": f"{p.amount_ghs:.2f}",
            "status": p.status,
            "reference": p.transaction_reference,
            "created_at": p.created_at.isoformat()
        } for p in payments]
    }), 200
