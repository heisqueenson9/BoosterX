from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
import re
from flask import current_app
from backend.app.db import db
from backend.app.models import Payment, PaymentStatus, PaymentVerification, LedgerTransaction, LedgerStatus, LedgerType, Setting, User, Notification
from backend.app.ai.payment_ai import PaymentAIExtraction
from backend.app.utils.phone import normalize_phone
from backend.app.services.ledger_service import get_owner_balance


def _validate_reference_format(ref: str, network: str = None) -> bool:
    if not ref or len(ref) < 6 or len(ref) > 30:
        return False
    if not re.match(r'^[A-Za-z0-9\-_]+$', ref):
        return False
    net_lower = (network or "").lower()
    if "telecel" in net_lower:
        if not re.match(r'^(TX|tx)?[A-Za-z0-9\-_]{4,24}$', ref):
            return False
    elif "mtn" in net_lower or "airtel" in net_lower or "tigo" in net_lower:
        if not re.match(r'^[A-Za-z0-9\-_]{6,24}$', ref):
            return False
    return True


def _parse_screenshot_datetime(dt_str: str):
    if not dt_str:
        return None
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    ]
    clean_str = dt_str.strip()
    for fmt in formats:
        try:
            return datetime.strptime(clean_str, fmt)
        except ValueError:
            continue
    try:
        from dateutil import parser
        return parser.parse(clean_str).replace(tzinfo=None)
    except Exception:
        return None


def _to_naive_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
import re
from flask import current_app
from backend.app.db import db
from backend.app.models import Payment, PaymentStatus, PaymentVerification, LedgerTransaction, LedgerStatus, LedgerType, Setting, User, Notification
from backend.app.ai.payment_ai import PaymentAIExtraction
from backend.app.utils.phone import normalize_phone
from backend.app.services.ledger_service import get_owner_balance


def _validate_reference_format(ref: str, network: str = None) -> bool:
    if not ref or len(ref) < 6 or len(ref) > 30:
        return False
    if not re.match(r'^[A-Za-z0-9\-_]+$', ref):
        return False
    net_lower = (network or "").lower()
    if "telecel" in net_lower:
        if not re.match(r'^(TX|tx)?[A-Za-z0-9\-_]{4,24}$', ref):
            return False
    elif "mtn" in net_lower or "airtel" in net_lower or "tigo" in net_lower:
        if not re.match(r'^[A-Za-z0-9\-_]{6,24}$', ref):
            return False
    return True


def _parse_screenshot_datetime(dt_str: str):
    if not dt_str:
        return None
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    ]
    clean_str = dt_str.strip()
    for fmt in formats:
        try:
            return datetime.strptime(clean_str, fmt)
        except ValueError:
            continue
    try:
        from dateutil import parser
        return parser.parse(clean_str).replace(tzinfo=None)
    except Exception:
        return None


