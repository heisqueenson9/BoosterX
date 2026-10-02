from datetime import datetime, timezone
from backend.app.db import db

class Platform(db.Model):
    __tablename__ = "platforms"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)


class Service(db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    provider_service_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    platform = db.Column(db.String(30), nullable=False, index=True)
    category = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    type = db.Column(db.String(50), nullable=False, default="Default")
    description = db.Column(db.Text, nullable=True)
    rate_usd_per_1000 = db.Column(db.Numeric(10, 4), nullable=False)
    min_qty = db.Column(db.Integer, nullable=False)
    max_qty = db.Column(db.Integer, nullable=False)
    refill_available = db.Column(db.Boolean, nullable=False, default=False)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    last_synced_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
