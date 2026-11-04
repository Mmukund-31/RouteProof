FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
# Migrate, seed (idempotent) then serve. Seeding can be skipped with SEED_ON_START=false.
CMD ["sh", "-c", "alembic upgrade head && if [ \"${SEED_ON_START:-true}\" = \"true\" ]; then python -c \"from app.core.db import SessionLocal; from app.services.seed import seed; s=SessionLocal(); print(seed(s))\"; fi && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
