"""
auth_service.py — BoostX authentication.

Two kinds of account, one login endpoint:

  * Customers register through the public sign-up flow (register_customer),
    which can ONLY ever create a UserRole.CUSTOMER account, and log in with the
    password stored (hashed) in the database.

  * The administrator logs in with the credentials configured in the server
    environment (ADMIN_EMAIL / ADMIN_PASSWORD). Those credentials are compared
    server-side in constant time and are never stored in the database, sent to
    the frontend, or returned by any API. On a successful admin login a database
    row with role "admin" is provisioned (it is needed as the owner of audit-log
    entries) but its password is a random, unknown value, so that row can never
    be authenticated through the customer password path.

Failure messages are deliberately generic so the login form can't be used to
discover which emails/phones have accounts.
"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Protocol

from werkzeug.security import check_password_hash

from backend.app.models import User, UserRole, UserStatus
from .models import validate_full_name, validate_identifier, validate_password_policy

LOCKOUT_THRESHOLD = 5          # failed attempts before a temporary lock
LOCKOUT_DURATION = timedelta(minutes=15)
GENERIC_LOGIN_ERROR = "Incorrect email/phone or password."
ACCOUNT_EXISTS_ERROR = "An account with those details already exists."

# A real (but meaningless) hash, verified when no account matches so response
# time doesn't reveal whether an identifier exists.
_DUMMY_HASH = "pbkdf2:sha256:600000$dummysalt$" + "0" * 64


class AuthError(Exception):
    """Safe to show to the end user as-is."""


class UserRepository(Protocol):
    def get_by_identifier(self, identifier: str) -> Optional[User]: ...
    def get_by_id(self, user_id: int) -> Optional[User]: ...
    def save(self, user: User) -> User: ...
    def exists(self, identifier: str) -> bool: ...


@dataclass(frozen=True)
class AuthResult:
    user: User
    redirect_path: str  # decided server-side; never trust a client-supplied redirect


class AuthService:
    def __init__(self, repo: UserRepository):
        self._repo = repo

    # ------------------------------------------------------------------ #
    # Registration — customers only, always
    # ------------------------------------------------------------------ #
    def register_customer(
        self,
        *,
        email: Optional[str],
        phone: Optional[str],
        password: str,
        full_name: Optional[str],
        reserved_identifiers: Iterable[str] = (),
    ) -> User:
        name_error = validate_full_name(full_name)
        if name_error:
            raise AuthError(name_error)

        id_error = validate_identifier(email, phone)
        if id_error:
            raise AuthError(id_error)

        pw_error = validate_password_policy(password)
        if pw_error:
            raise AuthError(pw_error)

        identifier = (email or phone or "").strip().lower()
        reserved = {r.strip().lower() for r in reserved_identifiers if r}
        if identifier in reserved or self._repo.exists(identifier):
            # Same generic phrasing whether the collision is a customer or the
            # reserved admin identity.
            raise AuthError(ACCOUNT_EXISTS_ERROR)

        user = User(
            public_user_id=User.new_public_id(UserRole.CUSTOMER),
            full_name=full_name.strip(),
            email=email.strip().lower() if email else None,
            phone=phone.strip() if phone else None,
            password_hash="",
            role=UserRole.CUSTOMER,   # hardcoded; never derived from input
            status=UserStatus.ACTIVE,
        )
        user.set_password(password)
        return self._repo.save(user)

    # ------------------------------------------------------------------ #
    # Unified login — the one endpoint both roles use
    # ------------------------------------------------------------------ #
    def authenticate(
        self,
        *,
        identifier: str,
        password: str,
        admin_email: str = "",
        admin_password: str = "",
    ) -> AuthResult:
        identifier = (identifier or "").strip().lower()
        password = password or ""

        # Administrator: verified ONLY against the environment credentials.
        if admin_email and admin_password and identifier == admin_email.strip().lower():
            if not hmac.compare_digest(password.encode("utf-8"), admin_password.encode("utf-8")):
                raise AuthError(GENERIC_LOGIN_ERROR)
            admin = self._provision_admin(admin_email.strip().lower())
            return AuthResult(user=admin, redirect_path=post_login_redirect(admin.role))

        # Customer: verified against the database.
        now = datetime.now(timezone.utc)
        user = self._repo.get_by_identifier(identifier)

        # Admin rows can never log in with a database password (see module doc).
        if user is None or user.role == UserRole.ADMIN:
            check_password_hash(_DUMMY_HASH, password)
            raise AuthError(GENERIC_LOGIN_ERROR)

        if user.is_locked(now=now) or user.status != UserStatus.ACTIVE:
            raise AuthError(GENERIC_LOGIN_ERROR)

        if not user.check_password(password):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= LOCKOUT_THRESHOLD:
                user.locked_until = now + LOCKOUT_DURATION
            self._repo.save(user)
            raise AuthError(GENERIC_LOGIN_ERROR)

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        self._repo.save(user)
        return AuthResult(user=user, redirect_path=post_login_redirect(user.role))

    # ------------------------------------------------------------------ #
    def _provision_admin(self, email: str) -> User:
        """
        Ensure a database row exists for the environment admin and is an active
        administrator. The row's password is random and unknown: the real
        credential is the environment variable, checked in authenticate().
        """
        now = datetime.now(timezone.utc)
        user = self._repo.get_by_identifier(email)
        if user is None:
            user = User(
                public_user_id=User.new_public_id(UserRole.ADMIN),
                full_name="Administrator",
                email=email,
                phone=None,
                password_hash="",
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
            )
        # The environment credentials are authoritative for this identity.
        if user.role != UserRole.ADMIN or not user.password_hash:
            user.set_password(secrets.token_urlsafe(48))
        user.role = UserRole.ADMIN
        user.status = UserStatus.ACTIVE
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        return self._repo.save(user)


def post_login_redirect(role: str) -> str:
    """Destination after a successful login, decided server-side from the role."""
    return "/admin" if role == UserRole.ADMIN else "/account/orders"
