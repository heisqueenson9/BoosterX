from flask import Blueprint, jsonify, request, session, current_app
from backend.app.db import db
from backend.app.models import User, UserRole
from backend.app.auth.repository import SQLAlchemyUserRepository
from backend.app.auth.auth_service import AuthService, AuthError
from backend.app.auth.models import validate_password_policy
from backend.app.auth.session import get_current_user, require_user
from backend.app.middleware import get_csrf_token, limiter
from backend.app.utils.phone import normalize_phone

auth_bp = Blueprint("auth", __name__, url_prefix="/api")

repo = SQLAlchemyUserRepository()
auth_service = AuthService(repo)


def _user_payload(user: User, csrf_token: str) -> dict:
    return {
        "authenticated": True,
        "user_id": user.public_user_id,
        "full_name": user.full_name,
        "role": user.role,
        "email": user.email,
        "phone": user.phone,
        "csrf_token": csrf_token,
    }


def _start_session(user: User) -> str:
    """
    Establish a fresh authenticated session. The previous session contents are
    discarded (prevents session fixation) and a new CSRF token is issued.
    """
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    session["session_version"] = user.session_version
    return get_csrf_token()


@auth_bp.post("/auth/register")
@limiter.limit("5 per minute")
def register():
    data = request.get_json(silent=True) or {}
    full_name = data.get("full_name")
    password = data.get("password") or ""
    confirm_password = data.get("confirm_password")

    # An explicit "email"/"phone" field is validated as exactly that; the generic
    # "identifier" is treated as an email if it contains "@", otherwise a phone.
    email_in, phone_in, identifier = data.get("email"), data.get("phone"), data.get("identifier")
    raw_values = [v for v in (email_in, phone_in, identifier) if v not in (None, "")]
    if not raw_values:
        return jsonify({"error": "Email or phone number is required."}), 400
    if (not all(isinstance(v, str) for v in raw_values) or not isinstance(password, str)
            or not isinstance(full_name, (str, type(None)))):
        return jsonify({"error": "Invalid registration details."}), 400
    if confirm_password is None or confirm_password != password:
        return jsonify({"error": "Passwords do not match."}), 400

    email = None
    phone = None
    if email_in:
        email = email_in.strip().lower()
    elif phone_in:
        phone = normalize_phone(phone_in)
    elif "@" in identifier:
        email = identifier.strip().lower()
    else:
        phone = normalize_phone(identifier)

    try:
        user = auth_service.register_customer(
            email=email,
            phone=phone,
            password=password,
            full_name=full_name,
            reserved_identifiers=[current_app.config.get("ADMIN_EMAIL", "")],
        )
    except AuthError as exc:
        return jsonify({"error": str(exc)}), 400

    # Auto-login after registration
    csrf_tok = _start_session(user)
    body = _user_payload(user, csrf_tok)
    body["redirect_path"] = "/account/orders"
    return jsonify(body), 201


@auth_bp.post("/auth/login")
@limiter.limit("5 per minute")
def login():
    data = request.get_json(silent=True) or {}
    identifier = data.get("identifier", "")
    password = data.get("password", "")

    if not isinstance(identifier, str) or not isinstance(password, str) or not identifier.strip() or not password:
        return jsonify({"error": "Email/phone and password are required."}), 400

    try:
        result = auth_service.authenticate(
            identifier=identifier,
            password=password,
            admin_email=current_app.config.get("ADMIN_EMAIL", ""),
            admin_password=current_app.config.get("ADMIN_PASSWORD", ""),
        )
    except AuthError as exc:
        return jsonify({"error": str(exc)}), 401

    csrf_tok = _start_session(result.user)
    body = _user_payload(result.user, csrf_tok)
    body["redirect_path"] = result.redirect_path
    return jsonify(body), 200


@auth_bp.post("/auth/logout")
def logout():
    user = get_current_user()
    if user:
        # Bumping the version invalidates every cookie previously issued for
        # this account, so a copied/old session cookie stops working too.
        user.session_version += 1
        db.session.commit()
    session.clear()
    return jsonify({"message": "Signed out."}), 200


@auth_bp.get("/auth/me")
def me():
    user = get_current_user()
    if not user:
        return jsonify({"authenticated": False}), 200
    return jsonify(_user_payload(user, get_csrf_token())), 200


@auth_bp.post("/auth/change-password")
@limiter.limit("5 per minute")
def change_password():
    user = require_user()
    if user.role == UserRole.ADMIN:
        return jsonify({"error": "Administrator credentials are managed by the server configuration."}), 403

    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")
    if not isinstance(current_password, str) or not isinstance(new_password, str):
        return jsonify({"error": "Invalid password details."}), 400

    if not user.check_password(current_password):
        return jsonify({"error": "Incorrect current password."}), 400

    err = validate_password_policy(new_password)
    if err:
        return jsonify({"error": err}), 400

    user.set_password(new_password)
    user.session_version += 1  # Invalidate all other sessions
    db.session.commit()

    session["session_version"] = user.session_version
    return jsonify({"message": "Password updated successfully."}), 200
