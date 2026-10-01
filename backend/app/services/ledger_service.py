from decimal import Decimal
from typing import Optional, Tuple
from sqlalchemy import func
from backend.app.db import db
from backend.app.models import LedgerTransaction, LedgerStatus, LedgerType

def get_owner_balance(user_id: Optional[int]) -> Decimal:
    """
    Computes available balance = posted credits - posted debits - reserved debits
    for the account `user_id`.
    """
    if not user_id:
        return Decimal("0.00")

    query = db.session.query(
        func.coalesce(func.sum(LedgerTransaction.amount_ghs), Decimal("0.00"))
    )

    filter_clause = (LedgerTransaction.user_id == user_id)

    # 1. Posted credits (payment_credit, refund_credit, admin_adjustment +)
    posted_credits = query.filter(
        filter_clause,
        LedgerTransaction.status == LedgerStatus.POSTED,
        LedgerTransaction.type.in_([LedgerType.PAYMENT_CREDIT, LedgerType.REFUND_CREDIT, LedgerType.ADMIN_ADJUSTMENT])
    ).scalar() or Decimal("0.00")

    # 2. Posted debits (order_debit)
    posted_debits = query.filter(
        filter_clause,
        LedgerTransaction.status == LedgerStatus.POSTED,
        LedgerTransaction.type == LedgerType.ORDER_DEBIT
    ).scalar() or Decimal("0.00")

    # 3. Reserved debits (order_debit in reserved state)
    reserved_debits = query.filter(
        filter_clause,
        LedgerTransaction.status == LedgerStatus.RESERVED,
        LedgerTransaction.type == LedgerType.ORDER_DEBIT
    ).scalar() or Decimal("0.00")

    available = posted_credits - posted_debits - reserved_debits
    return max(Decimal("0.00"), available)
