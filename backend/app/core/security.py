import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_ph = PasswordHasher()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(user_id: str, role: str, *, jti: str | None = None, auth_time: int | None = None) -> tuple[str, int]:
    """Short-lived token. `auth_time` (original login) and `jti` survive sliding refreshes, so the session's absolute
    lifetime and its CSRF token stay fixed while the idle expiry moves forward."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=s.access_token_expire_minutes)
    token = jwt.encode(
        {"sub": user_id, "role": role, "exp": exp, "iat": int(now.timestamp()),
         "auth_time": auth_time or int(now.timestamp()), "jti": jti or secrets.token_hex(16)},
        s.jwt_secret_key,
        algorithm="HS256",
    )
    return token, s.access_token_expire_minutes * 60


def decode_token(token: str) -> dict | None:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    auth_time = payload.get("auth_time")
    if auth_time and datetime.now(timezone.utc).timestamp() - auth_time > s.session_max_hours * 3600:
        return None  # absolute session lifetime exceeded, however recently it was refreshed
    return payload


def csrf_token_for(jti: str) -> str:
    """Session-bound CSRF token (signed double-submit): only a page that can read our cookie can present it."""
    return hmac.new(get_settings().jwt_secret_key.encode(), f"csrf:{jti}".encode(), hashlib.sha256).hexdigest()


def csrf_matches(jti: str, presented: str | None) -> bool:
    return bool(presented) and hmac.compare_digest(csrf_token_for(jti), presented)


def new_link_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
