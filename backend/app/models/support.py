from datetime import datetime, timezone
import uuid
from backend.app.db import db

class SupportTicket(db.Model):
    __tablename__ = "support_tickets"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    subject = db.Column(db.String(200), nullable=False)
    order_id_ref = db.Column(db.String(50), nullable=True)
    category = db.Column(db.String(50), nullable=False, default="Orders & delivery")
    status = db.Column(db.String(30), nullable=False, default="Open")  # Open, Answered, Closed
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @staticmethod
    def new_ticket_id() -> str:
        return f"BX-TK-{uuid.uuid4().hex[:6].upper()}"


class SupportMessage(db.Model):
    __tablename__ = "support_messages"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("support_tickets.id"), nullable=False, index=True)
    sender_role = db.Column(db.String(20), nullable=False)  # customer, admin
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
