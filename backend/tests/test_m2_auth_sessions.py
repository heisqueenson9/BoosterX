import os
import time
from datetime import timedelta

import pytest

from backend.app import create_app, db
from backend.app.config import Config, INSECURE_DEFAULT_SECRET_KEY
from backend.app.middleware import PUBLIC_API_ENDPOINTS
from backend.app.models import User, UserRole, UserStatus

ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]


@pytest.fixture
def app(tmp_path):
    db_file = tmp_path / "test_m2.db"
    app = create_app()
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file}",
        "SECRET_KEY": "test-secret-key"
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _register_payload(**overrides):
    payload = {
        "full_name": "Joseph Asare",
        "email": "joseph@example.com",
        "password": "Password123!",
        "confirm_password": "Password123!",
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #
def test_registration_creates_customer_and_signs_in(client, app):
    res = client.post("/api/auth/register", json=_register_payload())
    assert res.status_code == 201
    data = res.get_json()
    assert data["authenticated"] is True
    assert data["role"] == "customer"
    assert data["full_name"] == "Joseph Asare"
    assert data["redirect_path"] == "/account/orders"
    assert "Password123!" not in res.get_data(as_text=True)

    me = client.get("/api/auth/me").get_json()
    assert me["authenticated"] is True
    assert me["email"] == "joseph@example.com"

    with app.app_context():
        user = User.query.filter_by(email="joseph@example.com").first()
        assert user.role == UserRole.CUSTOMER
        assert user.password_hash and user.password_hash != "Password123!"


@pytest.mark.parametrize("overrides, fragment", [
    ({"full_name": ""}, "full name"),
    ({"full_name": None}, "full name"),
    ({"email": ""}, "required"),
    ({"email": "not-an-email"}, "valid email"),
    ({"password": "short1", "confirm_password": "short1"}, "at least 8"),
    ({"password": "onlyletters", "confirm_password": "onlyletters"}, "letters and numbers"),
    ({"password": "12345678", "confirm_password": "12345678"}, "letters and numbers"),
    ({"confirm_password": "Different123!"}, "do not match"),
    ({"confirm_password": None}, "do not match"),
])
def test_registration_validation(client, overrides, fragment):
    res = client.post("/api/auth/register", json=_register_payload(**overrides))
    assert res.status_code == 400
    assert fragment in res.get_json()["error"].lower()
    assert client.get("/api/auth/me").get_json()["authenticated"] is False


def test_registration_rejects_duplicate_account(client):
    assert client.post("/api/auth/register", json=_register_payload()).status_code == 201
    other = client.application.test_client()
    res = other.post("/api/auth/register", json=_register_payload(full_name="Someone Else"))
    assert res.status_code == 400
    assert "already exists" in res.get_json()["error"]


def test_registration_cannot_claim_admin_identity(client):
    res = client.post("/api/auth/register", json=_register_payload(email=ADMIN_EMAIL))
    assert res.status_code == 400
    assert "already exists" in res.get_json()["error"]


def test_registration_ignores_client_supplied_role(client, app):
    res = client.post("/api/auth/register", json=_register_payload(role="admin", is_admin=True))
    assert res.status_code == 201
    assert res.get_json()["role"] == "customer"
    assert client.get("/api/admin/overview").status_code == 404


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #
def test_login_after_logout(client, signup):
    headers = signup(client)
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me").get_json()["authenticated"] is False

    res = client.post("/api/auth/login", json={"identifier": "customer@example.com", "password": "Password123!"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["authenticated"] is True and body["role"] == "customer"
    assert body["redirect_path"] == "/account/orders"
    assert client.get("/api/account/wallet").status_code == 200


def test_login_failures_are_generic_and_do_not_authenticate(client, signup):
    signup(client)
    other = client.application.test_client()

    wrong_pw = other.post("/api/auth/login", json={"identifier": "customer@example.com", "password": "Nope12345!"})
    unknown = other.post("/api/auth/login", json={"identifier": "ghost@example.com", "password": "Nope12345!"})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.get_json()["error"] == unknown.get_json()["error"] == "Incorrect email/phone or password."
    assert other.get("/api/auth/me").get_json()["authenticated"] is False

    for payload in ({}, {"identifier": "customer@example.com"}, {"password": "x"}, {"identifier": "  ", "password": "x"}):
        res = other.post("/api/auth/login", json=payload)
        assert res.status_code == 400
        assert other.get("/api/auth/me").get_json()["authenticated"] is False

    # Non-string values must not crash the server
    assert other.post("/api/auth/login", json={"identifier": ["a"], "password": {"b": 1}}).status_code == 400


def test_account_lockout_after_repeated_failures(client, signup):
    signup(client)
    other = client.application.test_client()
    for _ in range(5):
        assert other.post("/api/auth/login", json={"identifier": "customer@example.com", "password": "Wrong12345!"}).status_code == 401
    # Even the correct password is refused while locked
    res = other.post("/api/auth/login", json={"identifier": "customer@example.com", "password": "Password123!"})
    assert res.status_code == 401


def test_suspended_user_is_signed_out_and_cannot_login(client, app, signup):
    signup(client)
    with app.app_context():
        user = User.query.filter_by(email="customer@example.com").first()
        user.status = UserStatus.SUSPENDED
        db.session.commit()
    assert client.get("/api/auth/me").get_json()["authenticated"] is False
    assert client.get("/api/account/wallet").status_code == 401
    res = client.post("/api/auth/login", json={"identifier": "customer@example.com", "password": "Password123!"})
    assert res.status_code == 401


# --------------------------------------------------------------------------- #
# No guest access / protected endpoints
# --------------------------------------------------------------------------- #
def test_guest_session_endpoint_is_gone(client, app):
    assert not any(rule.rule == "/api/session" for rule in app.url_map.iter_rules())
    res = client.post("/api/session")
    assert res.status_code in (401, 404, 405)  # never a guest session
    assert "boostx_guest" not in "".join(res.headers.getlist("Set-Cookie"))
    me = client.get("/api/auth/me")
    assert me.get_json() == {"authenticated": False}
    assert "Set-Cookie" not in me.headers  # anonymous visitors don't even get a cookie


def test_every_api_endpoint_requires_authentication_by_default(app):
    """Deny-by-default: walk every registered /api route anonymously."""
    anon = app.test_client()
    checked = 0
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/") or rule.endpoint in PUBLIC_API_ENDPOINTS:
            continue
        url = rule.build({arg: 1 for arg in rule.arguments})[1]
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            res = anon.open(url, method=method)
            assert res.status_code == 401, f"{method} {url} ({rule.endpoint}) returned {res.status_code}"
            assert res.get_json()["code"] == "auth_required"
            checked += 1
    assert checked >= 30


def test_unauthenticated_reads_never_return_data(client):
    for path in ("/api/platforms", "/api/services", "/api/account/orders", "/api/account/wallet",
                 "/api/account/transactions", "/api/notifications", "/api/payments", "/api/orders/BX-ORD-1",
                 "/api/orders/BX-ORD-1/status", "/api/admin/overview"):
        res = client.get(path)
        assert res.status_code == 401, path


def test_api_responses_are_not_cacheable(client):
    assert client.get("/api/auth/me").headers["Cache-Control"] == "no-store"


# --------------------------------------------------------------------------- #
# CSRF
# --------------------------------------------------------------------------- #
def test_csrf_is_enforced_for_signed_in_requests(client, signup):
    headers = signup(client)
    body = {"service_id": 999, "quantity": 100}
    assert client.post("/api/orders/preview", json=body).status_code == 403
    assert client.post("/api/orders/preview", json=body, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    ok = client.post("/api/orders/preview", json=body, headers=headers)
    assert ok.status_code == 404  # passed CSRF; service simply doesn't exist


def test_csrf_token_rotates_on_login(client, signup):
    first = signup(client)["X-CSRF-Token"]
    client.post("/api/auth/logout", headers={"X-CSRF-Token": first})
    res = client.post("/api/auth/login", json={"identifier": "customer@example.com", "password": "Password123!"})
    assert res.get_json()["csrf_token"] != first


# --------------------------------------------------------------------------- #
# Logout / session lifetime / revocation
# --------------------------------------------------------------------------- #
def test_logout_clears_session_and_revokes_old_cookie(client, signup):
    headers = signup(client)
    old_cookie = client.get_cookie("boostx_session").value

    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me").get_json()["authenticated"] is False
    assert client.get("/api/account/wallet").status_code == 401

    # Replaying the cookie captured before logout must not work.
    replay = client.application.test_client()
    replay.set_cookie("boostx_session", old_cookie)
    assert replay.get("/api/auth/me").get_json()["authenticated"] is False
    assert replay.get("/api/account/wallet").status_code == 401


def test_session_expires(app, signup):
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=1)
    client = app.test_client()
    signup(client)
    assert client.get("/api/account/wallet").status_code == 200
    time.sleep(2.1)
    assert client.get("/api/account/wallet").status_code == 401
    assert client.get("/api/auth/me").get_json()["authenticated"] is False


def test_session_cookie_flags(client):
    res = client.post("/api/auth/register", json=_register_payload())
    cookie = [c for c in res.headers.getlist("Set-Cookie") if c.startswith("boostx_session=")][0]
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Expires=" in cookie  # persistent, bounded lifetime


def test_change_password_revokes_other_sessions(app, signup):
    a = app.test_client()
    headers = signup(a)
    b = app.test_client()
    assert b.post("/api/auth/login", json={"identifier": "customer@example.com", "password": "Password123!"}).status_code == 200
    assert b.get("/api/account/wallet").status_code == 200

    res = a.post("/api/auth/change-password", json={"current_password": "Password123!", "new_password": "NewPassw0rd!"}, headers=headers)
    assert res.status_code == 200
    assert a.get("/api/account/wallet").status_code == 200   # the session that changed it stays signed in
    assert b.get("/api/account/wallet").status_code == 401   # every other session is revoked

    c = app.test_client()
    assert c.post("/api/auth/login", json={"identifier": "customer@example.com", "password": "Password123!"}).status_code == 401
    assert c.post("/api/auth/login", json={"identifier": "customer@example.com", "password": "NewPassw0rd!"}).status_code == 200


def test_change_password_validates_input(client, signup):
    headers = signup(client)
    bad_current = client.post("/api/auth/change-password", json={"current_password": "nope", "new_password": "NewPassw0rd!"}, headers=headers)
    assert bad_current.status_code == 400
    weak = client.post("/api/auth/change-password", json={"current_password": "Password123!", "new_password": "weak"}, headers=headers)
    assert weak.status_code == 400


# --------------------------------------------------------------------------- #
# Administrator
# --------------------------------------------------------------------------- #
def test_admin_logs_in_with_environment_credentials_only(client, app):
    # No admin account exists in the database before the first admin login.
    with app.app_context():
        assert User.query.filter_by(role=UserRole.ADMIN).count() == 0

    res = client.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert res.status_code == 200
    body = res.get_json()
    assert body["role"] == "admin"
    assert body["redirect_path"] == "/admin"
    assert ADMIN_PASSWORD not in res.get_data(as_text=True)

    me = client.get("/api/auth/me")
    assert me.get_json()["role"] == "admin"
    assert ADMIN_PASSWORD not in me.get_data(as_text=True)
    assert client.get("/api/admin/overview").status_code == 200

    with app.app_context():
        admin = User.query.filter_by(email=ADMIN_EMAIL).first()
        assert admin.role == UserRole.ADMIN
        # The credential lives in the environment, not the database.
        assert not admin.check_password(ADMIN_PASSWORD)


def test_admin_login_is_case_insensitive_on_email_and_exact_on_password(client):
    ok = client.post("/api/auth/login", json={"identifier": ADMIN_EMAIL.upper(), "password": ADMIN_PASSWORD})
    assert ok.status_code == 200
    other = client.application.test_client()
    assert other.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD + "x"}).status_code == 401
    assert other.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD.lower()}).status_code == 401
    assert other.get("/api/admin/overview").status_code == 401


