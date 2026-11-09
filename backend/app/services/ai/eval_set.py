"""Labelled POD evaluation set: what is printed on each document, what the trip record says, and how RouteProof must
route it. Used two ways:

1. Routing regression (always, in CI): feed the *correct* reading of each case to the deterministic validator and
   assert the expected decision. This pins down the business rules independently of any model.
2. Extraction evaluation (opt-in, real model): render each case, run the provider, and score field extraction
   accuracy separately from the final auto-verification outcome. The headline safety number is
   `false_auto_verified`: documents the system auto-verified although a person should have seen them.

Synthetic documents are a floor, not proof of real-world accuracy. The same report format accepts a manifest of real,
consented, anonymised photos (see load_manifest), which is what should drive any threshold decision. Never lower the
confidence threshold just to raise the auto-verification rate: billing needs reliable evidence.
"""
import io
import json
import math
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.services.ai.base import AIProvider, AIProviderError, TripContext
from app.services.ai.schema import PodExtractionResult
from app.services.ai.validation import Expected, evaluate, lr_core, name_similarity, normalize_unit

TODAY = date(2026, 11, 10)  # fixed so routing expectations are reproducible
DAY = TODAY - timedelta(days=1)

# Variation dimensions the set must cover (asserted by tests).
REQUIRED_TAGS = {
    "printed_lr", "handwritten_lr", "lr_format", "lang_hi", "lang_mr", "lang_en", "faint_stamp", "partial_stamp",
    "stamp_position", "missing_stamp", "qty_format", "shortage", "remark_position", "damage", "handwritten_note",
    "folded", "tilted", "shadowed", "blurred", "missing_date", "late_upload",
}


@dataclass
class Printed:
    """What is physically on the document (the ground truth a perfect reader returns)."""
    lr: str
    consignee: str
    qty: float | None
    unit: str | None
    date: date | None
    signature: bool = True
    stamp: str = "clear"  # clear | faint | partial | none
    stamp_pos: str = "bottom_right"  # bottom_right | top_left | middle
    remark: str | None = None
    remark_pos: str = "remarks_box"  # remarks_box | margin | across_stamp
    shortage: bool = False
    damage: bool = False
    labels: str = "en"  # en | hi | mr  (language of the printed field labels)
    handwritten: tuple[str, ...] = ()  # fields written by hand: lr, qty, remark, date
    photo: tuple[str, ...] = ()  # folded | tilted | shadowed | blurred


@dataclass
class TripSide:
    lr: str = "LR-66141"
    consignee: str = "Indore Warehouse"
    delivery_date: date | None = DAY
    expected_qty: Decimal | None = Decimal(100)
    unit: str | None = "cartons"


@dataclass
class EvalCase:
    id: str
    description: str
    tags: tuple[str, ...]
    printed: Printed
    trip: TripSide = field(default_factory=TripSide)
    expected_decision: str = "VERIFIED"
    expected_reasons: tuple[str, ...] = ()  # must all be present (others may be too)
    readable: bool = True  # a careful human could read it

    def expected(self) -> Expected:
        t = self.trip
        return Expected(t.lr, t.consignee, t.delivery_date, t.expected_qty, t.unit)


def _p(**kw) -> Printed:
    base = dict(lr="LR-66141", consignee="Indore Warehouse", qty=100, unit="cartons", date=DAY)
    base.update(kw)
    return Printed(**base)


