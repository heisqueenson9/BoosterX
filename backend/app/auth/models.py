"""
Validation helpers for account registration and login.

The persisted account model lives in backend/app/models/user.py. This module
only holds the input-validation rules shared by the auth service and routes.
"""

from __future__ import annotations

import re
from typing import Optional

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
E164_RE = re.compile(r"^\+\d{8,15}$")
MAX_NAME_LENGTH = 120
MAX_PASSWORD_LENGTH = 128


def validate_password_policy(raw_password: str) -> Optional[str]:
    """Returns an error message, or None if the password is acceptable."""
    if not isinstance(raw_password, str) or not raw_password:
        return "Password is required."
    if len(raw_password) < 8:
        return "Password must be at least 8 characters."
    if len(raw_password) > MAX_PASSWORD_LENGTH:
        return f"Password must be at most {MAX_PASSWORD_LENGTH} characters."
    if raw_password.isdigit() or raw_password.isalpha():
        return "Password must mix letters and numbers."
    return None


def validate_identifier(email: Optional[str], phone: Optional[str]) -> Optional[str]:
    """At least one of email/phone is required; email, if given, must look valid."""
    if not email and not phone:
        return "An email or phone number is required."
    if email and not EMAIL_RE.match(email):
        return "That doesn't look like a valid email address."
    if phone and not E164_RE.match(phone):
        return "That doesn't look like a valid phone number."
    return None


def validate_full_name(full_name: Optional[str]) -> Optional[str]:
    name = (full_name or "").strip()
    if len(name) < 2:
        return "Please enter your full name."
    if len(name) > MAX_NAME_LENGTH:
        return f"Name must be at most {MAX_NAME_LENGTH} characters."
    return None