def _to_naive_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def process_payment_verification(payment: Payment, ai_result: PaymentAIExtraction, admin_override_action: str = None) -> str:
    """
    Evaluates AI extraction results against backend rules and payment expectations strictly.
    Runs verification and ledger crediting in ONE transaction with owner lock.
    Returns decision: 'Verified', 'Rejected', 'Review Required', or 'Expired'.
    """
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    payment_expires = _to_naive_utc(payment.expires_at)

    # 1. Check expiration
    if payment_expires and now_utc > payment_expires and payment.status not in (PaymentStatus.VERIFIED, PaymentStatus.REJECTED):
        payment.status = PaymentStatus.EXPIRED
        db.session.commit()
        return PaymentStatus.EXPIRED

    # Handle Admin Override (Approve / Reject)
    if admin_override_action == "approve":
        return _apply_verified_credit(payment, ai_result, admin_approved=True)
    elif admin_override_action == "reject":
        payment.status = PaymentStatus.REJECTED
        payment.rejection_reason = payment.rejection_reason or "Admin rejected payment proof."
        _log_verification(payment.id, ai_result, decision=PaymentStatus.REJECTED, failed_checks=["admin_rejected"])
        db.session.commit()
        return PaymentStatus.REJECTED

    # Idempotency check: if already verified, return Verified without crediting again
    if payment.status == PaymentStatus.VERIFIED:
        return PaymentStatus.VERIFIED

    passed_checks = []
    failed_checks = []

    # 1. Check Recipient Number or Name Strictly
    payment_num_setting = Setting.query.filter_by(key="payment_number").first()
    target_num = payment_num_setting.value if payment_num_setting else "0202979378"
    norm_target_num = normalize_phone(target_num)

    allowed_aliases = ["ENOCK QUEENSON EDUAFO", "ENOCK QUEENSON", "QUEENSON EDUAFO", "BOOSTX", "BOOST X", "BOOSTX GHANA", "0202979378"]
    aliases_setting = Setting.query.filter_by(key="payment_recipient_aliases").first()
    if aliases_setting:
        try:
            db_aliases = json.loads(aliases_setting.value)
            if isinstance(db_aliases, list):
                allowed_aliases = list(set(allowed_aliases + [str(a).strip().upper() for a in db_aliases]))
        except Exception:
            pass

    extracted_num = normalize_phone(ai_result.recipient_number) if ai_result.recipient_number else None
    extracted_name = (ai_result.recipient_name or "").strip().upper()

    # Recipient match rules:
    # Option A: exact normalized phone number 0202979378 (or 233202979378)
    # Option B: exact normalized recipient name Enock Queenson Eduafo (or allowed aliases)
    num_match = (extracted_num == norm_target_num or extracted_num == "0202979378" or extracted_num == "233202979378") if extracted_num else False
    name_match = False
    if extracted_name:
        if "ENOCK" in extracted_name or "QUEENSON" in extracted_name or "EDUAFO" in extracted_name or "BOOSTX" in extracted_name:
            name_match = any(alias.upper() in extracted_name for alias in allowed_aliases)

    if num_match or name_match:
        passed_checks.append("recipient_matched")
    else:
        failed_checks.append("recipient_mismatch")
        payment.rejection_reason = "Required recipient phone number or recipient name was not clearly detected in the payment screenshot."

    # 2. Check Completed Payment Status
    status_clean = (ai_result.status or "").lower()
    if status_clean in ("successful", "success", "completed", "sent"):
        passed_checks.append("status_successful")
    else:
        failed_checks.append("status_unsuccessful")
        if not payment.rejection_reason:
            payment.rejection_reason = "Payment status is invalid or no valid completed payment evidence detected in screenshot."

    # 3. Check Reference & Screenshot Hash Uniqueness
    ref = (ai_result.reference or "").strip()
    if not ref:
        failed_checks.append("missing_reference")
    else:
        if not _validate_reference_format(ref, payment.network):
            failed_checks.append("invalid_reference_format")
            payment.rejection_reason = "Transaction reference format is invalid for selected network."
        else:
            existing_tx = LedgerTransaction.query.filter_by(reference=ref, type=LedgerType.PAYMENT_CREDIT).first()
            existing_verified_pay = Payment.query.filter_by(transaction_reference=ref, status=PaymentStatus.VERIFIED).first()
            if existing_tx or (existing_verified_pay and existing_verified_pay.id != payment.id):
                failed_checks.append("duplicate_reference")
                payment.rejection_reason = "Transaction already used."
            else:
                passed_checks.append("reference_unique")

    # Check file_hash duplicate
    if payment.file_hash:
        existing_hash = Payment.query.filter(
            Payment.file_hash == payment.file_hash,
            Payment.id != payment.id,
            Payment.status == PaymentStatus.VERIFIED
        ).first()
        if existing_hash:
            failed_checks.append("duplicate_file_hash")
            payment.rejection_reason = "Transaction already used."

    # 4. Check Screenshot Datetime Window
    if ai_result.datetime:
        parsed_dt = _parse_screenshot_datetime(ai_result.datetime)
        if parsed_dt:
            payment_created = _to_naive_utc(payment.created_at) or now_utc
            payment_expires_dt = payment_expires or (payment_created + timedelta(minutes=30))
            
            min_allowed = payment_created - timedelta(minutes=15)
            max_allowed = payment_expires_dt + timedelta(minutes=5)

            if parsed_dt < min_allowed or parsed_dt > max_allowed:
                failed_checks.append("expired_screenshot_timestamp")
                payment.rejection_reason = "Screenshot timestamp is outside the valid payment window."
            else:
                passed_checks.append("timestamp_valid")

    # 5. Check Amount (Source of truth is screenshot)
    if ai_result.amount is None or ai_result.amount <= 0:
        failed_checks.append("missing_amount")
        if not payment.rejection_reason:
            payment.rejection_reason = "Payment amount could not be detected in the payment screenshot."
    else:
        detected_amt = Decimal(str(ai_result.amount))
        expected_amt = Decimal(str(payment.amount_ghs))

        if detected_amt == expected_amt:
            passed_checks.append("amount_exact")
        else:
            failed_checks.append("amount_mismatch")
            payment.rejection_reason = f"Payment amount in screenshot (GHS {detected_amt:.2f}) does not match entered amount (GHS {expected_amt:.2f})."

    # 6. Check AI Integrity Flags (Doctored / Manipulated Screenshots)
    flags_lower = [f.lower() for f in (ai_result.integrity_flags or [])]
    has_doctored_flag = any(any(kw in flag for kw in ("doctored", "manipulated", "edited", "reused", "tampered", "fake")) for flag in flags_lower)

    if has_doctored_flag:
        failed_checks.append("doctored_screenshot")
        payment.rejection_reason = "Screenshot flagged for image manipulation or reuse."
    elif any(kw in f for f in flags_lower for kw in ("unreadable", "failed")):
        failed_checks.append("unreadable_screenshot")

    if ai_result.confidence < 0.85 or ("low_confidence" in ai_result.integrity_flags):
        if "low_confidence" not in failed_checks:
            failed_checks.append("low_confidence")

    # Decision Matrix Evaluation:
    reject_flags = {
        "duplicate_reference", "duplicate_file_hash", "recipient_mismatch", "status_unsuccessful",
        "missing_amount", "amount_mismatch", "doctored_screenshot", "invalid_reference_format", "expired_screenshot_timestamp"
    }
    if any(flag in failed_checks for flag in reject_flags):
        decision = PaymentStatus.REJECTED
        payment.status = PaymentStatus.REJECTED
        payment.transaction_reference = ref or None
        _log_verification(payment.id, ai_result, decision, passed_checks, failed_checks)
        db.session.commit()
        return PaymentStatus.REJECTED

    review_flags = {"low_confidence", "missing_reference", "unreadable_screenshot"}
    if any(flag in failed_checks for flag in review_flags):
        decision = PaymentStatus.REVIEW_REQUIRED
        payment.status = PaymentStatus.REVIEW_REQUIRED
        payment.transaction_reference = ref or None
        _log_verification(payment.id, ai_result, decision, passed_checks, failed_checks)
        db.session.commit()
        return PaymentStatus.REVIEW_REQUIRED

    # All checks passed -> Apply Credit in single transaction
    payment.transaction_reference = ref
    return _apply_verified_credit(payment, ai_result, passed_checks, failed_checks)


