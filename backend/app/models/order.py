from datetime import datetime, timezone
import uuid
from backend.app.db import db

class OrderStatus:
    PENDING = "Pending"
    PROCESSING = "Processing"
    COMPLETED = "Completed"
    PARTIAL = "Partial"
    CANCELLED = "Cancelled"
    FAILED = "Failed"
    REFUNDED = "Refunded"

class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    public_order_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    idempotency_key = db.Column(db.String(64), nullable=True, index=True)
    platform = db.Column(db.String(30), nullable=False)
    service_id = db.Column(db.Integer, nullable=False)
    service_name = db.Column(db.String(150), nullable=False)
    target = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    charge_ghs = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(30), nullable=False, default=OrderStatus.PENDING)
    provider_order_id = db.Column(db.Integer, nullable=True, index=True)
    provider_status_raw = db.Column(db.String(50), nullable=True)
    provider_charge = db.Column(db.Numeric(10, 4), nullable=True)
    needs_attention = db.Column(db.Boolean, nullable=False, default=False)
    start_count = db.Column(db.Integer, nullable=True)
    remains = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)

    @staticmethod
    def new_public_id() -> str:
        return f"BX-ORD-{uuid.uuid4().hex[:8].upper()}"


class OrderEvent(db.Model):
    __tablename__ = "order_events"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    event_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class Refill(db.Model):
    __tablename__ = "refills"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    provider_refill_id = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="Pending")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class Refund(db.Model):
    __tablename__ = "refunds"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    amount_ghs = db.Column(db.Numeric(10, 2), nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