CASES: list[EvalCase] = [
    EvalCase("printed_clean", "Clear printed LR, signed and stamped", ("printed_lr", "lang_en"), _p()),
    EvalCase("handwritten_lr", "LR number filled in by hand", ("handwritten_lr",), _p(handwritten=("lr",))),
    EvalCase("lr_label_no", "LR printed as 'LR No. 66141'", ("lr_format",), _p(lr="LR No. 66141")),
    EvalCase("lr_bare_number", "Only the number '66141' in the LR box", ("lr_format",), _p(lr="66141")),
    EvalCase("lr_series_format", "Series format 'LR/2026/66141' is not assumed to be the same LR",
             ("lr_format",), _p(lr="LR/2026/66141"), expected_decision="NEEDS_REVIEW", expected_reasons=("LR_MISMATCH",)),
    EvalCase("labels_hindi", "Field labels printed in Hindi, values in English", ("lang_hi",), _p(labels="hi")),
    EvalCase("consignee_marathi", "Consignee written in Marathi; trip record is English (no transliteration)",
             ("lang_mr",), _p(labels="mr", consignee="इंदूर वेअरहाऊस"),
             expected_decision="NEEDS_REVIEW", expected_reasons=("CONSIGNEE_MISMATCH",)),
    EvalCase("consignee_hindi_both", "Consignee in Devanagari on both the document and the trip record",
             ("lang_hi",), _p(labels="hi", consignee="इंदौर गोदाम"), TripSide(consignee="इंदौर गोदाम")),
    EvalCase("stamp_faint", "Consignee stamp faint but visible", ("faint_stamp",), _p(stamp="faint")),
    EvalCase("stamp_partial", "Stamp partly covered by a fold/thumb", ("partial_stamp",), _p(stamp="partial")),
    EvalCase("stamp_top_left", "Stamp in the top-left corner instead of the signature area", ("stamp_position",), _p(stamp_pos="top_left")),
    EvalCase("stamp_missing", "Signed, no consignee stamp", ("missing_stamp",), _p(stamp="none"),
             expected_decision="RETAKE_REQUESTED", expected_reasons=("STAMP_NOT_VISIBLE",)),
    EvalCase("qty_600_bags", "'600 bags'", ("qty_format",), _p(qty=600, unit="bags"), TripSide(expected_qty=Decimal(600), unit="bags")),
    EvalCase("qty_600_BAG", "'600 BAG' (singular, upper case)", ("qty_format",), _p(qty=600, unit="BAG"),
             TripSide(expected_qty=Decimal(600), unit="bags")),
    EvalCase("qty_6_MT_vs_bags", "'6 MT' on a trip booked in bags: different unit, a person must reconcile",
             ("qty_format",), _p(qty=6, unit="MT"), TripSide(expected_qty=Decimal(600), unit="bags"),
             expected_decision="NEEDS_REVIEW", expected_reasons=("QUANTITY_MISMATCH",)),
    EvalCase("qty_6_MT_vs_tonnes", "'6 MT' on a trip booked as 6 tonnes", ("qty_format",), _p(qty=6, unit="MT"),
             TripSide(expected_qty=Decimal(6), unit="tonnes")),
    EvalCase("qty_600_cartons", "'600 cartons'", ("qty_format",), _p(qty=600, unit="cartons"), TripSide(expected_qty=Decimal(600))),
    EvalCase("qty_no_expected", "Quantity printed; trip has no expected quantity (reading still validated)",
             ("qty_format",), _p(qty=40, unit="coils"), TripSide(expected_qty=None, unit=None)),
    EvalCase("shortage_remarks_box", "'Short by 6 cartons' in the remarks box, 94 delivered", ("shortage",),
             _p(qty=94, remark="Short by 6 cartons", shortage=True), expected_decision="NEEDS_REVIEW",
             expected_reasons=("SHORTAGE", "QUANTITY_MISMATCH")),
    EvalCase("shortage_margin", "Shortage scribbled in the margin", ("shortage", "remark_position", "handwritten_note"),
             _p(qty=94, remark="6 ctn short", shortage=True, remark_pos="margin", handwritten=("remark",)),
             expected_decision="NEEDS_REVIEW", expected_reasons=("SHORTAGE",)),
    EvalCase("shortage_across_stamp", "Shortage written across the stamp", ("shortage", "remark_position"),
             _p(qty=94, remark="SHORT 6", shortage=True, remark_pos="across_stamp"), expected_decision="NEEDS_REVIEW",
             expected_reasons=("SHORTAGE",)),
    EvalCase("damage_handwritten", "Handwritten damage note", ("damage", "handwritten_note"),
             _p(remark="2 cartons damaged", damage=True, handwritten=("remark",)), expected_decision="NEEDS_REVIEW",
             expected_reasons=("DAMAGE",)),
    EvalCase("note_good_condition", "Handwritten 'received in good condition' is not an exception", ("handwritten_note",),
             _p(remark="Received in good condition", handwritten=("remark",))),
    EvalCase("photo_folded", "Folded document", ("folded",), _p(photo=("folded",))),
    EvalCase("photo_tilted", "Photo taken at an angle", ("tilted",), _p(photo=("tilted",))),
    EvalCase("photo_shadowed", "Hand/phone shadow across the page", ("shadowed",), _p(photo=("shadowed",))),
    EvalCase("photo_blurred", "Motion-blurred photo, not readable", ("blurred",), _p(photo=("blurred",)),
             expected_decision="RETAKE_REQUESTED", expected_reasons=("UNREADABLE",), readable=False),
    EvalCase("date_missing", "No delivery date anywhere on the document", ("missing_date",), _p(date=None),
             expected_decision="RETAKE_REQUESTED", expected_reasons=("MISSING_FIELD",)),
    EvalCase("late_upload", "Delivered 5 days ago, uploaded today: the document date counts, not the upload date",
             ("late_upload",), _p(date=TODAY - timedelta(days=5)), TripSide(delivery_date=TODAY - timedelta(days=5))),
    EvalCase("late_upload_no_trip_date", "Uploaded days later; trip has no delivery date yet", ("late_upload",),
             _p(date=TODAY - timedelta(days=4)), TripSide(delivery_date=None)),
    EvalCase("date_differs", "Document date one day before the trip record: a person confirms which is right",
             ("late_upload",), _p(date=DAY - timedelta(days=1)), expected_decision="NEEDS_REVIEW",
             expected_reasons=("DATE_DIFFERS_FROM_TRIP",)),
]


