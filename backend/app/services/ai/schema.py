"""Strict structured-output contract for POD extraction (schema_version 1.0)."""
from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"
PROMPT_VERSION = "pod-extract-1.0"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextField(_Strict):
    value: str | None = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class QuantityField(_Strict):
    value: float | None = Field(None, ge=0)
    unit: str | None = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class DateField(_Strict):
    value: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")  # ISO date or null
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class PodExtractionResult(_Strict):
    lr_number: TextField
    consignee: TextField
    delivered_quantity: QuantityField
    delivery_date: DateField
    # Visibility only. This is NOT authentication of a signature or stamp.
    signature_visible: bool | None = None
    stamp_visible: bool | None = None
    shortage_detected: bool | None = None
    damage_detected: bool | None = None
    remarks: str | None = None
    document_readable: bool = True
    observations: list[str] = Field(default_factory=list)


EXTRACTION_TOOL = {
    "name": "record_pod_extraction",
    "description": "Record what is visibly written on the proof-of-delivery photograph. Use null when unreadable; never guess.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "lr_number", "consignee", "delivered_quantity", "delivery_date", "signature_visible", "stamp_visible",
            "shortage_detected", "damage_detected", "remarks", "document_readable", "observations",
        ],
        "properties": {
            "lr_number": {"type": "object", "additionalProperties": False, "required": ["value", "confidence"],
                          "properties": {"value": {"type": ["string", "null"]}, "confidence": {"type": "number", "minimum": 0, "maximum": 1}}},
            "consignee": {"type": "object", "additionalProperties": False, "required": ["value", "confidence"],
                          "properties": {"value": {"type": ["string", "null"]}, "confidence": {"type": "number", "minimum": 0, "maximum": 1}}},
            "delivered_quantity": {"type": "object", "additionalProperties": False, "required": ["value", "unit", "confidence"],
                                   "properties": {"value": {"type": ["number", "null"]}, "unit": {"type": ["string", "null"]},
                                                  "confidence": {"type": "number", "minimum": 0, "maximum": 1}}},
            "delivery_date": {"type": "object", "additionalProperties": False, "required": ["value", "confidence"],
                              "properties": {"value": {"type": ["string", "null"], "description": "ISO date YYYY-MM-DD"},
                                             "confidence": {"type": "number", "minimum": 0, "maximum": 1}}},
            "signature_visible": {"type": ["boolean", "null"]},
            "stamp_visible": {"type": ["boolean", "null"]},
            "shortage_detected": {"type": ["boolean", "null"]},
            "damage_detected": {"type": ["boolean", "null"]},
            "remarks": {"type": ["string", "null"], "description": "Handwritten/printed remarks about shortage, damage or other issues, verbatim"},
            "document_readable": {"type": "boolean", "description": "false if the photo is too blurred/dark/cropped to read"},
            "observations": {"type": "array", "items": {"type": "string"}},
        },
    },
}

SYSTEM_PROMPT = (
    "You read photographs of Indian lorry receipt / proof-of-delivery (POD) documents for a freight company. "
    "Extract only what is visibly present. If a field is not legible or not present, return null for its value and a low confidence. "
    "Never infer or invent values. Confidence is your own estimate of legibility/correctness between 0 and 1. "
    "signature_visible and stamp_visible mean only that a signature-like mark or a round/rectangular consignee stamp is visible; "
    "you must not judge authenticity. Set shortage_detected/damage_detected true only if the document text says so "
    "(e.g. 'short by 6', 'damaged', 'broken'). Dates must be ISO YYYY-MM-DD. Always call the record_pod_extraction tool."
)
