import time
import uuid

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import AppError, Forbidden, NotFound
from app.core.security import create_access_token, csrf_matches, csrf_token_for, decode_token
from app.models import Trip, User

DRIVER = "driver"
BILLING = "billing_executive"


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "X-CSRF-Token"


def set_session_cookies(response: Response, token: str, jti: str) -> None:
    """HttpOnly session cookie (unreadable by page JavaScript) plus a readable CSRF cookie for the double-submit check."""
    s = get_settings()
    common = dict(max_age=s.access_token_expire_minutes * 60, secure=bool(s.cookie_secure), samesite=s.cookie_samesite, path="/")
    response.set_cookie(s.session_cookie_name, token, httponly=True, **common)
    response.set_cookie(s.csrf_cookie_name, csrf_token_for(jti), httponly=False, **common)


def clear_session_cookies(response: Response) -> None:
    s = get_settings()
    for name in (s.session_cookie_name, s.csrf_cookie_name):
        response.delete_cookie(name, path="/", secure=bool(s.cookie_secure), samesite=s.cookie_samesite)


def current_user(request: Request, response: Response, db: Session = Depends(get_db)) -> User:
    """Accepts a bearer token (API clients, tests) or the HttpOnly session cookie (browser).

    Cookie-authenticated state-changing requests must carry the session-bound X-CSRF-Token header. Browser sessions
    slide: once half the idle window has passed, a fresh cookie is issued (same jti and auth_time).
    """
    s = get_settings()
    authz = request.headers.get("authorization")
    via_cookie = False
    if authz and authz.lower().startswith("bearer "):
        token = authz[7:].strip()
    else:
        token = request.cookies.get(s.session_cookie_name)
        via_cookie = True
    if not token:
        raise AppError(401, "unauthenticated", "Authentication required")
    payload = decode_token(token)
    if not payload:
        raise AppError(401, "invalid_token", "Invalid or expired session")
    if via_cookie and request.method not in SAFE_METHODS and not csrf_matches(payload.get("jti", ""), request.headers.get(CSRF_HEADER)):
        raise AppError(403, "csrf_failed", "Missing or invalid CSRF token")
    try:
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (ValueError, KeyError):
        user = None
    if not user or not user.is_active:
        raise AppError(401, "invalid_token", "Invalid or expired session")
    if via_cookie and payload.get("exp", 0) - time.time() < s.access_token_expire_minutes * 30:
        fresh, _ = create_access_token(str(user.id), user.role, jti=payload["jti"], auth_time=payload.get("auth_time"))
        set_session_cookies(response, fresh, payload["jti"])
    request.state.user_id = str(user.id)
    return user


def require_roles(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise Forbidden("Your role cannot perform this action")
        return user

    return dep


require_billing = require_roles(BILLING)
require_driver = require_roles(DRIVER)


def load_trip(db: Session, trip_id: uuid.UUID, user: User) -> Trip:
    """Resource-level authorization: drivers only see trips assigned to them. 404 (not 403) to avoid leaking existence."""
    trip = db.get(Trip, trip_id)
    if not trip or (user.role == DRIVER and trip.driver_id != user.id):
        raise NotFound("Trip")
    return trip