# ---------- the correct reading of each case ----------

def oracle_extraction(case: EvalCase, confidence: float = 0.95) -> PodExtractionResult:
    """What a perfect reader returns for this document."""
    p = case.printed
    if not case.readable:
        return PodExtractionResult.model_validate({
            "lr_number": {"value": None, "confidence": 0.0}, "consignee": {"value": None, "confidence": 0.0},
            "delivered_quantity": {"value": None, "unit": None, "confidence": 0.0}, "delivery_date": {"value": None, "confidence": 0.0},
            "signature_visible": None, "stamp_visible": None, "shortage_detected": None, "damage_detected": None, "remarks": None,
            "document_readable": False, "observations": ["too blurred to read"]})
    return PodExtractionResult.model_validate({
        "lr_number": {"value": p.lr, "confidence": confidence},
        "consignee": {"value": p.consignee, "confidence": confidence},
        "delivered_quantity": {"value": p.qty, "unit": p.unit, "confidence": confidence if p.qty is not None else 0.0},
        "delivery_date": {"value": p.date.isoformat() if p.date else None, "confidence": confidence if p.date else 0.0},
        "signature_visible": p.signature, "stamp_visible": p.stamp != "none",
        "shortage_detected": p.shortage, "damage_detected": p.damage, "remarks": p.remark,
        "document_readable": True, "observations": [],
    })


def route(case: EvalCase, res: PodExtractionResult | None, *, threshold: float = 0.85, error: str | None = None,
          today: date = TODAY):
    return evaluate(res, case.expected(), threshold=threshold, retakes_used=0, max_retakes=2, today=today, error=error)


# ---------- rendering ----------

_FONT_CANDIDATES = {
    "latin": ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"],
    "deva": ["Nirmala.ttc", "NirmalaUI.ttf", "mangal.ttf", "NotoSansDevanagari-Regular.ttf", "Lohit-Devanagari.ttf"],
    "hand": ["Inkfree.ttf", "LHANDW.TTF", "segoepr.ttf", "ComicNeue-Regular.ttf"],
}
_FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts",
              Path("/System/Library/Fonts"), Path("/Library/Fonts")]
_font_cache: dict = {}

LABELS = {
    "en": ["LR No.", "Consignee", "Delivered Qty", "Delivery Date", "Remarks", "Receiver signature"],
    "hi": ["एलआर नं.", "प्राप्तकर्ता", "मात्रा", "डिलीवरी तिथि", "टिप्पणी", "हस्ताक्षर"],
    "mr": ["एलआर क्र.", "मालघेणारा", "नग", "डिलिव्हरी तारीख", "शेरा", "सही"],
}


def _find_font(kind: str) -> Path | None:
    for name in _FONT_CANDIDATES[kind]:
        for d in _FONT_DIRS:
            if d.exists():
                hit = next(iter(d.rglob(name)), None) if d != Path("C:/Windows/Fonts") else (d / name if (d / name).exists() else None)
                if hit:
                    return hit
    return None


