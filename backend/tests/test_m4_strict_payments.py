import os
from io import BytesIO
from decimal import Decimal
import pytest
from PIL import Image
from backend.app import create_app, db
from backend.app.models import Payment, PaymentStatus, LedgerTransaction, LedgerType
from backend.app.services.ledger_service import get_owner_balance

@pytest.fixture
def app():
    db_path = os.path.join(os.path.dirname(__file__), "test_m4_strict.db")
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass
    app = create_app()
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SECRET_KEY": "test-secret-key",
        "PROVIDER_MODE": "fake"
    })
    with app.app_context():
        db.create_all()
        runner = app.test_cli_runner()
        runner.invoke(args=["seed"])
        yield app
        db.session.remove()
        db.drop_all()
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def customer_headers(client, signup):
    return signup(client, email="customer_strict@example.com")

def _create_mock_png():
    """Generates valid PNG image bytes for testing upload security."""
    img = Image.new("RGB", (100, 100), color="blue")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def test_payment_spec_test_1_recipient_phone_matching(client, customer_headers):
    """TEST 1: Recipient=0202979378, Amount=20.00, Status=successful => APPROVED, Credit=20.00"""
    res = client.post("/api/payments", json={"amount_ghs": "20.00", "network": "Telecel"}, headers=customer_headers)
    assert res.status_code == 201
    pay_id = res.json["payment_id"]

    buf = _create_mock_png()
    res_up = client.post(f"/api/payments/{pay_id}/screenshot", data={"file": (buf, "test1_phone.png")}, headers=customer_headers)
    assert res_up.status_code == 200
    assert res_up.json["status"] == PaymentStatus.VERIFIED
    assert res_up.json["verified"] is True
    assert res_up.json["verified_amount"] == 20.0

def test_payment_spec_test_2_recipient_name_matching(client, customer_headers):
    """TEST 2: Recipient=Enock Queenson Eduafo, Amount=100.00, Status=successful => APPROVED, Credit=100.00"""
    res = client.post("/api/payments", json={"amount_ghs": "100.00", "network": "Telecel"}, headers=customer_headers)
    assert res.status_code == 201
    pay_id = res.json["payment_id"]

    buf = _create_mock_png()
    res_up = client.post(f"/api/payments/{pay_id}/screenshot", data={"file": (buf, "test2_name.png")}, headers=customer_headers)
    assert res_up.status_code == 200
    assert res_up.json["status"] == PaymentStatus.VERIFIED
    assert res_up.json["verified"] is True
    assert res_up.json["verified_amount"] == 100.0

def test_payment_spec_test_3_recipient_info_missing(client, customer_headers):
    """TEST 3: Screenshot Amount=20.00, Recipient missing => REJECTED, Credit=0.00"""
    res = client.post("/api/payments", json={"amount_ghs": "20.00", "network": "Telecel"}, headers=customer_headers)
    pay_id = res.json["payment_id"]

    buf = _create_mock_png()
    res_up = client.post(f"/api/payments/{pay_id}/screenshot", data={"file": (buf, "test3_missing.png")}, headers=customer_headers)
    assert res_up.status_code == 200
    assert res_up.json["status"] == PaymentStatus.REJECTED
    assert res_up.json["verified"] is False

def test_payment_spec_test_4_wrong_recipient_phone(client, customer_headers):
    """TEST 4: Screenshot Amount=20.00, Wrong recipient phone => REJECTED, Credit=0.00"""
    res = client.post("/api/payments", json={"amount_ghs": "20.00", "network": "Telecel"}, headers=customer_headers)
    pay_id = res.json["payment_id"]

    buf = _create_mock_png()
    res_up = client.post(f"/api/payments/{pay_id}/screenshot", data={"file": (buf, "test4_wrong_phone.png")}, headers=customer_headers)
    assert res_up.status_code == 200
    assert res_up.json["status"] == PaymentStatus.REJECTED
    assert res_up.json["verified"] is False

def test_payment_spec_test_5_wrong_recipient_name(client, customer_headers):
    """TEST 5: Screenshot Amount=20.00, Wrong recipient name => REJECTED, Credit=0.00"""
    res = client.post("/api/payments", json={"amount_ghs": "20.00", "network": "Telecel"}, headers=customer_headers)
    pay_id = res.json["payment_id"]

    buf = _create_mock_png()
    res_up = client.post(f"/api/payments/{pay_id}/screenshot", data={"file": (buf, "test5_wrong_name.png")}, headers=customer_headers)
    assert res_up.status_code == 200
    assert res_up.json["status"] == PaymentStatus.REJECTED
    assert res_up.json["verified"] is False

