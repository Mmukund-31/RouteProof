import logging

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import auth, billing, dashboard, driver, driver_links, pods, trips
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import install_handlers


def create_app() -> FastAPI:
    s = get_settings()
    logging.basicConfig(level=s.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = FastAPI(title="RouteProof API", version="1.0.0", docs_url="/docs" if s.app_env != "production" else None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )
    install_handlers(app)

    api = APIRouter(prefix="/api/v1")
    for m in (auth, trips, pods, driver, driver_links, billing, dashboard):
        api.include_router(m.router)
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