def test_admin_login_disabled_when_environment_not_configured(app):
    app.config["ADMIN_EMAIL"] = ""
    app.config["ADMIN_PASSWORD"] = ""
    client = app.test_client()
    assert client.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).status_code == 401
    assert client.post("/api/auth/login", json={"identifier": "", "password": ""}).status_code == 400


def test_admin_row_cannot_log_in_with_a_database_password(app):
    """A role=admin row must only ever authenticate through the environment."""
    with app.app_context():
        user = User(public_user_id="BX-ADM-TEST0001", email="other-admin@example.com", password_hash="",
                    role=UserRole.ADMIN, status=UserStatus.ACTIVE, full_name="Other Admin")
        user.set_password("Known-Password-1")
        db.session.add(user)
        db.session.commit()
    client = app.test_client()
    res = client.post("/api/auth/login", json={"identifier": "other-admin@example.com", "password": "Known-Password-1"})
    assert res.status_code == 401


def test_customer_cannot_use_admin_api(client, signup):
    signup(client)
    res = client.get("/api/admin/overview")
    assert res.status_code == 404
    assert res.get_json()["error"] == "Resource not found"


def test_admin_cannot_use_customer_api_or_change_password(client, admin_login):
    headers = admin_login(client)
    assert client.get("/api/account/wallet").status_code == 403
    assert client.get("/api/services").status_code == 403
    assert client.post("/api/orders", json={"service_id": 1, "target": "x", "quantity": 1}, headers=headers).status_code == 403
    res = client.post("/api/auth/change-password", json={"current_password": "a", "new_password": "NewPassw0rd!"}, headers=headers)
    assert res.status_code == 403