def test_payment_spec_test_6_amount_mismatch_never_credit_typed(client, customer_headers):
    """TEST 6: User types 100.00, Screenshot shows 20.00 => REJECTED, NEVER credit 100.00"""
    res = client.post("/api/payments", json={"amount_ghs": "100.00", "network": "Telecel"}, headers=customer_headers)
    pay_id = res.json["payment_id"]

    buf = _create_mock_png()
    res_up = client.post(f"/api/payments/{pay_id}/screenshot", data={"file": (buf, "test6_mismatch.png")}, headers=customer_headers)
    assert res_up.status_code == 200
    assert res_up.json["status"] == PaymentStatus.REJECTED
    assert res_up.json["verified"] is False

def test_payment_spec_test_7_duplicate_transaction_prevention(client, customer_headers):
    """TEST 7: User sends same valid transaction twice => 1st APPROVED, 2nd REJECTED as duplicate"""
    res1 = client.post("/api/payments", json={"amount_ghs": "20.00", "network": "Telecel"}, headers=customer_headers)
    pay_id1 = res1.json["payment_id"]
    buf1 = _create_mock_png()
    res_up1 = client.post(f"/api/payments/{pay_id1}/screenshot", data={"file": (buf1, "test7_dup.png")}, headers=customer_headers)
    assert res_up1.json["status"] == PaymentStatus.VERIFIED

    res2 = client.post("/api/payments", json={"amount_ghs": "20.00", "network": "Telecel"}, headers=customer_headers)
    pay_id2 = res2.json["payment_id"]
    buf2 = _create_mock_png()
    res_up2 = client.post(f"/api/payments/{pay_id2}/screenshot", data={"file": (buf2, "test7_dup.png")}, headers=customer_headers)
    assert res_up2.json["status"] == PaymentStatus.REJECTED
    assert "already used" in res_up2.json["rejection_reason"]

def test_payment_spec_test_8_fake_screenshot(client, customer_headers):
    """TEST 8: Fake/edited screenshot with no recognizable evidence => REJECTED"""
    res = client.post("/api/payments", json={"amount_ghs": "20.00", "network": "Telecel"}, headers=customer_headers)
    pay_id = res.json["payment_id"]

    buf = _create_mock_png()
    res_up = client.post(f"/api/payments/{pay_id}/screenshot", data={"file": (buf, "test8_fake.png")}, headers=customer_headers)
    assert res_up.status_code == 200
    assert res_up.json["status"] == PaymentStatus.REJECTED
    assert res_up.json["verified"] is False

def test_payment_spec_test_9_phone_number_alone_not_proof(client, customer_headers):
    """TEST 9: Random screenshot containing ONLY phone number 0202979378 but no valid payment evidence => REJECTED"""
    res = client.post("/api/payments", json={"amount_ghs": "20.00", "network": "Telecel"}, headers=customer_headers)
    pay_id = res.json["payment_id"]

    buf = _create_mock_png()
    res_up = client.post(f"/api/payments/{pay_id}/screenshot", data={"file": (buf, "test9_phone_no_proof.png")}, headers=customer_headers)
    assert res_up.status_code == 200
    assert res_up.json["status"] == PaymentStatus.REJECTED
    assert res_up.json["verified"] is False

def test_payment_spec_test_10_another_person_payment(client, customer_headers):
    """TEST 10: Screenshot contains another person's payment => REJECTED"""
    res = client.post("/api/payments", json={"amount_ghs": "50.00", "network": "Telecel"}, headers=customer_headers)
    pay_id = res.json["payment_id"]

    buf = _create_mock_png()
    res_up = client.post(f"/api/payments/{pay_id}/screenshot", data={"file": (buf, "test10_another.png")}, headers=customer_headers)
    assert res_up.status_code == 200
    assert res_up.json["status"] == PaymentStatus.REJECTED
    assert res_up.json["verified"] is False

def test_payment_spec_test_11_network_mismatch(client, customer_headers):
    """TEST 11: Selected network is MTN but screenshot is Telecel => REJECTED with network mismatch"""
    res = client.post("/api/payments", json={"amount_ghs": "20.00", "network": "MTN"}, headers=customer_headers)
    pay_id = res.json["payment_id"]

    buf = _create_mock_png()
    # Mock screenshot filename contains telecel so AI returns provider Telecel while payment network is MTN
    res_up = client.post(f"/api/payments/{pay_id}/screenshot", data={"file": (buf, "test11_telecel.png")}, headers=customer_headers)
    assert res_up.status_code == 200
    assert res_up.json["status"] == PaymentStatus.REJECTED
    assert res_up.json["verified"] is False

