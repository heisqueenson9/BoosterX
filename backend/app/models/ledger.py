from datetime import datetime, timezone
from backend.app.db import db

class LedgerStatus:
    POSTED = "posted"
    RESERVED = "reserved"
    RELEASED = "released"

class LedgerType:
    PAYMENT_CREDIT = "payment_credit"
    ORDER_DEBIT = "order_debit"
    REFUND_CREDIT = "refund_credit"
    ADMIN_ADJUSTMENT = "admin_adjustment"

class LedgerTransaction(db.Model):
    __tablename__ = "ledger_transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    type = db.Column(db.String(30), nullable=False)
    amount_ghs = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=LedgerStatus.POSTED)
    reference = db.Column(db.String(100), nullable=True, index=True)
    description = db.Column(db.String(255), nullable=True)
    balance_before = db.Column(db.Numeric(10, 2), nullable=False)
    balance_after = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint("amount_ghs >= 0", name="chk_ledger_amount_positive"),
    )
