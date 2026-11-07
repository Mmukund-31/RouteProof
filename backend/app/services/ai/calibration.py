"""Confidence-threshold calibration against labelled synthetic POD documents.

AI_CONFIDENCE_THRESHOLD (default 0.85) is a policy value, not a measured accuracy. This module measures it: render
documents whose true values we know, run the configured provider, and for each candidate threshold report

  * coverage     - share of field readings at or above the threshold (what would be auto-accepted)
  * error rate   - share of those accepted readings that were actually wrong

The recommendation is the lowest threshold whose accepted-error rate, across every critical field, stays within the
target. Results only apply to documents like the ones sampled; re-run when the model, prompt or document mix changes.
"""
import io
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from PIL import Image, ImageFilter

from app.services.ai.base import AIProvider, AIProviderError, TripContext
from app.services.ai.validation import CRITICAL_FIELDS, _norm_id, name_similarity, normalize_unit
from app.services.demo_docs import render_pod

THRESHOLDS = [round(0.50 + 0.05 * i, 2) for i in range(10)] + [0.97, 0.99]
CONSIGNEES = ["Indore Warehouse", "Nagpur Cement Depot", "Pune Steel Yard", "Bhiwandi Distribution Hub", "Raipur Godown"]
UNITS = ["cartons", "bags", "coils"]
SCENARIOS = ["clear_signed_stamped", "missing_stamp", "shortage_remark", "damage_remark", "incorrect_lr", "blurred_unreadable"]


@dataclass
class Truth:
    lr_number: str
    consignee: str
    delivered_quantity: float
    unit: str
    delivery_date: str  # ISO
    scenario: str
    degradation: str


@dataclass
class Reading:
    field: str
    confidence: float
    correct: bool
    scenario: str
    degradation: str


@dataclass
class Report:
    samples: int
    provider_errors: int
    target_error_rate: float
    per_threshold: list[dict] = field(default_factory=list)
    per_field: dict = field(default_factory=dict)
    recommended_threshold: float | None = None
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _degrade(img: bytes, kind: str, rnd: random.Random) -> bytes:
    if kind == "none":
        return img
    im = Image.open(io.BytesIO(img)).convert("RGB")
    if kind == "light_blur":
        im = im.filter(ImageFilter.GaussianBlur(1.6))
    elif kind == "low_quality":
        im = im.resize((im.width // 2, im.height // 2))
    elif kind == "rotated":
        im = im.rotate(rnd.uniform(-7, 7), expand=True, fillcolor=(230, 230, 225))
    elif kind == "dark":
        im = im.point(lambda p: int(p * 0.45))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=35 if kind == "low_quality" else 70)
    return buf.getvalue()


def make_samples(n: int, seed: int = 7) -> list[tuple[bytes, Truth]]:
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        sc = SCENARIOS[i % len(SCENARIOS)]
        deg = rnd.choice(["none", "none", "light_blur", "low_quality", "rotated", "dark"])
        lr = f"LR-{rnd.randint(10000, 99999)}"
        consignee, unit = rnd.choice(CONSIGNEES), rnd.choice(UNITS)
        qty = rnd.choice([40, 100, 120, 600])
        d = date.today() - timedelta(days=rnd.randint(0, 20))
        printed_qty = qty - 6 if sc == "shortage_remark" else qty
        img = render_pod(sc, lr=lr, consignee=consignee, qty=printed_qty, unit=unit, date_str=d.strftime("%d/%m/%Y"), seed=i)
        shown_lr = "LR-" + str(int(lr.split("-")[-1]) + 17) if sc == "incorrect_lr" else lr  # what the document says
        out.append((_degrade(img, deg, rnd), Truth(shown_lr, consignee, float(printed_qty), unit, d.isoformat(), sc, deg)))
    return out


def score(res, t: Truth) -> list[Reading]:
    """One Reading per critical field the provider returned a value for. A null value is never auto-accepted, so it is
    not a calibration data point."""
    checks = {
        "lr_number": lambda: _norm_id(res.lr_number.value) == _norm_id(t.lr_number),
        "consignee": lambda: name_similarity(res.consignee.value, t.consignee) >= 0.9,
        "delivered_quantity": lambda: (res.delivered_quantity.value == t.delivered_quantity
                                       and normalize_unit(res.delivered_quantity.unit) == normalize_unit(t.unit)),
        "delivery_date": lambda: res.delivery_date.value == t.delivery_date,
    }
    out = []
    for f in CRITICAL_FIELDS:
        fv = getattr(res, f)
        if fv.value is None:
            continue
        out.append(Reading(f, fv.confidence, bool(checks[f]()), t.scenario, t.degradation))
    return out


def summarise(readings: list[Reading], *, samples: int, provider_errors: int, target_error_rate: float = 0.01,
              min_accepted: int = 30) -> Report:
    rep = Report(samples=samples, provider_errors=provider_errors, target_error_rate=target_error_rate)
    for thr in THRESHOLDS:
        row = {"threshold": thr, "fields": {}}
        worst = 0.0
        enough = True
        for f in CRITICAL_FIELDS:
            rs = [r for r in readings if r.field == f]
            acc = [r for r in rs if r.confidence >= thr]
            wrong = sum(1 for r in acc if not r.correct)
            err = wrong / len(acc) if acc else 0.0
            row["fields"][f] = {"readings": len(rs), "accepted": len(acc), "wrong_accepted": wrong,
                                "coverage": round(len(acc) / len(rs), 3) if rs else None, "error_rate": round(err, 4)}
            worst = max(worst, err)
            enough = enough and len(acc) >= min_accepted
        row["worst_error_rate"] = round(worst, 4)
        row["meets_target"] = worst <= target_error_rate and enough
        rep.per_threshold.append(row)
    for f in CRITICAL_FIELDS:
        rs = [r for r in readings if r.field == f]
        rep.per_field[f] = {"readings": len(rs), "accuracy": round(sum(r.correct for r in rs) / len(rs), 3) if rs else None,
                            "wrong_with_conf_ge_0.85": sum(1 for r in rs if not r.correct and r.confidence >= 0.85)}
    ok = [r["threshold"] for r in rep.per_threshold if r["meets_target"]]
    rep.recommended_threshold = min(ok) if ok else None
    rep.note = ("Lowest threshold meeting the target on every critical field with at least "
                f"{min_accepted} accepted readings per field." if ok else
                "No threshold met the target with enough data; collect more samples or keep routing to human review.")
    return rep


def calibrate(provider: AIProvider, n: int = 60, *, seed: int = 7, target_error_rate: float = 0.01, min_accepted: int = 30) -> Report:
    readings: list[Reading] = []
    errors = 0
    for i, (img, truth) in enumerate(make_samples(n, seed)):
        ctx = TripContext(f"CAL-{i:04d}", truth.lr_number, truth.consignee, "Calibration Client")
        try:
            res = provider.analyze_pod(img, "image/jpeg", ctx)
        except AIProviderError:
            errors += 1
            continue
        readings.extend(score(res, truth))
    return summarise(readings, samples=n, provider_errors=errors, target_error_rate=target_error_rate, min_accepted=min_accepted)
