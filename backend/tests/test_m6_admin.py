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
        runner.invoke(args=["create-admin", "--email", "admin_test@boostx.com", "--password", "AdminPassword123!"])
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

def test_admin_404_security_guard_for_unauthenticated(client):
    res = client.get("/api/admin/overview")
    assert res.status_code == 404
    assert res.get_json()["error"] == "Resource not found"

def test_admin_404_security_guard_for_customer(client):
    # Register customer
    res_reg = client.post("/api/auth/register", json={
        "identifier": "customer1@boostx.com",
        "full_name": "Customer One",
        "phone": "+233241112222",
        "password": "Password123!"
    })
    assert res_reg.status_code == 201

    res = client.get("/api/admin/overview")
    assert res.status_code == 404
    assert res.get_json()["error"] == "Resource not found"

def test_admin_authenticated_access_and_overview(client):
    # Login as admin
    res_log = client.post("/api/auth/login", json={"identifier": "admin@boostx.com", "password": "AdminPass123!"})
    assert res_log.status_code == 200

    res_ov = client.get("/api/admin/overview")
    assert res_ov.status_code == 200
    data = res_ov.get_json()
    assert "revenue_24h_ghs" in data
    assert "active_orders" in data
    assert "provider_balance" in data

def test_admin_payment_verification_and_rejection(client, app):
    # Login as admin
    csrf = client.post("/api/auth/login", json={"identifier": "admin@boostx.com", "password": "AdminPass123!"}).get_json()["csrf_token"]

    # Create dummy payment in DB
    with app.app_context():
        p = Payment(
            payment_id="PAY-TEST-99",
            user_id=None,
            session_id="test_sess_99",
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

def test_admin_order_actions_and_service_controls(client, app):
    csrf = client.post("/api/auth/login", json={"identifier": "admin@boostx.com", "password": "AdminPass123!"}).get_json()["csrf_token"]

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
