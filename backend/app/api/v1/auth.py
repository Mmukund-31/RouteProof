from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import clear_session_cookies, current_user, set_session_cookies
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import AppError
from app.core.ratelimit import limit
from app.core.security import create_access_token, csrf_token_for, decode_token, hash_password, verify_password
from app.models import User
from app.schemas.requests import LoginIn
from app.services.audit import audit

router = APIRouter(prefix="/auth", tags=["auth"])

# Verified against a dummy hash for unknown users so response time doesn't reveal which emails exist.
_DUMMY = hash_password("routeproof-timing-equaliser")


def user_out(u: User) -> dict:
    return {"id": str(u.id), "name": u.name, "email": u.email, "role": u.role, "preferred_language": u.preferred_language}


@router.post("/login", dependencies=[Depends(limit("login", get_settings().login_rate_limit_per_minute))])
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY)
    if not user or not ok or not user.is_active:
        audit(db, None, "user", user.id if user else "unknown", "auth.login_failed", None, None, {"email_known": bool(user)})
        db.commit()
        raise AppError(401, "invalid_credentials", "Incorrect email or password")
    token, ttl = create_access_token(str(user.id), user.role)
    jti = decode_token(token)["jti"]
    audit(db, user.id, "user", user.id, "auth.login", None, None, {"mode": body.mode})
    db.commit()
    out = {"token_type": "bearer", "expires_in": ttl, "user": user_out(user)}
    if body.mode == "cookie":
        # Browser: the token only ever lives in an HttpOnly cookie, never in a JavaScript-readable response body.
        set_session_cookies(response, token, jti)
        out["csrf_token"] = csrf_token_for(jti)
    else:
        out["access_token"] = token  # API clients / tests send it as a bearer header
    return out


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.post("/logout")
def logout(response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Clears the browser session cookies. Tokens are short-lived; revoking a copied bearer token before it expires
    # would need a server-side denylist (documented limitation).
    audit(db, user.id, "user", user.id, "auth.logout")
    db.commit()
    clear_session_cookies(response)
    return {"ok": True}
