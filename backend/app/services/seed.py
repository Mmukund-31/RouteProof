"""Repeatable, idempotent demo seeding. Every name, number and document is fictional."""
import random
import zlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import AuditLog, Client, Pod, PodExtraction, PodReview, Trip, UploadJob, User, Vehicle
from app.services.ai.mock import result
from app.services.ai.schema import PROMPT_VERSION, SCHEMA_VERSION
from app.services.ai.validation import Expected, evaluate
from app.services.billing.eligibility import sync_billing_status
from app.services.billing.service import create_export
from app.services.demo_docs import render_pod
from app.services.uploads.storage import get_storage

DEMO_PASSWORD = "Demo@12345"  # public demo only: NOT for production use

CLIENTS = [("Company B (Cement)", "CMPB"), ("Company C (Steel)", "CMPC"), ("Company D (Packaged Foods)", "CMPD")]
COMMODITY = {"CMPB": ("Cement", "bags"), "CMPC": ("Steel coils", "coils"), "CMPD": ("Packaged foods", "cartons")}
DRIVERS = [("driver1@routeproof.demo", "Ramesh Jadhav", "mr", "9000000001"), ("driver2@routeproof.demo", "Sunil Pawar", "mr", "9000000002"),
           ("driver3@routeproof.demo", "Imran Shaikh", "hi", "9000000003"), ("driver4@routeproof.demo", "Deepak Yadav", "hi", "9000000004"),
           ("driver5@routeproof.demo", "Santosh Kale", "mr", "9000000005"), ("driver6@routeproof.demo", "Vijay Singh", "hi", "9000000006")]
VEHICLES = [("MH20 EL 4521", "Trailer 32ft", "owned"), ("MH20 GT 7718", "Open truck 22ft", "owned"), ("MH17 BY 3092", "Container 24ft", "hired"),
            ("MH20 AB 1101", "Trailer 32ft", "owned"), ("MH20 CD 2202", "Open truck 22ft", "owned"), ("MH20 EF 3303", "Container 24ft", "owned"),
            ("MH14 GH 4404", "Trailer 32ft", "hired"), ("MH12 JK 5505", "Open truck 22ft", "hired"), ("MH15 LM 6606", "Container 24ft", "hired"),
            ("MH20 NP 7707", "Trailer 32ft", "owned")]
DESTS = [("Nagpur", "Nagpur Cement Depot", "Nagpur"), ("Pune", "Pune Steel Yard", "Pune"), ("Indore", "Indore Warehouse", "Indore"),
         ("Mumbai", "Bhiwandi Distribution Hub", "Mumbai"), ("Hyderabad", "Hyderabad Stockyard", "Hyderabad"),
         ("Nashik", "Nashik Retail Depot", "Nashik"), ("Raipur", "Raipur Godown", "Raipur")]
BRANCHES = ["Chhatrapati Sambhajinagar", "Pune", "Nagpur"]


def _utc(d: date, hour=10) -> datetime:
    return datetime(d.year, d.month, d.day, hour, 0, tzinfo=timezone.utc)


def cycle(d: date) -> str:
    return f"{d:%Y-%m}-H{1 if d.day <= 15 else 2}"


def _get_or_create(db, model, field, value, **kw):
    obj = db.scalar(select(model).where(getattr(model, field) == value))
    if not obj:
        obj = model(**{field: value}, **kw)
        db.add(obj)
        db.flush()
    return obj


