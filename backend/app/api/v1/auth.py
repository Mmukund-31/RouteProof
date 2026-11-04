from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import AppError
from app.core.ratelimit import limit
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.requests import LoginIn
from app.services.audit import audit

router = APIRouter(prefix="/auth", tags=["auth"])

# Verified against a dummy hash for unknown users so response time doesn't reveal which emails exist.
_DUMMY = hash_password("routeproof-timing-equaliser")


def user_out(u: User) -> dict:
    return {"id": str(u.id), "name": u.name, "email": u.email, "role": u.role, "preferred_language": u.preferred_language}


@router.post("/login", dependencies=[Depends(limit("login", get_settings().login_rate_limit_per_minute))])
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY)
    if not user or not ok or not user.is_active:
        audit(db, None, "user", user.id if user else "unknown", "auth.login_failed", None, None, {"email_known": bool(user)})
        db.commit()
        raise AppError(401, "invalid_credentials", "Incorrect email or password")
    token, ttl = create_access_token(str(user.id), user.role)
    audit(db, user.id, "user", user.id, "auth.login")
    db.commit()
    return {"access_token": token, "token_type": "bearer", "expires_in": ttl, "user": user_out(user)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.post("/logout")
def logout(user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Stateless JWT: the client discards the token; the server records the event.
    audit(db, user.id, "user", user.id, "auth.logout")
    db.commit()
    return {"ok": True}
