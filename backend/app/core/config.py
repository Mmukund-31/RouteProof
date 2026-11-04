from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"  # development | test | production
    log_level: str = "INFO"
    database_url: str = "sqlite:///./routeproof_dev.db"
    jwt_secret_key: str = ""
    access_token_expire_minutes: int = 480
    data_mode: str = "demo"  # label shown on dashboards: demo | live

    ai_provider: str = "claude"  # claude | manual | mock
    ai_api_key: str = ""
    ai_model: str = "claude-sonnet-5-5"
    ai_timeout_seconds: float = 60.0
    # Implementation assumption: a configurable policy value, not a calibrated probability.
    ai_confidence_threshold: float = 0.85
    max_retake_requests: int = 2

    storage_provider: str = "local"  # local | s3
    storage_local_dir: str = "./storage"
    storage_bucket: str = ""
    storage_endpoint: str = ""
    storage_region: str = "ap-south-1"
    storage_access_key: str = ""
    storage_secret_key: str = ""

    cors_allowed_origins: str = "http://localhost:3000"
    upload_max_size_bytes: int = 5 * 1024 * 1024
    upload_link_expiry_minutes: int = 1440
    public_app_url: str = "http://localhost:3000"
    rate_limit_enabled: bool = True
    login_rate_limit_per_minute: int = 10
    delivery_overdue_days: int = 3

    @model_validator(mode="after")
    def _check(self):
        problems = []
        if self.app_env == "production":
            if len(self.jwt_secret_key) < 32:
                problems.append("JWT_SECRET_KEY must be set (>=32 chars) in production")
            if self.ai_provider == "claude" and not self.ai_api_key:
                problems.append("AI_API_KEY is required when AI_PROVIDER=claude")
            if self.storage_provider == "s3" and not (
                self.storage_bucket and self.storage_access_key and self.storage_secret_key
            ):
                problems.append("STORAGE_BUCKET/STORAGE_ACCESS_KEY/STORAGE_SECRET_KEY required for s3 storage")
            if self.database_url.startswith("sqlite"):
                problems.append("DATABASE_URL must point to PostgreSQL in production")
        elif not self.jwt_secret_key:
            self.jwt_secret_key = "dev-only-insecure-secret-change-me-0123456789"
        if self.ai_provider not in {"claude", "manual", "mock"}:
            problems.append("AI_PROVIDER must be claude, manual or mock")
        if self.storage_provider not in {"local", "s3"}:
            problems.append("STORAGE_PROVIDER must be local or s3")
        if problems:
            raise ValueError("Invalid configuration: " + "; ".join(problems))
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
