"""Reliability, provenance and audit improvements

Revision ID: 0002
Revises: 0001

* trips: delivery_date_source / delivery_date_confirmed_at, billing milestone timestamps
* pods: proposed_delivery_date, location_status, processing bookkeeping, approved_exceptions
* pod_extractions: processing_id, attempt_count
* pod_reviews: approval_reason, accepted_exceptions
* pod_review_reasons: queryable (pod, reason, category) rows for the review queue, backfilled from pods.review_reasons

Revision 0001 materialises the *current* models with create_all, so on a fresh database these objects may already
exist. Every step therefore checks before it adds.
"""
import json
import uuid

import sqlalchemy as sa
from alembic import op

from app.models.entities import JSONType

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

COLUMNS = {
    "trips": [
        sa.Column("delivery_date_source", sa.String(20)),
        sa.Column("delivery_date_confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("billing_ready_at", sa.DateTime(timezone=True)),
        sa.Column("exported_at", sa.DateTime(timezone=True)),
        sa.Column("invoiced_at", sa.DateTime(timezone=True)),
    ],
    "pods": [
        sa.Column("location_status", sa.String(20)),
        sa.Column("proposed_delivery_date", sa.Date()),
        sa.Column("processing_started_at", sa.DateTime(timezone=True)),
        sa.Column("processing_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_processing_error", sa.Text()),
        sa.Column("approved_exceptions", JSONType),
    ],
    "pod_extractions": [
        sa.Column("processing_id", sa.String(36)),
        sa.Column("attempt_count", sa.Integer()),
    ],
    "pod_reviews": [
        sa.Column("approval_reason", sa.Text()),
        sa.Column("accepted_exceptions", JSONType),
    ],
}

INDEXES = [
    ("ix_pods_status_started", "pods", ["verification_status", "processing_started_at"]),
    ("ix_pods_review_priority", "pods", ["review_priority"]),
    ("ix_pod_extractions_processing_id", "pod_extractions", ["processing_id"]),
]

# Mirror of app.services.ai.validation.REASONS categories at this revision (migrations must not import app logic
# that may change later).
CATEGORY = {
    "AI_ERROR": "system", "PROCESSING_STALLED": "system",
    "LR_MISMATCH": "business", "CONSIGNEE_MISMATCH": "business", "SHORTAGE": "business", "DAMAGE": "business",
    "QUANTITY_MISMATCH": "business", "DATE_IMPLAUSIBLE": "business", "DATE_DIFFERS_FROM_TRIP": "business",
}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    for table, cols in COLUMNS.items():
        have = {c["name"] for c in insp.get_columns(table)}
        for col in cols:
            if col.name not in have:
                op.add_column(table, col)

    if not insp.has_table("pod_review_reasons"):
        op.create_table(
            "pod_review_reasons",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("pod_id", sa.Uuid(), sa.ForeignKey("pods.id", ondelete="CASCADE"), nullable=False),
            sa.Column("reason", sa.String(40), nullable=False),
            sa.Column("category", sa.String(20), nullable=False),
            sa.UniqueConstraint("pod_id", "reason", name="uq_pod_reason"),
        )
        op.create_index("ix_pod_reason_reason", "pod_review_reasons", ["reason", "pod_id"])
        op.create_index("ix_pod_reason_category", "pod_review_reasons", ["category", "pod_id"])

    insp = sa.inspect(bind)
    for name, table, cols in INDEXES:
        if name not in {i["name"] for i in insp.get_indexes(table)}:
            op.create_index(name, table, cols)

    # --- backfills ---
    reasons_t = sa.table("pod_review_reasons", sa.column("id", sa.Uuid()), sa.column("pod_id", sa.Uuid()),
                         sa.column("reason", sa.String()), sa.column("category", sa.String()))
    existing = {(str(p), r) for p, r in bind.execute(sa.text("select pod_id, reason from pod_review_reasons"))}
    rows = []
    for pod_id, raw in bind.execute(sa.text("select id, review_reasons from pods where review_reasons is not null")):
        reasons = raw if isinstance(raw, list) else json.loads(raw or "[]")
        for r in dict.fromkeys(reasons or []):
            if (str(pod_id), r) not in existing:
                rows.append({"id": uuid.uuid4(), "pod_id": pod_id if isinstance(pod_id, uuid.UUID) else uuid.UUID(str(pod_id)),
                             "reason": r, "category": CATEGORY.get(r, "document_quality")})
    if rows:
        op.bulk_insert(reasons_t, rows)

    op.execute("update pods set location_status = 'captured' where location_status is null and latitude is not null")
    op.execute("update pods set location_status = 'not_provided' where location_status is null")
    op.execute("update trips set delivery_date_source = 'import' where delivery_date_source is null and delivery_date is not null")
    # Best available history for billing milestones: verification time of the trip's verified POD.
    op.execute("""
        update trips set billing_ready_at = (
            select max(p.verified_at) from pods p where p.trip_id = trips.id and p.verification_status = 'VERIFIED')
        where billing_ready_at is null and billing_status in ('BILLING_READY', 'EXPORTED', 'INVOICED')
    """)
    op.execute("""
        update trips set exported_at = (
            select min(e.created_at) from billing_exports e join billing_export_items i on i.export_id = e.id
            where i.trip_id = trips.id)
        where exported_at is null and billing_status in ('EXPORTED', 'INVOICED')
    """)


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("pod_review_reasons"):
        op.drop_table("pod_review_reasons")
    for name, table, _ in INDEXES:
        if name in {i["name"] for i in insp.get_indexes(table)}:
            op.drop_index(name, table_name=table)
    for table, cols in COLUMNS.items():
        have = {c["name"] for c in sa.inspect(bind).get_columns(table)}
        with op.batch_alter_table(table) as b:
            for col in cols:
                if col.name in have:
                    b.drop_column(col.name)
