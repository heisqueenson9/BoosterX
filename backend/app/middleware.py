import os
import sys
import secrets
from functools import wraps
from flask import request, jsonify, session, current_app, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from backend.app.auth.session import get_current_user
from backend.app.models.user import UserRole

# API endpoints reachable without a session. Everything else under /api/ is
# authenticated by require_authentication() (deny by default), so a new route
# is protected even if its author forgets to check the user.
PUBLIC_API_ENDPOINTS = {"auth.login", "auth.register", "auth.me", "auth.logout"}
# Pre-auth state-changing endpoints: no authenticated session exists yet to
# forge actions against, and a first-time visitor has no CSRF token.
CSRF_EXEMPT_PATHS = {"/api/auth/login", "/api/auth/register"}

# "memory://" storage keeps a separate counter per worker process, so under
# gunicorn --workers 4 a "5 per minute" limit is actually ~20/minute, and
# every counter resets on each deploy/restart. Redis (already a hard
# dependency for RQ) gives one shared counter across all workers/dynos.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://") if ("pytest" in sys.modules or os.getenv("TESTING") == "true" or "REDIS_URL" not in os.environ) else os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)


def get_csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def validate_csrf():
    """Validate CSRF token header on state-changing requests."""
    if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
        if request.path in CSRF_EXEMPT_PATHS or not request.path.startswith("/api/"):
            return None
        # No signed-in session means nothing to forge; the authentication guards
        # answer these with 401 so the UI can send the user to the login page.
        if not session.get("user_id"):
            return None
        sent_token = request.headers.get("X-CSRF-Token") or request.headers.get("X-CSRF-TOKEN")
        expected_token = session.get("csrf_token")
        if not expected_token or not sent_token or not secrets.compare_digest(sent_token, expected_token):
            return jsonify({"error": "Invalid or missing CSRF token."}), 403
    return None


def require_authentication():
    """
    Deny-by-default guard for the customer API (registered as a before_request
    hook). Every /api/ endpoint except the PUBLIC_API_ENDPOINTS requires a valid
    session belonging to a customer account. /api/admin/* is guarded separately
    by admin_required.
    """
    path = request.path
    if request.method == "OPTIONS" or not path.startswith("/api/") or path.startswith("/api/admin"):
        return None
    if request.endpoint in PUBLIC_API_ENDPOINTS:
        return None

    user = get_current_user()
    if not user:
        return jsonify({"error": "Please sign in to continue.", "code": "auth_required"}), 401
    if user.role != UserRole.CUSTOMER:
        return jsonify({"error": "This area is only available to customer accounts.", "code": "forbidden"}), 403
    return None


def no_store_api_responses(response: Response) -> Response:
    """API responses are per-user; never let the browser or a proxy cache them."""
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def admin_required(f):
    """
    Security guard for /api/admin/*. Unauthenticated callers get 401 (so the UI
    can send them to the login page); authenticated non-admins get a generic 404
    so the existence of admin routes isn't revealed to them.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Please sign in to continue.", "code": "auth_required"}), 401
        if user.role != UserRole.ADMIN:
            return jsonify({"error": "Resource not found"}), 404
        return f(*args, **kwargs)
    return decorated_function