def font(kind: str, size: int):
    key = (kind, size)
    if key not in _font_cache:
        path = _find_font(kind)
        _font_cache[key] = ImageFont.truetype(str(path), size) if path else ImageFont.load_default(size=size)
    return _font_cache[key]


def rendering_notes() -> list[str]:
    """Honest caveats about how faithful the synthetic rendering is on this machine."""
    from PIL import features

    notes = []
    if not _find_font("deva"):
        notes.append("No Devanagari font found: Hindi/Marathi text renders as boxes")
    elif not features.check("raqm"):
        notes.append("Pillow has no complex-script shaping (raqm): Devanagari vowel signs/conjuncts are approximate")
    if not _find_font("hand"):
        notes.append("No handwriting font found: handwritten fields use a jittered print font")
    return notes


def _is_deva(s: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" for ch in s)


def _write(d: ImageDraw.ImageDraw, xy, text: str, size: int, *, hand: bool, rnd: random.Random, fill=(10, 10, 60)):
    if hand:
        x, y = xy
        f = font("hand" if not _is_deva(text) else "deva", size + 4)
        for ch in text:  # per-character jitter imitates handwriting
            d.text((x, y + rnd.randint(-3, 3)), ch, font=f, fill=(20, 30, 140))
            x += d.textlength(ch, font=f) + rnd.randint(-1, 2)
    else:
        d.text(xy, text, font=font("deva" if _is_deva(text) else "latin", size), fill=fill)


def _stamp(im: Image.Image, case: EvalCase, rnd: random.Random):
    p = case.printed
    if p.stamp == "none":
        return
    W, H = im.size
    cx, cy = {"bottom_right": (W - 230, H - 270), "top_left": (200, 200), "middle": (W // 2, H // 2)}[p.stamp_pos]
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    alpha = 70 if p.stamp == "faint" else 220
    col = (160, 20, 60, alpha)
    d.ellipse([cx - 120, cy - 120, cx + 120, cy + 120], outline=col, width=6)
    d.ellipse([cx - 100, cy - 100, cx + 100, cy + 100], outline=col, width=2)
    name = case.printed.consignee[:20]
    d.text((cx, cy - 40), name.upper() if not _is_deva(name) else name, font=font("deva" if _is_deva(name) else "latin", 22), fill=col, anchor="mm")
    d.text((cx, cy + 5), "RECEIVED", font=font("latin", 32), fill=col, anchor="mm")
    if p.date:
        d.text((cx, cy + 50), p.date.strftime("%d/%m/%Y"), font=font("latin", 22), fill=col, anchor="mm")
    layer = layer.rotate(rnd.uniform(-20, 20), center=(cx, cy))
    im.alpha_composite(layer)
    if p.stamp == "partial":  # a fold/thumb hides part of the stamp
        ImageDraw.Draw(im).rectangle([cx - 10, cy - 130, cx + 140, cy + 20], fill=(222, 214, 200, 255))


def _photo_effects(im: Image.Image, effects: tuple[str, ...], rnd: random.Random) -> Image.Image:
    im = im.convert("RGB")
    if "folded" in effects:
        d = ImageDraw.Draw(im)
        y = im.height // 2 + rnd.randint(-40, 40)
        d.line([0, y, im.width, y + rnd.randint(-15, 15)], fill=(150, 150, 140), width=4)
        lower = im.crop((0, y, im.width, im.height)).point(lambda v: int(v * 0.86))
        im.paste(lower, (0, y))
    if "shadowed" in effects:
        mask = Image.linear_gradient("L").rotate(rnd.choice([90, 135, 180]), expand=False).resize(im.size)
        dark = im.point(lambda v: int(v * 0.45))
        im = Image.composite(dark, im, mask.point(lambda v: int(v * 0.8)))
    if "tilted" in effects:
        im = im.rotate(rnd.choice([-9, 8, 11]), expand=True, fillcolor=(90, 80, 70))
    if "blurred" in effects:
        im = im.filter(ImageFilter.GaussianBlur(18))
    return im


def render_case(case: EvalCase, seed: int = 1) -> bytes:
    p = case.printed
    rnd = random.Random(f"{case.id}:{seed}")
    W, H = 1000, 1300
    im = Image.new("RGBA", (W, H), (250, 248, 240, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, W - 20, H - 20], outline=(40, 40, 40), width=3)
    d.text((W // 2, 70), "SAMPLE TRANSPORT CO. (FICTIONAL)", font=font("latin", 32), fill=(24, 59, 54), anchor="mm")
    d.text((W // 2, 120), "LORRY RECEIPT / PROOF OF DELIVERY", font=font("latin", 36), fill=(20, 20, 20), anchor="mm")
    d.line([40, 160, W - 40, 160], fill=(40, 40, 40), width=2)
    lab = LABELS[p.labels]
    qty_text = "" if p.qty is None else f"{p.qty:g} {p.unit or ''}".strip()
    rows = [(lab[0], p.lr, "lr"), (lab[1], p.consignee, "consignee"), (lab[2], qty_text, "qty"),
            (lab[3], p.date.strftime("%d/%m/%Y") if p.date else "", "date")]
    y = 220
    for k, v, key in rows:
        d.text((70, y), k + ":", font=font("deva" if _is_deva(k) else "latin", 32), fill=(70, 70, 70))
        if v:
            _write(d, (380, y), v, 38, hand=key in p.handwritten, rnd=rnd)
        d.line([380, y + 52, W - 70, y + 52], fill=(160, 160, 160), width=1)
        y += 95
    d.text((70, y + 10), lab[4] + ":", font=font("deva" if _is_deva(lab[4]) else "latin", 32), fill=(70, 70, 70))
    if p.remark and p.remark_pos == "remarks_box":
        _write(d, (380, y + 10), p.remark, 36, hand="remark" in p.handwritten, rnd=rnd)
    if p.signature:
        sy = 1050
        d.text((70, sy - 70), lab[5] + ":", font=font("deva" if _is_deva(lab[5]) else "latin", 28), fill=(70, 70, 70))
        pts = [(120 + i * 8, sy + 22 * math.sin(i / 2.2) + rnd.randint(-6, 6)) for i in range(32)]
        d.line(pts, fill=(15, 15, 120), width=4)
    _stamp(im, case, rnd)
    if p.remark and p.remark_pos == "margin":
        layer = Image.new("RGBA", (700, 80), (0, 0, 0, 0))
        _write(ImageDraw.Draw(layer), (0, 10), p.remark, 40, hand=True, rnd=rnd)
        im.alpha_composite(layer.rotate(90, expand=True), (W - 110, 300))
    if p.remark and p.remark_pos == "across_stamp":
        _write(ImageDraw.Draw(im), (W - 380, H - 300), p.remark, 44, hand=True, rnd=rnd)
    out = _photo_effects(im, p.photo, rnd).resize((800, 1040))
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=72, optimize=True)
    return buf.getvalue()


# ---------- scoring ----------

CRITICAL = ("lr_number", "consignee", "delivered_quantity", "delivery_date")
FIELDS = ("lr_number", "consignee", "delivered_quantity", "delivery_date", "stamp_visible", "signature_visible",
          "shortage_detected", "damage_detected")


def field_correct(case: EvalCase, res: PodExtractionResult) -> dict[str, bool]:
    """Per-field extraction correctness against what is printed (independent of routing)."""
    p = case.printed
    if not case.readable:  # the right answer for an unreadable photo is "I can't read it"
        return {"document_readable": res.document_readable is False}
    q = res.delivered_quantity
    return {
        "lr_number": lr_core(res.lr_number.value) == lr_core(p.lr),
        "consignee": name_similarity(res.consignee.value, p.consignee) >= 0.9,
        "delivered_quantity": (q.value is None and p.qty is None) or (
            q.value is not None and p.qty is not None and abs(q.value - p.qty) < 1e-9 and normalize_unit(q.unit) == normalize_unit(p.unit)),
        "delivery_date": res.delivery_date.value == (p.date.isoformat() if p.date else None),
        "stamp_visible": res.stamp_visible is (p.stamp != "none"),
        "signature_visible": res.signature_visible is p.signature,
        "shortage_detected": bool(res.shortage_detected) is p.shortage,
        "damage_detected": bool(res.damage_detected) is p.damage,
    }


@dataclass
class CaseResult:
    id: str
    tags: list[str]
    expected_decision: str
    decision: str
    reasons: list[str]
    routing_ok: bool
    fields: dict[str, bool]
    provider_error: str | None = None


def summarise(results: list[CaseResult]) -> dict:
    n = len(results)
    per_field: dict[str, list[bool]] = {}
    for r in results:
        for k, v in r.fields.items():
            per_field.setdefault(k, []).append(v)
    auto = [r for r in results if r.decision == "VERIFIED"]
    should_auto = [r for r in results if r.expected_decision == "VERIFIED"]
    return {
        "cases": n,
        # 1. How well fields are read (model quality).
        "field_accuracy": {k: round(sum(v) / len(v), 3) for k, v in per_field.items()},
        # 2. What the system then did with them (product outcome). Kept separate on purpose.
        "routing_agreement": round(sum(r.routing_ok for r in results) / n, 3) if n else None,
        "auto_verification_rate": round(len(auto) / n, 3) if n else None,
        "expected_auto_verification_rate": round(len(should_auto) / n, 3) if n else None,
        "false_auto_verified": [r.id for r in auto if r.expected_decision != "VERIFIED"],  # wrong routing: must be empty
        # Auto-verified although a critical field was misread (e.g. a wrong quantity with nothing to compare it to).
        # Routing looks right, the billing evidence is not: this must be empty too.
        "auto_verified_with_misread_fields": [r.id for r in auto if not all(r.fields.get(f, True) for f in CRITICAL)],
        "missed_auto_verified": [r.id for r in should_auto if r.decision != "VERIFIED"],  # cost: extra human work
        "provider_errors": [r.id for r in results if r.provider_error],
    }


def run(provider: AIProvider, cases: list[EvalCase] | None = None, *, threshold: float = 0.85,
        images: dict[str, bytes] | None = None, today: date = TODAY) -> dict:
    """Synthetic cases are dated around TODAY; pass today=date.today() for a manifest of real photos."""
    results = []
    for c in cases or CASES:
        img = (images or {}).get(c.id) or render_case(c)
        ctx = TripContext(f"EVAL-{c.id}", c.trip.lr, c.trip.consignee, "Evaluation Client")
        res, err = None, None
        try:
            res = provider.analyze_pod(img, "image/jpeg", ctx)
        except AIProviderError as e:
            err = f"{e.kind}: {e}"
        dec = route(c, res, threshold=threshold, error=err, today=today)
        results.append(CaseResult(c.id, list(c.tags), c.expected_decision, dec.decision, dec.reasons,
                                  dec.decision == c.expected_decision and set(c.expected_reasons) <= set(dec.reasons),
                                  field_correct(c, res) if res else {}, err))
    return {"summary": summarise(results), "results": [asdict(r) for r in results], "rendering_notes": rendering_notes()}


# ---------- real photos ----------

def load_manifest(path: Path) -> tuple[list[EvalCase], dict[str, bytes]]:
    """Real labelled photos. `path` is a JSON list next to the images:

    [{"id": "pod-001", "image": "pod-001.jpg", "expected_decision": "NEEDS_REVIEW", "expected_reasons": ["SHORTAGE"],
      "tags": ["handwritten_lr", "shortage"], "readable": true,
      "printed": {"lr": "LR-66141", "consignee": "...", "qty": 94, "unit": "cartons", "date": "2026-11-03",
                  "stamp": "clear", "signature": true, "shortage": true, "damage": false, "remark": "Short by 6"},
      "trip": {"lr": "LR-66141", "consignee": "...", "delivery_date": "2026-11-03", "expected_qty": 100, "unit": "cartons"}}]
    """
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    cases, images = [], {}
    for r in rows:
        pr, tr = dict(r["printed"]), dict(r.get("trip", {}))
        pr["date"] = date.fromisoformat(pr["date"]) if pr.get("date") else None
        if "delivery_date" in tr:
            tr["delivery_date"] = date.fromisoformat(tr["delivery_date"]) if tr["delivery_date"] else None
        if tr.get("expected_qty") is not None:
            tr["expected_qty"] = Decimal(str(tr["expected_qty"]))
        cases.append(EvalCase(r["id"], r.get("description", ""), tuple(r.get("tags", [])), Printed(**pr), TripSide(**tr),
                              r["expected_decision"], tuple(r.get("expected_reasons", [])), r.get("readable", True)))
        images[r["id"]] = (Path(path).parent / r["image"]).read_bytes()
    return cases, images
