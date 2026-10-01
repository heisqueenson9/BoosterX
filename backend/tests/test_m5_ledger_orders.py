import os
import io
import pytest
from decimal import Decimal
from PIL import Image
from backend.app import create_app, db
from backend.app.models import (
    Order, OrderStatus, LedgerTransaction, LedgerStatus, LedgerType,
    Payment, PaymentStatus, Service, Platform
)
from backend.app.services.ledger_service import get_owner_balance
from backend.app.orders.order_service import create_and_submit_order, OrderExecutionError
from backend.app.workers.order_worker import check_pending_orders, expire_payments

@pytest.fixture
def app():
    db_path = os.path.join(os.path.dirname(__file__), "test_m5.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    app = create_app()
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SECRET_KEY": "test-secret-key-m5",
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

def test_order_insufficient_balance(client, signup):
    # Establish session
    headers = signup(client)
    csrf_tok = headers["X-CSRF-Token"]
    headers = {"X-CSRF-Token": csrf_tok}

    # Attempt to place order with 0 balance
    res_o = client.post("/api/orders", json={
        "service_id": 1,
        "target": "https://tiktok.com/@testuser",
        "quantity": 1000
    }, headers=headers)
    assert res_o.status_code == 402
    data = res_o.get_json()
    assert "Insufficient wallet balance" in data["error"]


def test_order_creation_success_and_idempotency(client, app, signup):
    # 1. Establish session & upload payment screenshot to get balance
    headers = signup(client)
    csrf_tok = headers["X-CSRF-Token"]
    headers = {"X-CSRF-Token": csrf_tok}

    res_p = client.post("/api/payments", json={"amount_ghs": 100.00, "network": "Telecel"}, headers=headers)
    p_id = res_p.get_json()["payment_id"]

    img_bytes = create_dummy_image_bytes("PNG")
    client.post(f"/api/payments/{p_id}/screenshot", data={"file": (img_bytes, "receipt.png")}, content_type="multipart/form-data", headers=headers)

    # Enable platform TikTok & service 1 for testing
    with app.app_context():
        plat = Platform.query.filter_by(name="TikTok").first()
        if plat:
            plat.active = True
        srv = db.session.get(Service, 1)
        if srv:
            srv.enabled = True
        db.session.commit()

    # 2. Place Order with Idempotency Key
    idempotency_key = "test-idem-key-123"
    res_o = client.post("/api/orders", json={
        "service_id": 1,
        "target": "https://tiktok.com/@testuser",
        "quantity": 1000
    }, headers={"X-CSRF-Token": csrf_tok, "Idempotency-Key": idempotency_key})

    assert res_o.status_code == 201
    o_data = res_o.get_json()["order"]
    assert o_data["status"] == "Processing"
    assert o_data["public_order_id"].startswith("BX-ORD-")
    ord_id = o_data["public_order_id"]

    # 3. Repeat Request with SAME Idempotency Key returns SAME order
    res_o2 = client.post("/api/orders", json={
        "service_id": 1,
        "target": "https://tiktok.com/@testuser",
        "quantity": 1000
    }, headers={"X-CSRF-Token": csrf_tok, "Idempotency-Key": idempotency_key})

    assert res_o2.status_code == 201
    assert res_o2.get_json()["order"]["public_order_id"] == ord_id

    # 4. Check Wallet Balance updated
    res_w = client.get("/api/account/wallet", headers=headers)
    assert res_w.status_code == 200
    w_data = res_w.get_json()
    assert float(w_data["available_balance"]) < 100.00
    assert float(w_data["total_spent"]) > 0.00


def test_order_cancel_and_refund(client, app, signup):
    headers = signup(client)
    csrf_tok = headers["X-CSRF-Token"]
    headers = {"X-CSRF-Token": csrf_tok}

    res_p = client.post("/api/payments", json={"amount_ghs": 100.00, "network": "Telecel"}, headers=headers)
    p_id = res_p.get_json()["payment_id"]
    img_bytes = create_dummy_image_bytes("PNG")
    client.post(f"/api/payments/{p_id}/screenshot", data={"file": (img_bytes, "receipt.png")}, content_type="multipart/form-data", headers=headers)

    with app.app_context():
        plat = Platform.query.filter_by(name="TikTok").first()
        if plat:
            plat.active = True
        srv = db.session.get(Service, 1)
        if srv:
            srv.enabled = True
        db.session.commit()

    res_o = client.post("/api/orders", json={
        "service_id": 1,
        "target": "https://tiktok.com/@testuser",
        "quantity": 1000
    }, headers=headers)
    pub_id = res_o.get_json()["order"]["public_order_id"]

    # Cancel order
    res_c = client.post(f"/api/orders/{pub_id}/cancel", headers=headers)
    assert res_c.status_code == 200
    c_data = res_c.get_json()
    assert float(c_data["refund_amount_ghs"]) > 0.00

    # Wallet should be restored to 100.00
    res_w = client.get("/api/account/wallet", headers=headers)
    assert res_w.get_json()["available_balance"] == "100.00"


def test_order_worker_partial_refund(client, app, signup):
    headers = signup(client)
    csrf_tok = headers["X-CSRF-Token"]
    headers = {"X-CSRF-Token": csrf_tok}

    res_p = client.post("/api/payments", json={"amount_ghs": 100.00, "network": "Telecel"}, headers=headers)
    p_id = res_p.get_json()["payment_id"]
    img_bytes = create_dummy_image_bytes("PNG")
    client.post(f"/api/payments/{p_id}/screenshot", data={"file": (img_bytes, "receipt.png")}, content_type="multipart/form-data", headers=headers)

    with app.app_context():
        plat = Platform.query.filter_by(name="TikTok").first()
        if plat:
            plat.active = True
        srv = db.session.get(Service, 1)
        if srv:
            srv.enabled = True
        db.session.commit()

    res_o = client.post("/api/orders", json={
        "service_id": 1,
        "target": "https://tiktok.com/@testuser",
        "quantity": 1000
    }, headers=headers)
    pub_id = res_o.get_json()["order"]["public_order_id"]

    # Simulate provider setting status to Partial (e.g., 400 remains out of 1000)
    with app.app_context():
        ord_obj = Order.query.filter_by(public_order_id=pub_id).first()
        # Mock provider status
        from backend.app.providers.factory import get_provider_client
        prov_client = get_provider_client()
        prov_client.orders[ord_obj.provider_order_id] = {
            "charge_usd": 0.50,
            "status": "Partial",
            "start_count": 500,
            "remains": 400
        }
        
        # Run worker
        result = check_pending_orders(app)
        db.session.expire_all()
        ord_updated = Order.query.filter_by(public_order_id=pub_id).first()
        assert ord_updated.status == OrderStatus.PARTIAL
        assert ord_updated.remains == 400

    # Verify wallet received partial refund credit
    res_w = client.get("/api/account/wallet", headers=headers)
    w_bal = float(res_w.get_json()["available_balance"])
    assert w_bal > 0.00  # Refund credited
