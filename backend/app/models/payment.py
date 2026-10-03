from datetime import datetime, timezone, timedelta
import json
import uuid
from backend.app.db import db
from backend.app.utils.datetime import utc_now

class PaymentStatus:
    IDLE = "Idle"
    UPLOADING = "Uploading"
    VERIFYING = "verifying"
    VERIFIED = "Verified"
    REJECTED = "Rejected"
    REVIEW_REQUIRED = "Review Required"
    EXPIRED = "Expired"

class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    network = db.Column(db.String(20), nullable=False, default="Telecel")
    amount_ghs = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(30), nullable=False, default=PaymentStatus.IDLE)
    screenshot_filename = db.Column(db.String(255), nullable=True)
    file_hash = db.Column(db.String(64), nullable=True, index=True)
    transaction_reference = db.Column(db.String(100), nullable=True, index=True)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    rejection_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    expires_at = db.Column(db.DateTime, nullable=False, default=lambda: utc_now() + timedelta(minutes=30))
    verified_at = db.Column(db.DateTime, nullable=True)

    @staticmethod
    def new_payment_id() -> str:
        return f"BX-PAY-{uuid.uuid4().hex[:8].upper()}"


class PaymentVerification(db.Model):
    __tablename__ = "payment_verifications"

    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"), nullable=False, index=True)
    raw_ai_json_str = db.Column(db.Text, nullable=True)
    checks_passed_str = db.Column(db.Text, nullable=True)
    checks_failed_str = db.Column(db.Text, nullable=True)
    confidence = db.Column(db.Numeric(5, 2), nullable=True)
    decision = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    @property
    def raw_ai_json(self) -> dict:
        try:
            return json.loads(self.raw_ai_json_str or "{}")
        except Exception:
            return {}

    @raw_ai_json.setter
    def raw_ai_json(self, val: dict) -> None:
        self.raw_ai_json_str = json.dumps(val)

    @property
    def checks_passed(self) -> list:
        try:
            return json.loads(self.checks_passed_str or "[]")
        except Exception:
            return []

    @checks_passed.setter
    def checks_passed(self, val: list) -> None:
        self.checks_passed_str = json.dumps(val)

    @property
    def checks_failed(self) -> list:
        try:
            return json.loads(self.checks_failed_str or "[]")
        except Exception:
            return []

    @checks_failed.setter
    def checks_failed(self, val: list) -> None:
        self.checks_failed_str = json.dumps(val)
