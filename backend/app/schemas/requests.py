import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)
    # "cookie": browser session in an HttpOnly cookie (token never returned). "token": bearer token for API clients.
    mode: Literal["cookie", "token"] = "token"


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["APPROVE", "REJECT", "RETAKE"]
    corrections: dict[str, str | float | int | bool | None] | None = None
    correction_reason: str | None = Field(None, max_length=1000)
    rejection_reason: str | None = Field(None, max_length=1000)
    # Required when approving a POD that carries a business exception (shortage / damage / quantity mismatch).
    approval_reason: str | None = Field(None, max_length=1000)


class DriverLinkIn(BaseModel):
    trip_id: uuid.UUID
    phone: str | None = Field(None, max_length=20)
    expires_in_minutes: int | None = Field(None, ge=5, le=60 * 24 * 7)


class SyncIn(BaseModel):
    keys: list[str] = Field(max_length=200)


class ExportIn(BaseModel):
    trip_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    billing_period: str | None = Field(None, max_length=20)
    filters: dict | None = None
    reexport: bool = False
    reexport_reason: str | None = Field(None, max_length=500)


class InvoicedIn(BaseModel):
    invoice_reference: str = Field(min_length=1, max_length=60)
