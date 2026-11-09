"""Client POD-view links, upload size policy, invoice date, driver-link revocation

Revision ID: 0003
Revises: 0002

Like 0002, every step checks first: revision 0001 runs create_all on the current models, so a fresh database may
already have these objects.
"""
import sqlalchemy as sa
from alembic import op

from app.models.entities import JSONType

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

COLUMNS = {
    "trips": [sa.Column("invoice_date", sa.Date())],
    "pods": [
        sa.Column("upload_bytes", sa.Integer()),
        sa.Column("original_bytes", sa.Integer()),
        sa.Column("upload_size_policy", sa.String(10)),
    ],
    "driver_links": [
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by", sa.Uuid(), sa.ForeignKey("users.id", name="fk_driver_links_revoked_by_users")),
    ],
}
# SQLite batch mode rebuilds tables and must be able to name every constraint it reflects (0001 left FKs unnamed).
NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table, cols in COLUMNS.items():
        have = {c["name"] for c in insp.get_columns(table)}
        for col in cols:
            if col.name not in have:
                # SQLite cannot ALTER TABLE ADD a column with a foreign key inline; batch mode rebuilds the table there.
                with op.batch_alter_table(table, naming_convention=NAMING) as b:
                    b.add_column(col)

    if not insp.has_table("client_view_links"):
        op.create_table(
            "client_view_links",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id"), nullable=False),
            sa.Column("scope_type", sa.String(15), nullable=False),
            sa.Column("trip_ids", JSONType),
            sa.Column("billing_cycle", sa.String(10)),
            sa.Column("label", sa.String(120)),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True)),
            sa.Column("revoked_by", sa.Uuid(), sa.ForeignKey("users.id")),
            sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_accessed_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.CheckConstraint("scope_type in ('trips','billing_cycle')", name="ck_client_link_scope"),
        )
        op.create_index("ix_client_view_links_client_id", "client_view_links", ["client_id"])

    op.execute("update driver_links set revoked_at = created_at where revoked = true and revoked_at is null")
    # Existing invoiced trips: the best known invoice date is the day it was recorded.
    op.execute("update trips set invoice_date = date(invoiced_at) where invoice_date is null and invoiced_at is not null")


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("client_view_links"):
        op.drop_table("client_view_links")
    for table, cols in COLUMNS.items():
        have = {c["name"] for c in sa.inspect(bind).get_columns(table)}
        with op.batch_alter_table(table, naming_convention=NAMING) as b:
            for col in cols:
                if col.name in have:
                    b.drop_column(col.name)
