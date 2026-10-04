from datetime import datetime, timezone
import json
import uuid
from typing import Optional
from werkzeug.security import generate_password_hash, check_password_hash
from backend.app.db import db
from backend.app.utils.phone import normalize_phone

class UserRole:
    CUSTOMER = "customer"
    ADMIN = "admin"

class UserStatus:
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"
    DELETED = "deleted"

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    public_user_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    phone = db.Column(db.String(30), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=UserRole.CUSTOMER)
    status = db.Column(db.String(20), nullable=False, default=UserStatus.ACTIVE)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    deleted_at = db.Column(db.DateTime, nullable=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    notification_prefs_raw = db.Column(db.Text, nullable=False, default='{"order_updates": true, "payment_updates": true, "promotions": false, "security_alerts": true}')
    session_version = db.Column(db.Integer, nullable=False, default=1)

    @property
    def notification_prefs(self) -> dict:
        try:
            return json.loads(self.notification_prefs_raw or "{}")
        except Exception:
            return {}

    @notification_prefs.setter
    def notification_prefs(self, val: dict) -> None:
        self.notification_prefs_raw = json.dumps(val)

    @staticmethod
    def new_public_id(role: str) -> str:
        prefix = "BX-USR" if role == UserRole.CUSTOMER else "BX-ADM"
        return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password, method="pbkdf2:sha256")

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    def is_locked(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if self.locked_until:
            locked_until_dt = self.locked_until
            if locked_until_dt.tzinfo is None:
                locked_until_dt = locked_until_dt.replace(tzinfo=timezone.utc)
            return locked_until_dt > now
        return False
