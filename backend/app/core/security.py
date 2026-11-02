from __future__ import annotations

import hashlib
import hmac
import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()

_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    """Argon2id hash. Plaintext passwords are never stored or logged."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


@lru_cache(maxsize=1)
def _timing_equaliser() -> str:
    """A real hash to verify when no account matches. Never used for a login."""
    return _hasher.hash("sparkx-timing-equaliser-not-a-password")


def verify_password_for_login(password: str, stored_hash: str | None) -> bool:
    """Verify a login attempt whether or not the account exists.

    Without this, an unknown email returns immediately while a known one costs a
    full Argon2 verification. That gap is an account-enumeration oracle on the
    login form, and on a tool whose whole purpose is finding people it is worth
    closing before the endpoint exists rather than after.
    """
    return verify_password(password, stored_hash if stored_hash else _timing_equaliser())


def generate_session_token() -> str:
    """Opaque, high-entropy token handed to the client as a cookie."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """Only the digest is stored, so a database leak does not yield live sessions."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def sign_value(value: str) -> str:
    """Attach an HMAC so a client-held value can be tamper-checked."""
    secret = get_settings().signing_secret or "sparkx-development-signing-secret"
    digest = hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{digest}"


def unsign_value(signed: str) -> str | None:
    """Return the original value, or None when the signature does not verify."""
    secret = get_settings().signing_secret or "sparkx-development-signing-secret"
    value, _, digest = signed.rpartition(".")
    if not value or not digest:
        return None
    expected = hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()
    return value if hmac.compare_digest(expected, digest) else None
