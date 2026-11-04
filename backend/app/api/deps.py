import uuid

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import AppError, Forbidden, NotFound
from app.core.security import decode_token
from app.models import Trip, User

DRIVER = "driver"
BILLING = "billing_executive"


def current_user(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError(401, "unauthenticated", "Authentication required")
    payload = decode_token(authorization[7:].strip())
    if not payload:
        raise AppError(401, "invalid_token", "Invalid or expired token")
    try:
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (ValueError, KeyError):
        user = None
    if not user or not user.is_active:
        raise AppError(401, "invalid_token", "Invalid or expired token")
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
