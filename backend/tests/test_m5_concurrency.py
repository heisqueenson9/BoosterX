import os
import io
import time
import threading
import pytest
from decimal import Decimal
from PIL import Image

from backend.app import create_app, db
from backend.app.models import (
    User, UserRole, UserStatus, Payment, PaymentStatus, LedgerTransaction, LedgerStatus, LedgerType,
    Order, OrderStatus, Service, Platform
)
from backend.app.services.ledger_service import get_owner_balance
from backend.app.orders.order_service import create_and_submit_order, OrderExecutionError
from backend.app.payments.decision_engine import process_payment_verification

from backend.app.config import Config

POSTGRES_TEST_URI = os.getenv("TEST_DATABASE_URL", "postgresql://postgres@127.0.0.1:5432/boostx_test")

class PostgresTestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = POSTGRES_TEST_URI
    SECRET_KEY = "test-secret-key-concurrency"
    PROVIDER_MODE = "fake"

def make_user(tag):
    user = User(public_user_id=f"BX-USR-{tag[:8].upper()}", email=f"{tag}@example.com", password_hash="x",
                role=UserRole.CUSTOMER, status=UserStatus.ACTIVE, full_name=tag)
    db.session.add(user)
    db.session.commit()
    return user.id

def add_credit(user_id, amount="50.00", ref="INIT-CREDIT"):
    tx = LedgerTransaction(
        user_id=user_id,
        type=LedgerType.PAYMENT_CREDIT,
        status=LedgerStatus.POSTED,
        amount_ghs=Decimal(amount),
        balance_before=Decimal("0.00"),
        balance_after=Decimal(amount),
        reference=ref
    )
    db.session.add(tx)
    db.session.commit()

@pytest.fixture
def pg_app():
    app = create_app(PostgresTestConfig)
    with app.app_context():
        db.create_all()
        runner = app.test_cli_runner()
        runner.invoke(args=["seed"])
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def pg_client(pg_app):
    return pg_app.test_client()

def test_postgres_concurrency_double_order(pg_app):
    """
    Spec §17 Critical Concurrency Test:
    Owner balance is GHS 50.
    Two simultaneous orders for GHS 40 are submitted concurrently.
    PostgreSQL SELECT FOR UPDATE row locking guarantees exactly one succeeds,
    one fails with insufficient balance, and final balance is exactly GHS 10 (never negative).
    """
    with pg_app.app_context():
        owner_id = make_user("test_concurrent_sess_1")
        add_credit(owner_id, amount="50.00", ref="INIT-CREDIT-50")
        
        initial_bal = get_owner_balance(owner_id)
        assert initial_bal == Decimal("50.00")

        # Ensure platform TikTok & service 1 active
        plat = Platform.query.filter_by(name="TikTok").first()
        if plat:
            plat.active = True
        srv = db.session.get(Service, 1)
        if srv:
            srv.enabled = True
            srv.rate_usd_per_1000 = Decimal("3.2710280373831775") # Cost ~ GHS 40.00
        db.session.commit()

        results = []
        errors = []

        def place_order(thread_id):
            with pg_app.app_context():
                try:
                    order = create_and_submit_order(
                        service_id=1,
                        target="https://tiktok.com/@concurrency_user",
                        quantity=1000,
                        user_id=owner_id,
                        idempotency_key=f"idem-key-thread-{thread_id}"
                    )
                    results.append(order)
                except OrderExecutionError as err:
                    errors.append(err)
                except Exception as e:
                    errors.append(e)

        # Launch two threads at the exact same instant
        t1 = threading.Thread(target=place_order, args=(1,))
        t2 = threading.Thread(target=place_order, args=(2,))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Verification: Exactly ONE succeeds, ONE fails
        assert len(results) == 1, f"Expected 1 order success, got {len(results)}"
        assert len(errors) == 1, f"Expected 1 order failure, got {len(errors)}"
        assert "Insufficient wallet balance" in str(errors[0])

        # Final Balance Check: Balance is GHS 10.00 (50 - 40), never negative
        final_bal = get_owner_balance(owner_id)
        assert final_bal >= Decimal("0.00")
        assert final_bal == Decimal("10.00")

