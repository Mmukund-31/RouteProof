import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.db import Base

# JSONB on PostgreSQL, generic JSON elsewhere (SQLite is used for fast unit tests only).
JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; PostgreSQL returns aware ones. Normalise to UTC-aware."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def ts() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role in ('driver','billing_executive')", name="ck_users_role"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(30))
    phone: Mapped[str | None] = mapped_column(String(20))
    preferred_language: Mapped[str] = mapped_column(String(5), default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = ts()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    company_name: Mapped[str] = mapped_column(String(160))
    client_code: Mapped[str] = mapped_column(String(20), unique=True)
    billing_contact_email: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = ts()


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (CheckConstraint("ownership_type in ('owned','hired')", name="ck_vehicle_ownership"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    registration_number: Mapped[str] = mapped_column(String(20), unique=True)
    vehicle_type: Mapped[str] = mapped_column(String(40))
    ownership_type: Mapped[str] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint("freight_amount >= 0", name="ck_trip_freight"),
        CheckConstraint("trip_status in ('IN_TRANSIT','DELIVERED','POD_PENDING','POD_VERIFIED','CANCELLED')", name="ck_trip_status"),
        CheckConstraint("billing_status in ('NOT_READY','BILLING_READY','EXPORTED','INVOICED')", name="ck_billing_status"),
        Index("ix_trips_status", "trip_status", "billing_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    trip_reference: Mapped[str] = mapped_column(String(30), unique=True)
    lr_number: Mapped[str] = mapped_column(String(40), unique=True)
    eway_bill_number: Mapped[str] = mapped_column(String(20), index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"), index=True)
    driver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    origin: Mapped[str] = mapped_column(String(80))
    destination: Mapped[str] = mapped_column(String(80))
    branch: Mapped[str | None] = mapped_column(String(60))
    commodity: Mapped[str | None] = mapped_column(String(60))
    consignee_name: Mapped[str | None] = mapped_column(String(160))
    expected_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    quantity_unit: Mapped[str | None] = mapped_column(String(20))
    freight_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # Operational delivery date. Set from the TMS/CSV import, or confirmed from a *verified* POD
    # (see delivery_date_source). It is never inferred from the date a photo happened to be uploaded.
    delivery_date: Mapped[date | None] = mapped_column(Date, index=True)
    delivery_date_source: Mapped[str | None] = mapped_column(String(20))  # import | pod_ai | pod_human
    delivery_date_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    billing_cycle: Mapped[str | None] = mapped_column(String(10), index=True)  # e.g. 2026-11-H1
    trip_status: Mapped[str] = mapped_column(String(20), default="IN_TRANSIT")
    billing_status: Mapped[str] = mapped_column(String(20), default="NOT_READY")
    invoice_reference: Mapped[str | None] = mapped_column(String(60))
    # Billing milestone timestamps (set by billing_transition) so dashboard turnaround metrics share one clock.
    billing_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invoiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # when the invoice was *recorded* here
    invoice_date: Mapped[date | None] = mapped_column(Date)  # the invoice date as issued in the accounting system
    created_at: Mapped[datetime] = ts()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    client: Mapped[Client] = relationship(lazy="joined")
    vehicle: Mapped[Vehicle] = relationship(lazy="joined")
    driver: Mapped[User | None] = relationship(lazy="joined")
    pods: Mapped[list["Pod"]] = relationship(back_populates="trip", order_by="Pod.attempt_number")


class Pod(Base):
    __tablename__ = "pods"
    __table_args__ = (
        UniqueConstraint("trip_id", "attempt_number", name="uq_pod_attempt"),
        CheckConstraint(
            "verification_status in ('PENDING','UPLOADED','AI_PROCESSING','NEEDS_REVIEW','RETAKE_REQUESTED','VERIFIED','REJECTED')",
            name="ck_pod_verification",
        ),
        CheckConstraint("upload_status in ('PENDING','UPLOADED','FAILED')", name="ck_pod_upload"),
        CheckConstraint("retake_count >= 0 and retake_count <= 2", name="ck_pod_retake"),
        Index("ix_pods_status_started", "verification_status", "processing_started_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    original_image_path: Mapped[str | None] = mapped_column(String(300))
    uploaded_image_path: Mapped[str | None] = mapped_column(String(300))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # client clock: unverified
    server_received_at: Mapped[datetime] = ts()
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    location_accuracy: Mapped[float | None] = mapped_column()
    # captured | permission_denied | unavailable | timeout | unsupported | not_provided
    location_status: Mapped[str | None] = mapped_column(String(20))
    upload_bytes: Mapped[int | None] = mapped_column(Integer)  # size of the compressed upload as received
    original_bytes: Mapped[int | None] = mapped_column(Integer)  # size of the full-resolution original, once attached
    upload_size_policy: Mapped[str | None] = mapped_column(String(10))  # OK | OVERSIZE (compressed upload >= limit)
    upload_status: Mapped[str] = mapped_column(String(15), default="UPLOADED")
    verification_status: Mapped[str] = mapped_column(String(20), default="UPLOADED", index=True)
    verification_method: Mapped[str | None] = mapped_column(String(10))  # ai | human
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_reasons: Mapped[list | None] = mapped_column(JSONType)
    review_priority: Mapped[str | None] = mapped_column(String(10), index=True)
    source: Mapped[str] = mapped_column(String(15), default="driver_app")  # driver_app | sms_link | staff
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    retake_count: Mapped[int] = mapped_column(Integer, default=0)
    # Delivery date read from the document. A proposal only: it reaches the trip after verification.
    proposed_delivery_date: Mapped[date | None] = mapped_column(Date)
    # AI processing bookkeeping (stale-job detection, retry visibility).
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_processing_error: Mapped[str | None] = mapped_column(Text)
    # Business exceptions (SHORTAGE, DAMAGE, ...) a reviewer explicitly accepted. Empty/None = no exception.
    approved_exceptions: Mapped[list | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = ts()

    trip: Mapped[Trip] = relationship(back_populates="pods", lazy="joined")
    extractions: Mapped[list["PodExtraction"]] = relationship(order_by="PodExtraction.created_at", lazy="select")
    reviews: Mapped[list["PodReview"]] = relationship(order_by="PodReview.reviewed_at", lazy="select")
    reason_rows: Mapped[list["PodReviewReason"]] = relationship(cascade="all, delete-orphan", lazy="select")

    @validates("review_reasons")
    def _sync_reason_rows(self, _key, value):
        """Keep the queryable pod_review_reasons rows in step with the review_reasons JSON list."""
        from app.services.ai.validation import reason_category

        self.reason_rows = [PodReviewReason(reason=r, category=reason_category(r)) for r in dict.fromkeys(value or [])]
        return value

    @property
    def has_approved_exception(self) -> bool:
        return bool(self.approved_exceptions)


class PodReviewReason(Base):
    """One row per (pod, reason) so the review queue can filter by reason/category in SQL."""

    __tablename__ = "pod_review_reasons"
    __table_args__ = (
        UniqueConstraint("pod_id", "reason", name="uq_pod_reason"),
        Index("ix_pod_reason_reason", "reason", "pod_id"),
        Index("ix_pod_reason_category", "category", "pod_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    pod_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pods.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(20))  # system | document_quality | business


class PodExtraction(Base):
    __tablename__ = "pod_extractions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    pod_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pods.id"), index=True)
    extracted_data: Mapped[dict | None] = mapped_column(JSONType)
    confidence_data: Mapped[dict | None] = mapped_column(JSONType)
    validation_data: Mapped[dict | None] = mapped_column(JSONType)
    model_provider: Mapped[str] = mapped_column(String(30))
    model_identifier: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(20))
    schema_version: Mapped[str] = mapped_column(String(20))
    processing_status: Mapped[str] = mapped_column(String(15))  # SUCCEEDED | FAILED
    processing_error: Mapped[str | None] = mapped_column(Text)
    processing_duration_ms: Mapped[int | None] = mapped_column(Integer)
    processing_id: Mapped[str | None] = mapped_column(String(36), index=True)  # correlates logs for one processing run
    attempt_count: Mapped[int | None] = mapped_column(Integer)  # provider calls made in this run (retries included)
    created_at: Mapped[datetime] = ts()


class PodReview(Base):
    __tablename__ = "pod_reviews"
    __table_args__ = (CheckConstraint("decision in ('APPROVED','REJECTED','RETAKE_REQUESTED')", name="ck_review_decision"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    pod_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pods.id"), index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    original_values: Mapped[dict | None] = mapped_column(JSONType)
    corrected_values: Mapped[dict | None] = mapped_column(JSONType)
    correction_reason: Mapped[str | None] = mapped_column(Text)
    # Why the reviewer approved despite a business exception (shortage/damage/quantity), and which ones.
    approval_reason: Mapped[str | None] = mapped_column(Text)
    accepted_exceptions: Mapped[list | None] = mapped_column(JSONType)
    decision: Mapped[str] = mapped_column(String(20))
    reviewed_at: Mapped[datetime] = ts()


class UploadJob(Base):
    __tablename__ = "upload_jobs"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_upload_idem"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    pod_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pods.id"), index=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id"))
    idempotency_key: Mapped[str] = mapped_column(String(80))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    upload_status: Mapped[str] = mapped_column(String(15), default="UPLOADED")
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = ts()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DriverLink(Base):
    __tablename__ = "driver_links"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    phone_masked: Mapped[str | None] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = ts()


class ClientViewLink(Base):
    """Read-only link a client uses to see delivery evidence for its own trips.

    Deliberately a separate table and URL space from DriverLink: a driver link may *write* one POD for one trip, a
    client link may only *read* verified PODs for one client's trips. A token for one can never resolve as the other.
    """

    __tablename__ = "client_view_links"
    __table_args__ = (CheckConstraint("scope_type in ('trips','billing_cycle')", name="ck_client_link_scope"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    scope_type: Mapped[str] = mapped_column(String(15))  # trips | billing_cycle
    trip_ids: Mapped[list | None] = mapped_column(JSONType)  # scope_type=trips: explicit list of trip UUID strings
    billing_cycle: Mapped[str | None] = mapped_column(String(10))  # scope_type=billing_cycle
    label: Mapped[str | None] = mapped_column(String(120))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = ts()

    client: Mapped[Client] = relationship(lazy="joined")


class SmsLog(Base):
    """Development delivery log for the mock SMS provider. Nothing is actually sent."""

    __tablename__ = "sms_delivery_log"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    link_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("driver_links.id"))
    to_masked: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(20), default="mock")
    status: Mapped[str] = mapped_column(String(20), default="LOGGED_NOT_SENT")
    created_at: Mapped[datetime] = ts()


class BillingExport(Base):
    __tablename__ = "billing_exports"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    export_reference: Mapped[str] = mapped_column(String(30), unique=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clients.id"))
    billing_period: Mapped[str | None] = mapped_column(String(20))
    filters: Mapped[dict | None] = mapped_column(JSONType)
    trip_count: Mapped[int] = mapped_column(Integer, default=0)
    total_freight: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    is_reexport: Mapped[bool] = mapped_column(Boolean, default=False)
    reexport_reason: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = ts()

    items: Mapped[list["BillingExportItem"]] = relationship(lazy="select")
    client: Mapped[Client | None] = relationship(lazy="joined")


class BillingExportItem(Base):
    __tablename__ = "billing_export_items"
    __table_args__ = (UniqueConstraint("export_id", "trip_id", name="uq_export_trip"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    export_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("billing_exports.id"), index=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id"), index=True)
    trip_reference: Mapped[str] = mapped_column(String(30))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(60), index=True)
    previous_values: Mapped[dict | None] = mapped_column(JSONType)
    new_values: Mapped[dict | None] = mapped_column(JSONType)
    meta: Mapped[dict | None] = mapped_column("metadata", JSONType)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped[User | None] = relationship(lazy="joined")
