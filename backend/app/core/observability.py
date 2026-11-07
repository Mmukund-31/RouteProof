"""Structured logging with correlation IDs.

Every log record carries the current request_id (from the X-Request-ID header or generated) and, inside AI processing,
a processing_id. Fields are an explicit allow-list: callers pass IDs, statuses, durations and error kinds through
`extra=`. Names, phone numbers, emails, GPS coordinates, image bytes, tokens and raw request paths (driver-link URLs
embed a token) must never be logged.
"""
import contextvars
import json
import logging
import re
import uuid
from datetime import datetime, timezone

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
processing_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("processing_id", default=None)

_SAFE_RID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

# Only these `extra=` keys are emitted. Anything else is dropped, so a careless extra={"name": ...} cannot leak PII.
ALLOWED_FIELDS = {
    "method", "route", "status", "duration_ms", "user_id", "role", "pod_id", "trip_id", "extraction_id", "export_id",
    "processing_id", "provider", "model", "attempt", "attempts", "decision", "reasons", "categories", "error_kind",
    "from_status", "to_status", "storage_key", "orphans", "removed", "failed", "dry_run", "recovered", "requeued",
    "trips", "reexport", "count",
}


def new_request_id(incoming: str | None = None) -> str:
    return incoming if incoming and _SAFE_RID.match(incoming) else uuid.uuid4().hex


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        rid, pid = request_id_var.get(), processing_id_var.get()
        if rid:
            out["request_id"] = rid
        if pid:
            out["processing_id"] = pid
        for k, v in record.__dict__.items():
            if k in ALLOWED_FIELDS and k not in out:
                out[k] = v if isinstance(v, (int, float, bool, type(None), list)) else str(v)
        if record.exc_info:
            # Exception type and traceback only; exception messages from providers can echo document content.
            etype = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
            out["exc_type"] = etype
            out["traceback"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


class TextFormatter(logging.Formatter):
    def __init__(self):
        super().__init__("%(asctime)s %(levelname)s %(name)s [%(rid)s] %(message)s%(ctx)s")

    def format(self, record: logging.LogRecord) -> str:
        record.rid = request_id_var.get() or "-"
        ctx = {k: v for k, v in record.__dict__.items() if k in ALLOWED_FIELDS}
        if processing_id_var.get():
            ctx["processing_id"] = processing_id_var.get()
        record.ctx = (" " + " ".join(f"{k}={v}" for k, v in ctx.items())) if ctx else ""
        return super().format(record)


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    # Replace only our own handler so repeated create_app() calls (tests) don't duplicate output.
    for h in list(root.handlers):
        if getattr(h, "_routeproof", False):
            root.removeHandler(h)
    handler._routeproof = True  # type: ignore[attr-defined]
    root.addHandler(handler)
