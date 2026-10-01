import os
import io
import pytest
from PIL import Image
from backend.app import create_app, db
from backend.app.models import Payment, PaymentStatus, LedgerTransaction, LedgerType
from backend.app.services.ledger_service import get_owner_balance

@pytest.fixture
def app():
    db_path = os.path.join(os.path.dirname(__file__), "test_m4.db")
    if os.path.exists(db_path):
        os.remove(db_path)
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

def create_dummy_image_bytes(fmt="PNG"):
    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    return buf

def test_create_payment(client):
    csrf = client.post("/api/session").get_json()["csrf_token"]
    res = client.post("/api/payments", json={
        "amount_ghs": 100.00,
        "network": "Telecel"
    }, headers={"X-CSRF-Token": csrf})
    assert res.status_code == 201
    data = res.get_json()
    assert "payment_id" in data
    assert data["amount_ghs"] == "100.00"
    assert data["status"] == "Idle"

def test_screenshot_upload_and_verification(client, app):
    # Establish guest session
    res_s = client.post("/api/session")
    csrf_tok = res_s.get_json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_tok}

    # 1. Create Payment
    res_p = client.post("/api/payments", json={"amount_ghs": 100.00, "network": "Telecel"}, headers=headers)
    p_id = res_p.get_json()["payment_id"]

    # 2. Upload Screenshot (verified mock filename)
    img_bytes = create_dummy_image_bytes("PNG")
    data = {"file": (img_bytes, "receipt.png")}
    
    res_u = client.post(f"/api/payments/{p_id}/screenshot", data=data, content_type="multipart/form-data", headers=headers)
    assert res_u.status_code == 200
    u_data = res_u.get_json()
    assert u_data["status"] == "Verified"
    assert u_data["expected_amount_ghs"] == "100.00"

    # Check ledger balance updated
    with app.app_context():
        payment = Payment.query.filter_by(payment_id=p_id).first()
        bal = get_owner_balance(None, payment.session_id)
        assert bal == 100.00

def test_underpaid_screenshot_no_credit(client, app):
    # GHS 20 screenshot on GHS 50 expected yields no credit
    res_s = client.post("/api/session")
    csrf_tok = res_s.get_json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_tok}

    res_p = client.post("/api/payments", json={"amount_ghs": 50.00, "network": "Telecel"}, headers=headers)
    p_id = res_p.get_json()["payment_id"]

    img_bytes = create_dummy_image_bytes("PNG")
    data = {"file": (img_bytes, "reject_underpaid.png")}

    res_u = client.post(f"/api/payments/{p_id}/screenshot", data=data, content_type="multipart/form-data", headers=headers)
    assert res_u.status_code == 200
    u_data = res_u.get_json()
    assert u_data["status"] == "Rejected"
    assert u_data["rejection_reason"] is not None

    with app.app_context():
        payment = Payment.query.filter_by(payment_id=p_id).first()
        bal = get_owner_balance(None, payment.session_id)
        assert bal == 0.00  # No credit awarded

def test_duplicate_reference_rejection(client, app):
    res_s = client.post("/api/session")
    csrf_tok = res_s.get_json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_tok}

    # Manually insert ledger transaction with reference TX_DUPLICATE
    with app.app_context():
        tx = LedgerTransaction(
            user_id=None,
            session_id="test_sess",
            type=LedgerType.PAYMENT_CREDIT,
            amount_ghs=50.00,
            status="posted",
            reference="TX804188",
            description="Prior payment",
            balance_before=0,
            balance_after=50
        )
        db.session.add(tx)
        db.session.commit()

    res_p = client.post("/api/payments", json={"amount_ghs": 50.00, "network": "Telecel"}, headers=headers)
    p_id = res_p.get_json()["payment_id"]

    img_bytes = create_dummy_image_bytes("PNG")
    data = {"file": (img_bytes, "mismatch_dup.png")}

    res_u = client.post(f"/api/payments/{p_id}/screenshot", data=data, content_type="multipart/form-data", headers=headers)
    assert res_u.status_code == 200
    u_data = res_u.get_json()
    assert u_data["status"] == "Rejected"
    assert "Transaction already used" in u_data["rejection_reason"]


def test_pdf_upload_rejection(client, app):
    """PDF files must be rejected by magic bytes (%PDF) returning HTTP 400 Bad Request."""
    res_s = client.post("/api/session")
    csrf_tok = res_s.get_json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_tok}

    res_p = client.post("/api/payments", json={"amount_ghs": 100.00, "network": "Telecel"}, headers=headers)
    p_id = res_p.get_json()["payment_id"]

    pdf_bytes = io.BytesIO(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF")
    data = {"file": (pdf_bytes, "receipt.pdf")}

    res_u = client.post(f"/api/payments/{p_id}/screenshot", data=data, content_type="multipart/form-data", headers=headers)
    assert res_u.status_code == 400
    u_data = res_u.get_json()
    assert "PDF files are not accepted" in u_data["error"]

    # Verify payment status remained Idle (AI not invoked)
    with app.app_context():
        payment = Payment.query.filter_by(payment_id=p_id).first()
        assert payment.status == PaymentStatus.IDLE


def test_expired_screenshot_timestamp(client, app):
    """Screenshot timestamp outside the payment window must be rejected."""
    res_s = client.post("/api/session")
    csrf_tok = res_s.get_json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_tok}

    res_p = client.post("/api/payments", json={"amount_ghs": 100.00, "network": "Telecel"}, headers=headers)
    p_id = res_p.get_json()["payment_id"]

    img_bytes = create_dummy_image_bytes("PNG")
    data = {"file": (img_bytes, "expired_timestamp.png")}

    res_u = client.post(f"/api/payments/{p_id}/screenshot", data=data, content_type="multipart/form-data", headers=headers)
    assert res_u.status_code == 200
    u_data = res_u.get_json()
    assert u_data["status"] == "Rejected"
    assert "outside the valid payment window" in u_data["rejection_reason"]


def test_doctored_screenshot_rejection(client, app):
    """Screenshots flagged with manipulation or doctored integrity flags must be rejected."""
    res_s = client.post("/api/session")
    csrf_tok = res_s.get_json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_tok}

    res_p = client.post("/api/payments", json={"amount_ghs": 100.00, "network": "Telecel"}, headers=headers)
    p_id = res_p.get_json()["payment_id"]

    img_bytes = create_dummy_image_bytes("PNG")
    data = {"file": (img_bytes, "doctored_screenshot.png")}

    res_u = client.post(f"/api/payments/{p_id}/screenshot", data=data, content_type="multipart/form-data", headers=headers)
    assert res_u.status_code == 200
    u_data = res_u.get_json()
    assert u_data["status"] == "Rejected"
    assert "image manipulation or reuse" in u_data["rejection_reason"]