def seed(db: Session, with_demo_trips: bool = True) -> dict:
    pw_hash = None
    users = {}
    existing = {u.email: u for u in db.scalars(select(User))}
    for email, name, lang, phone, role in [("billing@routeproof.demo", "Meera Kulkarni", "en", "9000000000", "billing_executive")] + \
            [(e, n, l, p, "driver") for e, n, l, p in DRIVERS]:
        if email not in existing:
            pw_hash = pw_hash or hash_password(DEMO_PASSWORD)
            existing[email] = User(name=name, email=email, password_hash=pw_hash, role=role, phone=phone, preferred_language=lang)
            db.add(existing[email])
    db.flush()
    users = existing
    clients = {c: _get_or_create(db, Client, "client_code", c, company_name=n) for n, c in CLIENTS}
    vehicles = {r: _get_or_create(db, Vehicle, "registration_number", r, vehicle_type=t, ownership_type=o) for r, t, o in VEHICLES}
    db.commit()
    if not with_demo_trips:
        return {"users": len(users), "trips": 0}
    if db.scalar(select(Trip).where(Trip.trip_reference == "TRP-66120")):
        return {"users": len(users), "trips": db.query(Trip).count(), "skipped": "already seeded"}

    ctx = _Ctx(db, users, clients, vehicles)
    today = date.today()
    # --- the three client-provided scenarios (IDs/values preserved) ---
    ctx.trip("TRP-66120", "LR-66120", "CMPB", "MH20 EL 4521", "driver1@routeproof.demo", "Nagpur", "Nagpur Cement Depot", Decimal("38500"),
             today - timedelta(days=3), 600, "bags", state="ai_verified", branch="Nagpur", received_days_ago=2, scenario="clear_signed_stamped")
    ctx.trip("TRP-66134", "LR-66134", "CMPC", "MH20 GT 7718", "driver2@routeproof.demo", "Pune", "Pune Steel Yard", Decimal("26000"),
             today - timedelta(days=4), 40, "coils", state="retake", branch="Pune", received_days_ago=3, scenario="missing_stamp")
    ctx.trip("TRP-66141", "LR-66141", "CMPD", "MH17 BY 3092", "driver3@routeproof.demo", "Indore", "Indore Warehouse", Decimal("41200"),
             today - timedelta(days=2), 100, "cartons", state="review_shortage", branch="Chhatrapati Sambhajinagar", received_days_ago=1,
             scenario="shortage_remark")

    # --- additional fictional trips (deterministic) ---
    plan = (["in_transit"] * 4 + ["no_pod"] * 9 + ["ai_verified"] * 5 + ["human_verified"] * 2 + ["exported"] * 6 +
            ["review_damage", "review_lowconf", "review_lr", "retake", "retake_exhausted_review", "rejected", "invoiced"] + ["ai_verified"])
    rnd = random.Random(42)
    for i, state in enumerate(plan):
        code = CLIENTS[i % 3][1]
        dest, consignee, _ = DESTS[(i + (0 if code != "CMPD" else 2)) % len(DESTS)]
        veh = VEHICLES[(i + 3) % len(VEHICLES)][0]
        drv = DRIVERS[i % len(DRIVERS)][0]
        qty_unit = COMMODITY[code][1]
        qty = {"bags": 600, "coils": 40, "cartons": 120}[qty_unit]
        age = {"in_transit": 0, "no_pod": rnd.choice([1, 2, 4, 6, 9, 12, 16, 21, 27])}.get(state, rnd.randint(6, 40))
        ctx.trip(f"TRP-66{150 + i}", f"LR-66{150 + i}", code, veh, drv, dest, consignee, Decimal(rnd.randrange(18, 56) * 1000 + rnd.choice([0, 500])),
                 today - timedelta(days=age), qty, qty_unit, state=state, branch=BRANCHES[i % 3],
                 received_days_ago=max(age - rnd.randint(0, 3), 0), scenario=None, idx=i)
    db.commit()
    ctx.finish_exports()
    return {"users": len(users), "trips": db.query(Trip).count()}


