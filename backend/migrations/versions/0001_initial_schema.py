"""Initial RouteProof schema

Revision ID: 0001
Revises:

The baseline migration materialises the declarative schema (UUID keys, JSONB on PostgreSQL, NUMERIC money columns,
FK / unique / check constraints and indexes) as it stands at this revision. Subsequent schema changes should be
added as normal incremental revisions (`alembic revision --autogenerate`).
"""
from alembic import op

import app.models  # noqa: F401
from app.core.db import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(bind=op.get_bind())


def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())