def test_underpaid_screenshot_no_credit(pg_app):
    """
    Spec §17 Case A: GHS 20 screenshot against GHS 50 expected credits nothing silently.
    """
    from datetime import datetime, timedelta
    from backend.app.ai.payment_ai import PaymentAIExtraction
    with pg_app.app_context():
        owner_id = make_user("test_underpaid_sess")
        now = datetime.utcnow()
        pay = Payment(
            payment_id="PAY-UNDERPAID-1",
            user_id=owner_id,
            network="Telecel",
            amount_ghs=Decimal("50.00"),
            status=PaymentStatus.VERIFYING,
            created_at=now,
            expires_at=now + timedelta(minutes=30)
        )
        db.session.add(pay)
        db.session.commit()

        extracted_data = PaymentAIExtraction(
            amount=20.00,
            reference="TX-UNDERPAID-999",
            recipient_name="BOOSTX",
            recipient_number="0202979378",
            confidence=0.95
        )
        process_payment_verification(pay, extracted_data)

        updated_pay = db.session.get(Payment, pay.id)
        assert updated_pay.status in (PaymentStatus.REJECTED, PaymentStatus.REVIEW_REQUIRED)
        bal = get_owner_balance(owner_id)
        assert bal == Decimal("0.00")

def test_duplicate_reference_rejection(pg_app):
    """
    Spec §17 Case B: Duplicate transaction reference is rejected on second use.
    """
    from datetime import datetime, timedelta
    from backend.app.ai.payment_ai import PaymentAIExtraction
    with pg_app.app_context():
        owner_id = make_user("test_dup_ref_sess")
        now = datetime.utcnow()
        
        # Payment 1 verified with reference TX-DUP-100
        pay1 = Payment(
            payment_id="PAY-DUP-1",
            user_id=owner_id,
            network="Telecel",
            amount_ghs=Decimal("50.00"),
            status=PaymentStatus.VERIFYING,
            created_at=now,
            expires_at=now + timedelta(minutes=30)
        )
        db.session.add(pay1)
        db.session.commit()

        extracted_data_1 = PaymentAIExtraction(
            amount=50.00,
            reference="TX-DUP-100",
            recipient_name="BOOSTX",
            recipient_number="0202979378",
            status="Successful",
            confidence=0.98
        )
        process_payment_verification(pay1, extracted_data_1)
        assert db.session.get(Payment, pay1.id).status == PaymentStatus.VERIFIED
        assert get_owner_balance(owner_id) == Decimal("50.00")

        # Payment 2 attempts to use SAME reference TX-DUP-100
        pay2 = Payment(
            payment_id="PAY-DUP-2",
            user_id=owner_id,
            network="Telecel",
            amount_ghs=Decimal("50.00"),
            status=PaymentStatus.VERIFYING,
            created_at=now,
            expires_at=now + timedelta(minutes=30)
        )
        db.session.add(pay2)
        db.session.commit()

        extracted_data_2 = PaymentAIExtraction(
            amount=50.00,
            reference="TX-DUP-100",
            recipient_name="BOOSTX",
            recipient_number="0202979378",
            status="Successful",
            confidence=0.98
        )
        process_payment_verification(pay2, extracted_data_2)

        assert db.session.get(Payment, pay2.id).status == PaymentStatus.REJECTED
        assert get_owner_balance(owner_id) == Decimal("50.00")

def test_provider_failure_restores_balance_to_full(pg_app):
    """
    Spec §17 Case C: Provider failure after reservation returns balance to exactly GHS 50, not GHS 20.
    """
    with pg_app.app_context():
        owner_id = make_user("test_prov_fail_sess")
        add_credit(owner_id, amount="50.00", ref="INIT-CREDIT-PROV-FAIL")
        assert get_owner_balance(owner_id) == Decimal("50.00")

        plat = Platform.query.filter_by(name="TikTok").first()
        if plat:
            plat.active = True
        srv = db.session.get(Service, 1)
        if srv:
            srv.enabled = True
            srv.rate_usd_per_1000 = Decimal("2.33") # Cost ~ GHS 30.00
        db.session.commit()

        from backend.app.providers.factory import get_provider_client
        provider = get_provider_client()
        provider.fail_next_add = True

        with pytest.raises(OrderExecutionError) as exc_info:
            create_and_submit_order(
                service_id=1,
                target="https://tiktok.com/@private_user",
                quantity=1000,
                user_id=owner_id,
            )
        assert "Provider submission failed" in str(exc_info.value)

        bal = get_owner_balance(owner_id)
        assert bal == Decimal("50.00")
