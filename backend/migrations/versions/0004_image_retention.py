"""POD image retention: when and why a POD's images were purged

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

COLS = [sa.Column("images_purged_at", sa.DateTime(timezone=True)), sa.Column("images_purge_reason", sa.String(300))]


def upgrade():
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("pods")}
    for col in COLS:
        if col.name not in have:
            op.add_column("pods", col)


def downgrade():
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("pods")}
    with op.batch_alter_table("pods", naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}) as b:
        for col in COLS:
            if col.name in have:
                b.drop_column(col.name)
