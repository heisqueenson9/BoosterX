import os
import pytest
from backend.app import create_app, db
from backend.app.models import User, UserRole, UserStatus, Payment, Order, Service, Platform, AdminAction, LedgerTransaction, LedgerStatus, LedgerType

@pytest.fixture
def app():
    db_path = os.path.join(os.path.dirname(__file__), "test_m6.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    app = create_app()
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SECRET_KEY": "test-secret-key-m6",
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

def test_admin_guard_for_unauthenticated(client):
    res = client.get("/api/admin/overview")
    assert res.status_code == 401

def test_admin_404_security_guard_for_customer(client, signup):
    signup(client, email="customer1@boostx.com", full_name="Customer One")

    res = client.get("/api/admin/overview")
    assert res.status_code == 404
    assert res.get_json()["error"] == "Resource not found"

def test_admin_authenticated_access_and_overview(client, admin_login):
    admin_login(client)

    res_ov = client.get("/api/admin/overview")
    assert res_ov.status_code == 200
    data = res_ov.get_json()
    assert "revenue_24h_ghs" in data
    assert "active_orders" in data
    assert "provider_balance" in data

def test_admin_payment_verification_and_rejection(client, app, admin_login):
    csrf = admin_login(client)["X-CSRF-Token"]

    # Create dummy payment in DB
    with app.app_context():
        owner = User(public_user_id="BX-USR-TESTPAY1", email="payer@example.com", password_hash="x",
                     role=UserRole.CUSTOMER, status=UserStatus.ACTIVE, full_name="Payer")
        db.session.add(owner)
        db.session.flush()
        p = Payment(
            payment_id="PAY-TEST-99",
            user_id=owner.id,
            network="Telecel",
            amount_ghs=50.00,
            status="Verifying"
        )
        db.session.add(p)
        db.session.commit()

    # Manual verify
    res_v = client.post("/api/admin/payments/PAY-TEST-99/verify", json={"reference": "MANUAL-TX-99"}, headers={"X-CSRF-Token": csrf})
    assert res_v.status_code == 200

    with app.app_context():
        p_updated = Payment.query.filter_by(payment_id="PAY-TEST-99").first()
        assert p_updated.status == "Verified"
        tx = LedgerTransaction.query.filter_by(reference="MANUAL-TX-99").first()
        assert tx is not None
        assert float(tx.amount_ghs) == 50.00
        action = AdminAction.query.filter_by(action="VERIFY_PAYMENT").first()
        assert action is not None

def test_admin_order_actions_and_service_controls(client, app, admin_login):
    csrf = admin_login(client)["X-CSRF-Token"]

    # Service update
    res_s = client.patch("/api/admin/services/1", json={"enabled": True, "min_qty": 50}, headers={"X-CSRF-Token": csrf})
    assert res_s.status_code == 200

    with app.app_context():
        srv = db.session.get(Service, 1)
        assert srv.enabled is True
        assert srv.min_qty == 50

    # Platform update
    res_p = client.patch("/api/admin/platforms/1", json={"active": True}, headers={"X-CSRF-Token": csrf})
    assert res_p.status_code == 200

    # System Health
    res_h = client.get("/api/admin/system/health")
    assert res_h.status_code == 200
    assert res_h.get_json()["status"] in ("HEALTHY", "DEGRADED")

    # Audit Logs
    res_a = client.get("/api/admin/audit-logs")
    assert res_a.status_code == 200
    assert len(res_a.get_json()["audit_logs"]) > 0

def test_admin_cannot_modify_admin_accounts_via_user_api(client, app, admin_login):
    csrf = admin_login(client)["X-CSRF-Token"]
    with app.app_context():
        admin_id = User.query.filter_by(role=UserRole.ADMIN).first().id
    res = client.patch(f"/api/admin/users/{admin_id}", json={"status": "suspended"}, headers={"X-CSRF-Token": csrf})
    assert res.status_code == 403
    with app.app_context():
        assert db.session.get(User, admin_id).status == UserStatus.ACTIVE

def test_no_endpoint_creates_admin_accounts(client, admin_login):
    csrf = admin_login(client)["X-CSRF-Token"]
    res = client.post("/api/admin/admins", json={"email": "x@y.com", "password": "Password123!"}, headers={"X-CSRF-Token": csrf})
    assert res.status_code in (404, 405)
