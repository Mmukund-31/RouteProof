FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
# Migrate, optionally seed demo data (SEED_ON_START=true; refused in production unless ALLOW_DEMO_ACCOUNTS=true), then serve.
# --no-access-log: uvicorn's access log prints full URLs, and driver/client link URLs carry access tokens. The app writes
# its own access log with route templates instead (app.main.request_context).
CMD ["sh", "-c", "alembic upgrade head && if [ \"${SEED_ON_START:-false}\" = \"true\" ]; then python -c \"from app.core.db import SessionLocal; from app.services.seed import seed; s=SessionLocal(); print(seed(s))\"; fi && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log --proxy-headers"]