class _Ctx:
    def __init__(self, db, users, clients, vehicles):
        self.db, self.users, self.clients, self.vehicles = db, users, clients, vehicles
        self.billing = users["billing@routeproof.demo"]
        self.to_export: list[Trip] = []
        self.invoiced: list[str] = []

    def _audit(self, uid, etype, eid, action, when, new=None, prev=None, meta=None):
        self.db.add(AuditLog(user_id=uid, entity_type=etype, entity_id=str(eid), action=action, previous_values=prev, new_values=new,
                             meta=meta, timestamp=when))

    def trip(self, ref, lr, code, reg, driver_email, dest, consignee, freight, delivery_date, qty, unit, *, state, branch, received_days_ago,
             scenario, idx=0):
        db = self.db
        client, veh, drv = self.clients[code], self.vehicles[reg], self.users[driver_email]
        in_transit = state == "in_transit"
        t = Trip(trip_reference=ref, lr_number=lr, eway_bill_number=f"3310{int(ref[-5:]):08d}", client_id=client.id, vehicle_id=veh.id,
                 driver_id=drv.id, origin="Chhatrapati Sambhajinagar", destination=dest, branch=branch, commodity=COMMODITY[code][0],
                 consignee_name=consignee, expected_quantity=Decimal(qty), quantity_unit=unit, freight_amount=freight,
                 delivery_date=None if in_transit else delivery_date, billing_cycle=cycle(delivery_date),
                 trip_status="IN_TRANSIT" if in_transit else "DELIVERED", billing_status="NOT_READY",
                 created_at=_utc(delivery_date - timedelta(days=3)))
        db.add(t)
        db.flush()
        self._audit(self.billing.id, "trip", t.id, "trip.imported", t.created_at, {"trip_reference": ref})
        if state in ("in_transit", "no_pod"):
            return t

        recv = _utc(date.today() - timedelta(days=received_days_ago), 11)
        if recv < _utc(delivery_date, 8):
            recv = _utc(delivery_date, 14)
        date_str = delivery_date.isoformat()
        sc = scenario or {"review_damage": "damage_remark", "review_lr": "incorrect_lr", "review_lowconf": "clear_signed_stamped",
                          "retake": "missing_stamp", "retake_exhausted_review": "missing_stamp"}.get(state, "clear_signed_stamped")
        doc = render_pod(sc, lr=lr, consignee=consignee, qty=qty if sc != "shortage_remark" else qty - 6, unit=unit,
                         date_str=delivery_date.strftime("%d/%m/%Y"), client=client.company_name, vehicle=reg, seed=zlib.crc32(ref.encode()) % 1000)

        retakes = {"retake_exhausted_review": 2}.get(state, 0)
        attempts = retakes + 1
        for a in range(1, attempts + 1):
            last = a == attempts
            pod = Pod(trip_id=t.id, attempt_number=a, retake_count=a - 1, upload_status="UPLOADED",
                      source="sms_link" if veh.ownership_type == "hired" else "driver_app", captured_at=recv - timedelta(minutes=3),
                      server_received_at=recv + timedelta(hours=a - 1), latitude=Decimal("19.876") + Decimal(str(a / 1000)),
                      longitude=Decimal("75.343"), location_accuracy=18.0, created_at=recv)
            db.add(pod)
            db.flush()
            key = f"seed-{ref}-{a}"
            path = f"pods/{t.id}/{pod.id}.jpg"
            get_storage().put(path, doc, "image/jpeg")
            pod.original_image_path = pod.uploaded_image_path = path
            db.add(UploadJob(pod_id=pod.id, trip_id=t.id, idempotency_key=key))
            self._audit(drv.id, "pod", pod.id, "pod.uploaded", pod.server_received_at, {"trip": ref, "attempt": a})
            if not last:
                pod.verification_status = "RETAKE_REQUESTED"
                pod.review_reasons, pod.review_priority = ["STAMP_NOT_VISIBLE"], "low"
                pod.retake_count = a - 1
                self._extract(pod, t, "missing_stamp", qty, unit, date_str)
                pod.retake_count = a
                self._audit(None, "pod", pod.id, "pod.retake_requested", pod.server_received_at, {"automatic": True, "retake_count": a})
                continue
            self._finalize(pod, t, state, sc, qty, unit, date_str, drv, retakes)
        t.trip_status = "POD_VERIFIED" if db.get(Pod, pod.id).verification_status == "VERIFIED" else "POD_PENDING"
        db.flush()
        if pod.verification_status == "VERIFIED":
            db.refresh(t)
            sync_billing_status(t)
            self._audit(None, "trip", t.id, "trip.billing_ready", pod.verified_at)
        if state in ("exported", "invoiced"):
            self.to_export.append(t)
        if state == "invoiced":
            self.invoiced.append(t.trip_reference)
        return t

    def _extract(self, pod, t, sc, qty, unit, date_str, conf=0.96, seed_note=False):
        s_unit = unit
        kw = dict(lr=t.lr_number, consignee=t.consignee_name, qty=qty, unit=s_unit, date=date_str, conf=conf)
        if sc == "missing_stamp":
            kw["stamp"] = False
        if sc == "shortage_remark":
            kw.update(qty=qty - 6, shortage=True, remarks="Short by 6 cartons")
        if sc == "damage_remark":
            kw.update(damage=True, remarks="2 bags damaged / torn at delivery")
        if sc == "incorrect_lr":
            kw["lr"] = "LR-" + str(int(t.lr_number.split("-")[-1]) + 17)
        if sc == "low_conf":
            kw.update(conf=0.71)
        res = result(**kw)
        dec = evaluate(res, Expected(t.lr_number, t.consignee_name, t.delivery_date, t.expected_quantity, t.quantity_unit),
                       threshold=0.85, retakes_used=pod.retake_count, max_retakes=2, today=date.today())
        self.db.add(PodExtraction(
            pod_id=pod.id, extracted_data=res.model_dump(),
            confidence_data={k: getattr(res, k).confidence for k in ("lr_number", "consignee", "delivered_quantity", "delivery_date")},
            validation_data={"checks": dec.checks, "reasons": dec.reasons, "decision": dec.decision, "priority": dec.priority,
                             "confidence_threshold": 0.85},
            model_provider="seed-data", model_identifier="synthetic-seed-record", prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION,
            processing_status="SUCCEEDED", processing_duration_ms=1800, created_at=pod.server_received_at + timedelta(seconds=9)))
        return dec

    def _finalize(self, pod, t, state, sc, qty, unit, date_str, drv, retakes):
        rb = self.billing
        sc = {"review_lowconf": "low_conf"}.get(state, sc)
        if state == "retake":
            pod.verification_status, pod.review_reasons, pod.review_priority = "RETAKE_REQUESTED", ["STAMP_NOT_VISIBLE"], "low"
            pod.retake_count = 0
            self._extract(pod, t, "missing_stamp", qty, unit, date_str)
            pod.retake_count = 1
            self._audit(None, "pod", pod.id, "pod.retake_requested", pod.server_received_at, {"automatic": True, "retake_count": 1})
            return
        pod.retake_count = retakes
        dec = self._extract(pod, t, sc, qty, unit, date_str)
        when = pod.server_received_at + timedelta(seconds=12)
        if state in ("ai_verified", "exported", "invoiced"):
            pod.verification_status, pod.verification_method, pod.verified_at = "VERIFIED", "ai", when
            self._audit(None, "pod", pod.id, "pod.verified", when, {"method": "ai"})
        elif state == "human_verified":
            pod.verification_status, pod.verification_method, pod.verified_at = "VERIFIED", "human", when + timedelta(hours=6)
            self.db.add(PodReview(pod_id=pod.id, reviewer_id=rb.id, original_values={"delivery_date": date_str}, corrected_values=None,
                                  correction_reason="Checked original image; all fields correct", decision="APPROVED", reviewed_at=pod.verified_at))
            self._audit(rb.id, "pod", pod.id, "pod.verified", pod.verified_at, {"method": "human"})
        elif state == "rejected":
            pod.verification_status, pod.rejection_reason = "REJECTED", "Document belongs to a different consignment"
            pod.review_reasons, pod.review_priority = dec.reasons or ["LR_MISMATCH"], "high"
            self.db.add(PodReview(pod_id=pod.id, reviewer_id=rb.id, original_values={}, correction_reason=pod.rejection_reason,
                                  decision="REJECTED", reviewed_at=when + timedelta(hours=5)))
            self._audit(rb.id, "pod", pod.id, "pod.rejected", when + timedelta(hours=5), {"reason": pod.rejection_reason})
        else:  # review_* and retake_exhausted_review
            pod.verification_status, pod.review_reasons, pod.review_priority = "NEEDS_REVIEW", dec.reasons, dec.priority
            self._audit(None, "pod", pod.id, "pod.ai_processed", when, {"decision": "NEEDS_REVIEW", "reasons": dec.reasons})

    def finish_exports(self):
        db = self.db
        ready = [t for t in self.to_export if t.billing_status == "BILLING_READY"]
        by_client: dict = {}
        for t in ready:
            by_client.setdefault(t.client_id, []).append(t)
        for ts in by_client.values():
            create_export(db, self.billing.id, [t.id for t in ts], reexport=False, reexport_reason=None,
                          billing_period=cycle(date.today()), filters={"seeded": True})
        # manually-recorded external invoice (RouteProof never issues invoices)
        for t in [t for t in self.to_export if t.trip_reference in self.invoiced]:
            db.refresh(t)
            if t.billing_status == "EXPORTED":
                t.billing_status, t.invoice_reference = "INVOICED", "INV-DEMO-0001"
                self._audit(self.billing.id, "trip", t.id, "trip.invoiced_recorded", datetime.now(timezone.utc),
                            {"invoice_reference": "INV-DEMO-0001"})
        db.commit()
