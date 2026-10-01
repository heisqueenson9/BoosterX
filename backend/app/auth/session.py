from typing import Optional
from flask import abort, jsonify, make_response, session
from backend.app.db import db
from backend.app.models import User, UserStatus


def get_current_user() -> Optional[User]:
    """
    Loads the authenticated user from the signed session cookie.

    The session is rejected (and cleared) if the account no longer exists, is
    not active, or if its session_version no longer matches the account's - the
    version is bumped on logout and password change, which invalidates every
    previously issued cookie for that account.
    """
    user_id = session.get("user_id")
    if not user_id:
        return None

    user = db.session.get(User, user_id)
    if not user or user.status != UserStatus.ACTIVE:
        session.clear()
        return None

    if session.get("session_version") != user.session_version:
        session.clear()
        return None

    return user


def require_user() -> User:
    """Returns the authenticated user or aborts with a JSON 401."""
    user = get_current_user()
    if not user:
        abort(make_response(jsonify({"error": "Please sign in to continue.", "code": "auth_required"}), 401))
    return user
