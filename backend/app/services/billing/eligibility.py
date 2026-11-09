from app.models import Trip
from app.services.pods.state import billing_transition


def pod_reference(trip: Trip, pod) -> str:
    """Human-readable reference for the exact POD attempt, e.g. POD-TRP-66141-A2."""
    return f"POD-{trip.trip_reference}-A{pod.attempt_number}"


def pod_image_reference(pod) -> str:
    """Stable identifier of the POD image. Not a storage path and not a URL: it is resolved only through the
    authenticated app (/pods/<id>) or a client view link, so a shared CSV never exposes the image itself."""
    return f"PODIMG-{pod.id}"


def blockers(trip: Trip) -> list[str]:
    """Reasons a trip cannot enter the billing queue. Empty list == eligible."""
    out: list[str] = []
    if trip.trip_status == "CANCELLED":
        out.append("Trip is cancelled")
    last = trip.pods[-1] if trip.pods else None
    if last is None:
        out.append("No POD uploaded")
    elif last.verification_status != "VERIFIED":
        out.append(f"POD is {last.verification_status}, not VERIFIED")
    for label, val in (("LR number", trip.lr_number), ("E-way bill number", trip.eway_bill_number),
                       ("Delivery date", trip.delivery_date), ("Client", trip.client_id)):
        if not val:
            out.append(f"{label} missing")
    if trip.freight_amount is None or trip.freight_amount <= 0:
        out.append("Freight amount missing")
    return out


def is_eligible(trip: Trip) -> bool:
    return not blockers(trip)


def sync_billing_status(trip: Trip, at=None) -> bool:
    """Promote NOT_READY -> BILLING_READY when all eligibility rules hold. Returns True if promoted."""
    if trip.billing_status == "NOT_READY" and is_eligible(trip):
        billing_transition(trip, "BILLING_READY", at=at)
        return True
    return False
