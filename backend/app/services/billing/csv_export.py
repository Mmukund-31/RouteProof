"""Tally-compatible CSV (a flat voucher-source file for manual/bulk import; NOT a live Tally integration)."""
import csv
import io

from app.models import Trip, aware
from app.services.billing.eligibility import pod_reference

COLUMNS = [
    "export_reference", "trip_reference", "lr_number", "eway_bill_number", "client_code", "client_name",
    "vehicle_registration", "destination", "delivery_date", "freight_amount_inr", "pod_reference", "pod_verified_date",
    "pod_exceptions",  # business exceptions a reviewer accepted, e.g. "SHORTAGE"; empty = clean POD
]
_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(v) -> str:
    """Neutralise spreadsheet formula injection; csv module handles quoting/escaping of commas, quotes, newlines."""
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(_DANGEROUS) else s


def _d(d) -> str:
    return d.strftime("%d-%m-%Y") if d else ""  # Tally's default import date format


def build_csv(export_reference: str, trips: list[Trip]) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    w.writerow(COLUMNS)
    for t in trips:
        pod = t.pods[-1]
        w.writerow([safe_cell(x) for x in [
            export_reference, t.trip_reference, t.lr_number, t.eway_bill_number, t.client.client_code, t.client.company_name,
            t.vehicle.registration_number, t.destination, _d(t.delivery_date), f"{t.freight_amount:.2f}",
            pod_reference(t, pod), _d(aware(pod.verified_at)), ";".join(pod.approved_exceptions or []),
        ]])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM so Excel reads UTF-8 correctly
