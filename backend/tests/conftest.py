import os

# Administrator credentials come from the environment. Fixed test values are
# set BEFORE the app config is imported so every test app sees them.
os.environ["ADMIN_EMAIL"] = "admin@boostx.test"
os.environ["ADMIN_PASSWORD"] = "Test-Admin-Passw0rd-Only"

import pytest  # noqa: E402


@pytest.fixture
def signup():
    """Factory: register a customer (auto-signed-in) and return CSRF headers."""
    def _signup(client, email="customer@example.com", password="Password123!", full_name="Test Customer"):
        res = client.post("/api/auth/register", json={
            "full_name": full_name,
            "email": email,
            "password": password,
            "confirm_password": password,
        })
        assert res.status_code == 201, res.get_json()
        return {"X-CSRF-Token": res.get_json()["csrf_token"]}
    return _signup


@pytest.fixture
def admin_login():
    """Factory: sign in as the environment administrator and return CSRF headers."""
    def _login(client):
        res = client.post("/api/auth/login", json={
            "identifier": os.environ["ADMIN_EMAIL"],
            "password": os.environ["ADMIN_PASSWORD"],
        })
        assert res.status_code == 200, res.get_json()
        return {"X-CSRF-Token": res.get_json()["csrf_token"]}
    return _login