def _apply_verified_credit(payment: Payment, ai_result: PaymentAIExtraction, passed_checks=None, failed_checks=None, admin_approved=False) -> str:
    """
    Applies payment credit to owner's ledger in ONE transaction with SELECT FOR UPDATE lock.
    Uses verified screenshot amount as source of truth.
    Idempotent: if already verified, returns 'Verified' without double-crediting.
    """
    if payment.status == PaymentStatus.VERIFIED:
        return PaymentStatus.VERIFIED

    passed_checks = passed_checks or ["admin_approved" if admin_approved else "all_passed"]
    failed_checks = failed_checks or []

    with db.session.begin_nested():
        # Lock owner row
        if not payment.user_id:
            raise ValueError(f"Payment {payment.payment_id} has no owning account and cannot be credited.")
        user_id = payment.user_id
        db.session.query(User).filter_by(id=user_id).with_for_update().first()

        # Calculate balance before
        balance_before = get_owner_balance(user_id)

        # Source of truth: verified screenshot amount
        if ai_result and ai_result.amount is not None and ai_result.amount > 0:
            credit_amount = Decimal(str(ai_result.amount))
        else:
            credit_amount = Decimal(str(payment.amount_ghs))

        balance_after = balance_before + credit_amount

        # Update payment status
        payment.status = PaymentStatus.VERIFIED
        payment.verified_at = datetime.now(timezone.utc)

        # Create Ledger Transaction (posted)
        ledger = LedgerTransaction(
            user_id=user_id,
            type=LedgerType.PAYMENT_CREDIT,
            amount_ghs=credit_amount,
            status=LedgerStatus.POSTED,
            reference=payment.transaction_reference or payment.payment_id,
            description=f"Mobile money top-up ({payment.network})",
            balance_before=balance_before,
            balance_after=balance_after
        )
        db.session.add(ledger)

        # Log verification
        _log_verification(payment.id, ai_result, PaymentStatus.VERIFIED, passed_checks, failed_checks)

        # Create Notification
        notif = Notification(
            user_id=user_id,
            title="Payment Verified",
            message=f"Your payment of GHS {credit_amount:.2f} has been verified and credited to your wallet."
        )
        db.session.add(notif)

    db.session.commit()
    return PaymentStatus.VERIFIED


def _log_verification(payment_id: int, ai_result: PaymentAIExtraction, decision: str, passed_checks=None, failed_checks=None):
    if not ai_result:
        raw_dict = {}
    elif hasattr(ai_result, "model_dump"):
        raw_dict = ai_result.model_dump()
    elif hasattr(ai_result, "dict"):
        raw_dict = ai_result.dict()
    else:
        raw_dict = dict(ai_result)

    confidence_val = Decimal(str(ai_result.confidence)) if (ai_result and ai_result.confidence is not None) else Decimal("0.0")

    pv = PaymentVerification(
        payment_id=payment_id,
        confidence=confidence_val,
        decision=decision
    )
    pv.raw_ai_json = raw_dict
    pv.checks_passed = passed_checks or []
    pv.checks_failed = failed_checks or []
    db.session.add(pv)

