import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import auth, billing, client_links, dashboard, driver, driver_links, pods, trips
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import install_handlers
from app.core.observability import configure_logging, new_request_id, request_id_var

log = logging.getLogger("routeproof.http")

# The API only ever returns JSON, images and CSV, so the strictest policy applies.
API_SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-site",
}


def _maintenance_loop(stop: threading.Event, interval: int) -> None:
    """Periodic stale-job recovery. Durable enough for one instance; the DB claim in process_pod keeps it safe to run
    on several instances at once."""
    from app.services.pods.service import recover_stale
    from app.services.retention import record_link_expiries

    while not stop.wait(interval):
        try:
            with SessionLocal() as db:
                recover_stale(db)
                record_link_expiries(db)  # audit only; nothing is deleted automatically
        except Exception:
            log.exception("maintenance.sweep_failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    stop = threading.Event()
    if s.maintenance_interval_seconds > 0 and s.app_env != "test":
        threading.Thread(target=_maintenance_loop, args=(stop, s.maintenance_interval_seconds), daemon=True,
                         name="routeproof-maintenance").start()
    yield
    stop.set()


def create_app() -> FastAPI:
    s = get_settings()
    configure_logging(s.log_level, s.log_format)
    app = FastAPI(title="RouteProof API", version="1.1.0", docs_url="/docs" if s.app_env != "production" else None, redoc_url=None,
                  lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,  # explicit origins only, never "*"
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-CSRF-Token", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = new_request_id(request.headers.get("x-request-id"))
        token = request_id_var.set(rid)
        t0 = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            for k, v in API_SECURITY_HEADERS.items():
                response.headers.setdefault(k, v)
            if s.app_env == "production":
                response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
            return response
        finally:
            route = request.scope.get("route")
            # Route template, never the raw path: driver-link URLs carry a secret token.
            log.info("http.request", extra={
                "method": request.method, "route": getattr(route, "path", "unmatched"), "status": status,
                "duration_ms": int((time.perf_counter() - t0) * 1000), "user_id": getattr(request.state, "user_id", None)})
            request_id_var.reset(token)

    install_handlers(app)

    api = APIRouter(prefix="/api/v1")
    for m in (auth, trips, pods, driver, driver_links, billing, dashboard, client_links):
        api.include_router(m.router)
    api.include_router(client_links.public)
    app.include_router(api)

    @app.get("/health", tags=["ops"])
    def health():
        try:
            with SessionLocal() as db:
                db.execute(text("select 1"))
            db_ok = True
        except Exception:
            db_ok = False
        return {"status": "ok" if db_ok else "degraded", "database": db_ok, "ai_provider": s.ai_provider, "env": s.app_env}

    return app


app = create_app()