def test_admin_logout_revokes_session(client, admin_login):
    headers = admin_login(client)
    assert client.get("/api/admin/overview").status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/admin/overview").status_code == 401
    assert client.get("/api/auth/me").get_json()["authenticated"] is False


def test_existing_customer_with_admin_email_cannot_keep_customer_access(app):
    """If a customer row already holds the admin email, env credentials win."""
    with app.app_context():
        user = User(public_user_id="BX-USR-LEGACY01", email=ADMIN_EMAIL, password_hash="", role=UserRole.CUSTOMER,
                    status=UserStatus.ACTIVE, full_name="Legacy")
        user.set_password("Customer-Password-1")
        db.session.add(user)
        db.session.commit()
    client = app.test_client()
    # Their old customer password no longer works for that identity...
    assert client.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": "Customer-Password-1"}).status_code == 401
    # ...and the environment credentials sign in as admin.
    res = client.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert res.get_json()["role"] == "admin"


# --------------------------------------------------------------------------- #
# Configuration safety
# --------------------------------------------------------------------------- #
def test_refuses_to_start_with_default_secret_key_outside_testing():
    class ProdConfig(Config):
        TESTING = False
        SECRET_KEY = INSECURE_DEFAULT_SECRET_KEY

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(ProdConfig)


def test_cors_is_disabled_by_default(client):
    res = client.get("/api/auth/me", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in res.headers


def test_update_profile_email_and_duplicate_rejection(client, app, signup):
    headers1 = signup(client, email="user1@example.com")

    client2 = app.test_client()
    headers2 = signup(client2, email="user2@example.com")

    # 1. Update user 2 email to new unique email -> 200
    res_ok = client2.patch("/api/account/profile", json={
        "email": "user2new@example.com"
    }, headers=headers2)
    assert res_ok.status_code == 200
    assert res_ok.get_json()["email"] == "user2new@example.com"

    # 2. Attempt to update user 2 email to user 1's email -> 400 (rejection with clear message, not 500)
    res_dup = client2.patch("/api/account/profile", json={
        "email": "user1@example.com"
    }, headers=headers2)
    assert res_dup.status_code == 400
    assert res_dup.get_json()["error"] == "That email is already in use"

