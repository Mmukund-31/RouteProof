"""Builds Technical_Design_Document.pdf. Run: python docs/architecture/build_tdd.py <out.pdf>

Content mirrors what is implemented in this repository. Items that were NOT verified (live AI inference, PostgreSQL run,
cloud deployment, GitHub URL) are stated as such: edit the constants below once they exist and rebuild.
"""
import sys
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

# ---- fill these in after publishing / deploying, then rebuild ----
GITHUB_URL = "NOT YET PUBLISHED - add the public repository URL here"
LIVE_URL = "NOT DEPLOYED - no live URL exists yet"
HEALTH_URL = "NOT DEPLOYED"
# -------------------------------------------------------------------

FOREST, TEAL, AMBER, CANVAS, LINE = colors.HexColor("#183B36"), colors.HexColor("#2D7768"), colors.HexColor("#D69B37"), colors.HexColor("#F3F5F2"), colors.HexColor("#DDE3DF")
ss = getSampleStyleSheet()
BODY = ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.3, leading=12.8, alignment=TA_LEFT, spaceAfter=4)
SMALL = ParagraphStyle("s", parent=BODY, fontSize=8.2, leading=11)
H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=13.5, textColor=FOREST, spaceBefore=9, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=10, textColor=TEAL, spaceBefore=5, spaceAfter=2)
CELL = ParagraphStyle("c", parent=BODY, fontSize=8.2, leading=10.6, spaceAfter=0)
CELLB = ParagraphStyle("cb", parent=CELL, fontName="Helvetica-Bold")
BUL = ParagraphStyle("bl", parent=BODY, leftIndent=10, bulletIndent=1, spaceAfter=1.5)
ASSUME = ParagraphStyle("as", parent=BODY, backColor=colors.HexColor("#FBF3E1"), borderPadding=3, leftIndent=4, rightIndent=4, spaceBefore=2, spaceAfter=5, fontSize=8.2, leading=11)


def P(t, st=BODY): return Paragraph(t, st)
def B(items): return [Paragraph(i, BUL, bulletText="•") for i in items]
def A(n, t): return Paragraph(f"<b>Assumption A{n}.</b> {t}", ASSUME)


def table(rows, widths, header=True, font=CELL):
    data = [[Paragraph(str(c), CELLB if (header and i == 0) else font) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
    if header:
        st.append(("BACKGROUND", (0, 0), (-1, 0), CANVAS))
    t.setStyle(TableStyle(st))
    return t


# ---------- diagrams ----------
def box(d, x, y, w, h, title, lines=(), fill=colors.white, stroke=FOREST, tc=FOREST):
    d.add(Rect(x, y, w, h, fillColor=fill, strokeColor=stroke, strokeWidth=0.9, rx=3, ry=3))
    d.add(String(x + w / 2, y + h - 10, title, fontName="Helvetica-Bold", fontSize=7.6, fillColor=tc, textAnchor="middle"))
    for i, l in enumerate(lines):
        d.add(String(x + w / 2, y + h - 20 - i * 8.2, l, fontName="Helvetica", fontSize=6.4, fillColor=colors.HexColor("#444444"), textAnchor="middle"))


def arrow(d, x1, y1, x2, y2, label=None, color=colors.HexColor("#555555")):
    import math
    d.add(Line(x1, y1, x2, y2, strokeColor=color, strokeWidth=0.9))
    a = math.atan2(y2 - y1, x2 - x1)
    s = 4.2
    d.add(Polygon([x2, y2, x2 - s * math.cos(a - 0.4), y2 - s * math.sin(a - 0.4), x2 - s * math.cos(a + 0.4), y2 - s * math.sin(a + 0.4)], fillColor=color, strokeColor=color))
    if label:
        d.add(String((x1 + x2) / 2, (y1 + y2) / 2 + 2.5, label, fontName="Helvetica-Oblique", fontSize=6, fillColor=color, textAnchor="middle"))


def arch_diagram():
    d = Drawing(520, 215)
    box(d, 5, 150, 120, 55, "Driver PWA (mobile)", ["Next.js, IndexedDB queue", "Canvas compression <300 KB", "Service worker, hi/mr voice"], CANVAS)
    box(d, 5, 82, 120, 55, "Billing workspace", ["Next.js, Tailwind, Recharts", "Dashboard, review, billing", "Tokens in browser storage"], CANVAS)
    box(d, 5, 14, 120, 55, "Hired-driver landing", ["/upload/{token}, no account", "Single-trip scoped token", "Same capture + queue engine"], CANVAS)
    box(d, 190, 20, 150, 185, "FastAPI modular monolith", [], colors.HexColor("#EEF5F2"), TEAL, TEAL)
    for i, (t, l) in enumerate([("api/v1 routers", "authN/Z, validation, errors"), ("services/pods", "state machine, review, retake"), ("services/ai", "provider adapter + validation"),
                                ("services/billing", "eligibility, CSV, exports"), ("services/uploads", "storage adapter, image checks"), ("repositories + models", "SQLAlchemy 2, Alembic")]):
        box(d, 198, 168 - i * 28, 134, 24, t, [l], colors.white, TEAL, FOREST)
    box(d, 405, 150, 110, 55, "Claude vision API", ["HTTPS REST, tool-use JSON", "Structured JSON + confidence", "Provider is swappable"], colors.HexColor("#FBF3E1"), AMBER)
    box(d, 405, 82, 110, 55, "PostgreSQL 16", ["UUID, JSONB, NUMERIC", "Constraints + indexes", "Append-only audit_logs"], colors.white)
    box(d, 405, 14, 110, 55, "Private object storage", ["Local disk or S3-compatible", "Never public; API-served", "Images + export CSVs"], colors.white)
    for y in (177, 109, 41):
        arrow(d, 125, y, 190, 110 if y != 177 else 150)
    arrow(d, 340, 150, 405, 177, "inference")
    arrow(d, 340, 110, 405, 109, "SQL")
    arrow(d, 340, 70, 405, 41, "put/get")
    return d


def er_diagram():
    d = Drawing(520, 280)
    T = {}
    ops = []
    def tb(key, x, y, w, name, cols):
        h = 16 + 8 * len(cols)
        T[key] = (x, y, w, h)
        ops.append((x, y, w, h, name, cols))
    tb("users", 4, 180, 100, "users", ["id uuid PK", "email UNIQUE, role CHECK", "password_hash (argon2)", "preferred_language"])
    tb("clients", 4, 118, 100, "clients", ["id uuid PK", "client_code UNIQUE", "company_name"])
    tb("vehicles", 4, 56, 100, "vehicles", ["id uuid PK", "registration UNIQUE", "ownership owned|hired"])
    tb("trips", 150, 100, 120, "trips", ["id uuid PK", "trip_reference, lr_number UNIQUE", "eway_bill_number", "client_id, vehicle_id, driver_id FK", "freight_amount NUMERIC(12,2)", "trip_status, billing_status CHECK", "billing_cycle, branch, delivery_date"])
    tb("pods", 150, 4, 120, "pods", ["id uuid PK, UNIQUE(trip,attempt)", "trip_id FK, attempt_number", "original_/uploaded_image_path", "captured_at (client), server_received_at", "latitude/longitude/accuracy", "upload_status, verification_status", "retake_count CHECK <=2"])
    tb("ext", 315, 200, 110, "pod_extractions", ["pod_id FK", "extracted_data JSONB", "confidence_data JSONB", "validation_data JSONB", "provider/model/prompt/schema", "status, error, duration_ms"])
    tb("rev", 315, 138, 110, "pod_reviews", ["pod_id FK, reviewer_id FK", "original_values JSONB", "corrected_values JSONB", "correction_reason, decision"])
    tb("job", 315, 82, 110, "upload_jobs", ["pod_id FK, trip_id FK", "idempotency_key UNIQUE", "retry_count, last_error"])
    tb("link", 315, 28, 110, "driver_links", ["token_hash UNIQUE (SHA-256)", "trip_id FK, expires_at", "revoked, use_count"])
    tb("exp", 440, 190, 76, "billing_exports", ["export_reference UQ", "filters JSONB", "file_path, is_reexport", "created_by FK"])
    tb("item", 440, 130, 76, "billing_export_items", ["export_id FK", "trip_id FK", "UNIQUE(export,trip)"])
    tb("audit", 440, 50, 76, "audit_logs", ["user_id FK", "entity_type/id", "action", "previous/new JSONB", "metadata, timestamp"])
    tb("sms", 440, 4, 76, "sms_delivery_log", ["link_id FK", "provider=mock", "LOGGED_NOT_SENT"])
    def c(k, side): x, y, w, h = T[k]; return {"l": (x, y + h / 2), "r": (x + w, y + h / 2), "t": (x + w / 2, y + h), "b": (x + w / 2, y)}[side]
    for a, sa, b, sb in [("users", "r", "trips", "l"), ("clients", "r", "trips", "l"), ("vehicles", "r", "trips", "l"), ("trips", "b", "pods", "t"), ("pods", "r", "ext", "l"),
                         ("pods", "r", "rev", "l"), ("pods", "r", "job", "l"), ("trips", "r", "link", "l"), ("exp", "b", "item", "t"), ("trips", "r", "item", "l")]:
        (x1, y1), (x2, y2) = c(a, sa), c(b, sb)
        d.add(Line(x1, y1, x2, y2, strokeColor=colors.HexColor("#9AA8A4"), strokeWidth=0.6))
    for (x, y, w, h, name, cols) in ops:  # tables drawn after the connector lines so text stays readable
        d.add(Rect(x, y, w, h, fillColor=colors.white, strokeColor=FOREST, strokeWidth=0.8))
        d.add(Rect(x, y + h - 11, w, 11, fillColor=FOREST, strokeColor=FOREST))
        d.add(String(x + 3, y + h - 8.4, name, fontName="Helvetica-Bold", fontSize=6.8, fillColor=colors.white))
        for i, c_ in enumerate(cols):
            d.add(String(x + 3, y + h - 20 - i * 8, c_, fontName="Helvetica", fontSize=5.9, fillColor=colors.HexColor("#333333")))
    d.add(String(4, 270, "Solid lines = foreign keys (1:N). 13 tables; all primary keys are UUIDs.", fontName="Helvetica-Oblique", fontSize=6.5, fillColor=colors.HexColor("#555555")))
    return d


def state_diagram():
    d = Drawing(520, 128)
    n = {}
    def node(k, x, y, label, fill=colors.white, w=70):
        d.add(Rect(x, y, w, 20, fillColor=fill, strokeColor=FOREST, strokeWidth=0.8, rx=4, ry=4))
        d.add(String(x + w / 2, y + 7, label, fontName="Helvetica-Bold", fontSize=6.6, fillColor=FOREST, textAnchor="middle"))
        n[k] = (x, y, w)
    d.add(String(4, 116, "POD verification_status (one row per attempt)", fontName="Helvetica-Bold", fontSize=7, fillColor=TEAL))
    node("up", 4, 62, "UPLOADED"); node("ai", 110, 62, "AI_PROCESSING", colors.HexColor("#E8EEF7"), 84)
    node("ver", 250, 90, "VERIFIED", colors.HexColor("#E8F3F0")); node("rev", 250, 52, "NEEDS_REVIEW", colors.HexColor("#FBF3E1"), 80)
    node("ret", 250, 14, "RETAKE_REQUESTED", colors.HexColor("#FBF3E1"), 98); node("rej", 400, 52, "REJECTED", colors.HexColor("#FBECEB"))
    node("new", 400, 14, "next attempt = new POD row", colors.white, 112)
    arrow(d, 74, 72, 110, 72)
    arrow(d, 194, 76, 250, 98); arrow(d, 194, 72, 250, 62); arrow(d, 194, 68, 250, 26)
    arrow(d, 285, 72, 285, 90, "approve"); arrow(d, 330, 62, 400, 62, "reject"); arrow(d, 285, 52, 285, 34, "retake")
    arrow(d, 348, 24, 400, 24, "driver retakes")
    return d


def state_notes():
    return [P("<b>Trip status:</b> IN_TRANSIT &gt; DELIVERED &gt; POD_PENDING &gt; POD_VERIFIED (or CANCELLED). <b>Billing status:</b> NOT_READY &gt; BILLING_READY &gt; EXPORTED &gt; INVOICED "
              "(recorded manually; invoices are issued outside RouteProof). <b>Retake cap:</b> two requests, after which the next attempt is routed to NEEDS_REVIEW. "
              "<b>Reprocess:</b> NEEDS_REVIEW &gt; AI_PROCESSING lets staff re-run the model. Every transition is validated in <font face='Courier'>services/pods/state.py</font> and audited.", SMALL)]


# ---------- document ----------
def build(out: Path):
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
                            title="RouteProof - Technical Design Document", author="RouteProof")
    W = A4[0] - 34 * mm
    s = []
    s += [P(f"<b>GitHub repository:</b> {GITHUB_URL}", ParagraphStyle("g", parent=BODY, fontSize=10, textColor=FOREST, backColor=CANVAS, borderPadding=4, spaceAfter=3)),
          P(f"<b>Live application:</b> {LIVE_URL} &nbsp;|&nbsp; <b>Backend health:</b> {HEALTH_URL}", SMALL),
          Spacer(1, 4), P("RouteProof", ParagraphStyle("t", parent=H1, fontSize=24, spaceBefore=4, spaceAfter=0)),
          P("Technical Design Document &mdash; Proof of Delivery Intelligence Platform", ParagraphStyle("st", parent=BODY, fontSize=11, textColor=TEAL, spaceAfter=6))]

    s += [P("1. Project overview", H1),
          P("RouteProof turns a physical delivery document into a verified, traceable and billing-ready digital record for a full-truckload transporter "
            "(Chhatrapati Sambhajinagar; ~2,200 trips/month). Flow: <b>trip assigned &gt; driver captures POD (offline-capable PWA) &gt; upload &gt; vision model extracts structured fields &gt; "
            "deterministic validation &gt; human review of exceptions &gt; verified POD &gt; billing queue &gt; Tally-compatible CSV</b>. The original photograph stays the source of truth; the AI "
            "never authorises an invoice and the system never issues, sends or posts one. Two roles exist: <i>driver</i> (own trips only) and <i>billing executive</i> (workspace). "
            "Seven primary screens are implemented (dashboard, trips, POD capture, AI verification, review queue, billing queue, missing-POD operations) plus login, upload queue, trip/POD detail, audit history, "
            "unauthorized/not-found pages and the hired-driver landing page."),
          P("2. GitHub and live deployment links", H1),
          P(f"GitHub: <b>{GITHUB_URL}</b>. Live frontend: <b>{LIVE_URL}</b>. Health endpoint: <b>{HEALTH_URL}</b>. "
            "The code, Dockerfile, <font face='Courier'>render.yaml</font> and step-by-step instructions are complete, but the application has <b>not</b> been deployed from the authoring environment "
            "(no hosting or GitHub credentials were available, and the brief asked for code and configuration only). No deployment claim is made."),
          P("3. Client problem and product objectives", H1),
          P("Signed lorry receipts return 10&ndash;20 days after delivery; WhatsApp photos are lost; invoices cannot be raised without POD, so working capital is locked. Client-provided figures "
            "(<b>assumptions supplied by the client, not verified by us</b>): POD-to-invoice 18 days today, 4-day target; ~Rs 3.24 crore working capital released; ~Rs 38.9 lakh annual financing benefit; "
            "~Rs 63.36 lakh/yr lost to lost or disputed PODs; ~Rs 1.02 crore total opportunity. This build instruments the pipeline (upload latency, upload-to-billing-ready time) so that such figures can later be measured; "
            "it does <b>not</b> assert any achieved improvement."),
          *B(["Capture POD at the consignee with one obvious action, even with no network.", "Extract LR, consignee, quantity, date, signature/stamp visibility and shortage/damage remarks with a vision model; never trust confidence alone.",
              "Route every doubtful case to a person with the original image beside the AI values; preserve AI originals and every attempt.",
              "Make only verified trips billable; export a documented CSV; keep a complete audit trail."])]

    s += [P("4. Explicit assumptions", H1),
          A(1, "AI confidence threshold 0.85 on critical fields (LR, consignee, date) is an implementation default, <b>not</b> a calibrated probability; it is configurable (<font face='Courier'>AI_CONFIDENCE_THRESHOLD</font>) and recorded with every extraction."),
          A(2, "When the model returns output and <i>all</i> deterministic checks pass (LR match, consignee match, plausible date, no shortage/damage, stamp and signature visible, confidences above threshold, quantity equal if an expected quantity exists), the POD is auto-verified (<i>verification_method = ai</i>) and the trip becomes billing-ready. A reviewer may prefer a mandatory human step; that is a one-line policy change."),
          A(3, "Consignee match = case/punctuation-insensitive substring or >= 0.70 sequence similarity. Date plausible = not in the future and within 7 days before to 30 days after the trip delivery date. LR compared after stripping non-alphanumerics."),
          A(4, "Trips carry an optional expected quantity + unit (added to the specified schema). Quantity is compared <i>only</i> when it exists; otherwise the check is reported as not compared."),
          A(5, "Missing stamp, missing signature, missing LR or an unreadable image request a retake (max 2); a mismatch, shortage, damage, quantity/date problem or low confidence goes to review. After 2 retakes everything goes to review."),
          A(6, "The compressed (&lt;300 KB) JPEG is the server-side evidence. The full-resolution original is kept on the device until the server acknowledges the upload; the API can also store a separate original but the PWA does not send it to spare bandwidth on basic phones."),
          A(7, "Client clocks and GPS are labelled as device-reported and are not proof; server receipt time is stored separately. Billing cycles are half-months (e.g. 2026-11-H1). A POD is 'overdue' after 3 days (configurable)."),
          A(8, "Auth uses a stateless JWT (8 h) held in browser storage for simplicity; logout is audited but cannot revoke a token before expiry. Rate limiting is an in-memory per-instance sliding window. All seeded data and demo credentials are fictional and non-production.")]

    s += [P("5. Architecture and technology decisions", H1), arch_diagram(),
          table([["Decision", "Choice and reason"],
                 ["Modular monolith", "One deployable FastAPI service with strict module seams (api / services / repositories / adapters); microservices would add cost with no benefit at ~2,200 trips/month."],
                 ["Backend", "Python 3.12+, FastAPI, Pydantic v2 (strict extraction schema, request validation), SQLAlchemy 2, Alembic, Argon2 (passwords), PyJWT."],
                 ["Frontend", "Next.js 16 App Router, React 19, strict TypeScript, Tailwind v4 with shadcn-style components (button, input, select, badge, card, table, dialog, dropdown, toast, empty/error/skeleton states), Lucide, Recharts."],
                 ["Persistence", "PostgreSQL (JSONB, UUID, NUMERIC money, CHECK/UNIQUE/FK). SQLite is used only for fast unit tests via portable column types. All timestamps are UTC; the UI renders IST."],
                 ["AI provider", "<font face='Courier'>AIProvider.analyze_pod()</font> interface; <font face='Courier'>ClaudeVisionProvider</font> calls the Anthropic Messages API directly over HTTPS with tool-use JSON, validated against a strict schema (the Python SDK was avoided because a native dependency was blocked by Windows Application Control during development); <font face='Courier'>manual</font> fallback; deterministic <font face='Courier'>mock</font> for tests only."],
                 ["Storage", "Adapter: local disk (dev / Render persistent disk) or private S3-compatible bucket. Images and CSVs are never public; they are streamed through authenticated endpoints with <i>Cache-Control: private, no-store</i>."]],
                [34 * mm, W - 34 * mm])]


    s += [P("API surface (versioned under /api/v1)", H2),
          table([["Area", "Endpoints (role)"],
                 ["Auth", "POST /auth/login (rate-limited), GET /auth/me, POST /auth/logout"],
                 ["Trips", "GET /trips (billing, search + 9 filters + pagination), GET /trips/{id} (billing; driver if assigned), POST /trips/import (billing, ?dry_run), GET /trips/{id}/history (billing), GET /meta/options"],
                 ["PODs", "POST /trips/{id}/pods (Idempotency-Key; driver own / billing), GET /pods/{id}, GET /pods/{id}/image (authenticated stream), POST /pods/{id}/process, POST /pods/{id}/retake (billing)"],
                 ["Review", "GET /reviews (status, reason, priority, client filters), POST /pods/{id}/review (billing)"],
                 ["Driver", "GET /driver/trips, GET /driver/uploads, POST /driver/uploads/sync (acknowledges idempotency keys)"],
                 ["Hired driver", "POST /driver-links (billing), GET /driver-links/{token}, POST /driver-links/{token}/pods (token-scoped, no account)"],
                 ["Billing", "GET /billing/queue, POST /billing/exports, GET /billing/exports, GET /billing/exports/{id}/download, POST /billing/trips/{id}/invoiced (manual record)"],
                 ["Dashboard / audit", "GET /dashboard/metrics | pod-aging | client-breakdown | missing-pods | recent-activity, GET /audit-logs (billing). GET /health is unauthenticated."]],
                [26 * mm, W - 26 * mm]),
          P("Errors use one envelope, <font face='Courier'>{error:{code,message,details}}</font>, with 400/401/403/404/409/413/415/422/429 used consistently. Request bodies are Pydantic models; responses are explicit serializers that never expose storage paths or token hashes.", SMALL)]

    s += [PageBreak(), P("6. Database schema and ER diagram", H1), er_diagram(),
          P("Thirteen normalised tables: the nine required (users, clients, vehicles, trips, pods, pod_extractions, pod_reviews, upload_jobs, billing_exports, audit_logs) plus <b>billing_export_items</b> (normalised export contents), "
            "<b>driver_links</b> (hashed single-trip tokens) and <b>sms_delivery_log</b> (mock provider log). Added columns beyond the brief: trips.consignee_name, expected_quantity, quantity_unit, billing_cycle, invoice_reference; "
            "pods.verification_method, verified_at, review_reasons, review_priority, source. Constraints: unique LR/trip reference, unique (trip, attempt), unique idempotency key, retake_count 0..2, status CHECKs, NUMERIC(12,2) freight. "
            "Evidence is never overwritten: each retake is a new pods row, each AI run a new pod_extractions row, each human decision a pod_reviews row. "
            "The Alembic baseline revision materialises this schema; later changes should be incremental revisions."),
          P("7. Main workflows", H1), state_diagram(), *state_notes(),
          *B(["<b>Upload.</b> POST /trips/{id}/pods with an <i>Idempotency-Key</i>; the server validates the image by decoding it (type, size), stores it, writes pod + upload_job + audit in one transaction, returns 201 (or 200 with the original resource on a duplicate key), then processes asynchronously.",
              "<b>Review.</b> POST /pods/{id}/review (APPROVE | REJECT | RETAKE). Corrections are validated per field, require a reason, and are stored beside the untouched AI values; every decision writes audit rows. Only NEEDS_REVIEW can be reviewed; a rejected POD stays in history.",
              "<b>Billing.</b> Eligible = trip not cancelled, latest POD VERIFIED, LR / e-way bill / client / delivery date / freight present. POST /billing/exports writes a CSV, an export record with its trip list and marks trips EXPORTED. Re-exporting an exported trip is refused unless <i>reexport=true</i> with a reason. INVOICED can only be recorded manually with an external reference.",
              "<b>Hired driver.</b> Billing creates a 256-bit random token (only its SHA-256 is stored), scoped to one trip, expiring (default 24 h). The /upload/{token} page needs no account; opens and uploads are audited. A mock provider writes a delivery-log row; <b>no SMS is sent</b>."])]

    s += [P("8. AI document processing architecture", H1),
          P("After upload a background task reads the stored image, runs a cheap blank-image pre-check, and calls the provider with a system prompt that forbids guessing, a tool whose JSON Schema "
            "requires every field (null when unreadable; <i>tool_choice=auto</i> because the model rejects forced choice, so the prompt mandates the call and a missing call is an <i>invalid_output</i> error), and <b>no expected trip values</b> (so the model reads rather than confirms). Output is validated by a strict Pydantic model "
            "(<font face='Courier'>extra=forbid</font>, confidences in [0,1], ISO dates) &mdash; failure is an <i>invalid_output</i> error. Extracted: LR number, consignee, delivered quantity + unit, delivery date, "
            "signature visible, stamp visible, shortage / damage flags, verbatim remarks, readability and observations. Every run stores provider, model id, prompt version (pod-extract-1.0), schema version (1.0), duration, "
            "field confidences, validation checks and any error."),
          table([["Failure", "Handling"],
                 ["Timeout / network / rate limit / 5xx", "Typed AIProviderError; POD kept; routed to NEEDS_REVIEW with reason AI_ERROR; staff can <i>Re-run AI extraction</i>."],
                 ["Invalid structured output / unsupported or unreadable image", "Same, or retake when the image is blank/unreadable and retakes remain."],
                 ["Missing API key / provider disabled", "Not-configured error recorded; every POD goes to a human (manual mode)."],
                 ["Any exception during processing", "Caught; extraction row records the failure; the document is never lost."]], [60 * mm, W - 60 * mm]),
          P("<b>Provider verification status:</b> the adapter is contract-tested against a stubbed HTTP layer (request shape, success parsing, 400/401/429/5xx/timeout/network and invalid-output mappings) <b>and was exercised live</b> "
            "with model <i>claude-sonnet-5-5</i> on three synthetic documents (credit use was deliberately limited). A clean signed+stamped POD was read correctly (LR, consignee, 600 bags, date; confidences 0.95-0.97) and auto-verified through the real API path in 4.7 s; "
            "a shortage document returned 594 bags, 'Short by 6 bags' and shortage_detected=true. <b>This is three samples, not an accuracy measurement</b>: no accuracy, cost or load figures are claimed, and blurred, wrong-LR, missing-stamp and damage photos were not run live (covered by mock tests). Seeded demo extractions are labelled <i>seed-data</i>.", ASSUME)]

    s += [P("9. Confidence handling and human review", H1),
          table([["Rule (implemented in services/ai/validation.py)", "Outcome"],
                 ["Critical field (LR, consignee, date) confidence below threshold (default 0.85)", "NEEDS_REVIEW (LOW_CONFIDENCE)"],
                 ["Shortage remark, damage remark, LR mismatch, consignee mismatch, quantity mismatch (only if expected quantity exists), implausible date", "NEEDS_REVIEW (high / medium priority)"],
                 ["Missing LR/consignee/date, stamp or signature not visible, unreadable image", "RETAKE_REQUESTED while retakes remain (cap 2), else NEEDS_REVIEW"],
                 ["Provider error", "NEEDS_REVIEW (AI_ERROR)"],
                 ["All checks pass", "VERIFIED by automated checks (see A2); high confidence never overrides a failed check"]], [W - 62 * mm, 62 * mm]),
          P("The review screen (shared by the AI verification screen) shows the original image with zoom/rotate, Expected vs AI-read per field, field confidence, check results and highlights for matches, mismatches, "
            "missing and low-confidence values. Signature and stamp are shown as <i>visible/not visible</i> with an explicit notice that <b>RouteProof does not authenticate them</b>. Reviewers edit a field, give a reason, then approve, "
            "reject (reason required) or request a retake (disabled at the cap). Both the AI original and the corrected value stay visible, in the review history and in the audit log.")]

    s += [P("10. Offline-first architecture", H1),
          *B(["<b>Capture:</b> file input with <i>capture=environment</i> opens the phone camera (also works on basic Android); GPS requested with timeout and permission handling; capture UUID, trip id, client timestamp, coordinates/accuracy stored.",
              "<b>Compression:</b> Canvas re-encode to JPEG, stepping quality then dimension until &lt;300 KB (verified in e2e and unit tests). The original blob and the compressed upload artifact are stored as separate fields in IndexedDB.",
              "<b>Queue:</b> record is persisted <i>before</i> any network call. Statuses: PENDING (shown as 'waiting for network' when offline), UPLOADING, UPLOADED, FAILED, RETRY_REQUIRED (after 3 transient failures; manual retry button). A single-flight flush runs on the browser <i>online</i> event, every 20 s, on tab focus, at start-up and via the retry button.",
              "<b>Idempotency:</b> the capture UUID is the Idempotency-Key on every attempt; the server enforces a unique key and returns the original POD on duplicates. Keys cannot be reused across trips.",
              "<b>Acknowledgement:</b> only after a successful response is the original (and compressed) blob released. Permanent 4xx errors become FAILED with the server message instead of retrying forever.",
              "<b>PWA:</b> manifest + production service worker caching the app shell; Background Sync merely wakes open pages (the token lives in the page), so manual and foreground retry are the guaranteed path."])]

    s += [P("11. UI/UX design decisions and key screens", H1),
          P("Two deliberately different interaction models on one design system (forest #183B36, teal #2D7768, canvas #F3F5F2, amber #D69B37, Inter). <b>Driver:</b> one giant camera button, large cards showing the LR number, "
            "icon-first status (green = verified, amber = retake/review, red only for real errors), Hindi/Marathi/English toggle with browser speech synthesis where a voice exists and on-screen text otherwise, persistent online/offline banner. "
            "<b>Executive:</b> sidebar workspace, compact KPI cards, dense tables with right-aligned tabular numbers, filters on every list, split-pane document review. Every list has skeleton, empty and error-with-retry states; destructive or irreversible actions use confirmation dialogs; toasts report outcomes."),
          table([["Screen", "Route", "Notes"],
                 ["Operations dashboard", "/dashboard", "KPIs, aging chart, client stacked bars, branch table, recent activity; filters date/client/branch; labelled <i>Seeded demo data</i> vs <i>Live</i> from DATA_MODE; every number from /dashboard/*"],
                 ["Trips + detail", "/trips, /trips/{id}", "search, 6 filters, pagination, CSV import (dry-run, duplicate + row-error report); POD attempts, audit history, billing history, hired-driver link"],
                 ["POD capture (driver)", "/driver, /driver/capture/{id}, /driver/queue", "offline indicator, preview/retake, GPS chip, state tracker, queue with retry"],
                 ["AI verification + review", "/pods/{id}, /reviews", "split view, confidence, validation, corrections with reasons, approve/reject/retake, priority queue"],
                 ["Billing queue", "/billing", "verified trips only, client/cycle/date/search filters, selection, CSV, export history, explicit re-export"],
                 ["Missing PODs", "/operations", "actionable overdue list, elapsed days, freight held back, pending reviews"],
                 ["Hired driver", "/upload/{token}", "mobile landing, no login, same capture engine"]], [38 * mm, 42 * mm, W - 80 * mm])]

    s += [P("12. Security and data protection", H1),
          *B(["<b>AuthN/Z:</b> Argon2 hashes, JWT with expiry, 401/403 enforced in FastAPI dependencies. Drivers are limited to assigned trips by a resource-level check that returns 404 (not 403) for others' trips, PODs and images; drivers receive no freight/billing fields. Billing-only endpoints return 403 to drivers (tested).",
              "<b>Input:</b> Pydantic validation, CSV size/row limits, image validated by decoding (not by Content-Type), 5 MB cap, CSV formula-injection neutralisation, safe error envelope without stack traces.",
              "<b>Abuse:</b> in-memory rate limits on login and link endpoints (per instance); unknown-user logins cost the same hash verification; CORS restricted to configured origins; security headers on the frontend.",
              "<b>Secrets:</b> environment variables only; production start-up fails with a clear message when required secrets are missing; .env is git-ignored; the browser never sees the AI key.",
              "<b>Audit:</b> state change and audit row commit in one transaction (uploads, AI runs, corrections, approvals, exports, link creation/open/upload, login/logout).",
              "<b>Privacy (DPDP-aware, not a compliance claim):</b> data minimisation (no Aadhaar or unrelated identifiers; phone numbers only masked in logs; fictional demo data); POD images and consignee details treated as sensitive; images private and served only to authorised users; "
              "retention/deletion is <b>not</b> automated &mdash; a production policy (retention period, deletion on request, consent/notice for GPS capture, processor agreements with the AI vendor, data-residency choice) must be defined. "
              "Sending images to a third-party model is a cross-border processing decision for the client's legal team. <b>A proper legal and security review is required before production use.</b>"])]

    s += [P("13. Testing strategy and actual results", H1),
          table([["Layer", "Scope", "Result (run in the authoring environment)"],
                 ["Backend unit + API (pytest, httpx TestClient, SQLite, mock AI)", "routing policy, thresholds, schema strictness, state machine, retake cap, eligibility, CSV escaping, idempotency, auth, RBAC, driver scoping, upload validation, duplicate upload, AI timeout/invalid output/unreadable, review corrections + audit, queue filters, export + duplicate protection + re-export, hired-link security, dashboard, CSV import, Claude adapter contract", "<b>58 passed</b> on SQLite and again on PostgreSQL 16"],
                 ["Frontend (Vitest + Testing Library + fake-indexeddb)", "login, dashboard rendering and error state, trip search, verification highlighting, correction-reason rule, retake cap, billing export and re-export, offline queue (retry with same key, ack releases blobs, no concurrent flush, offline skip), i18n and voice fallback, compression policy", "<b>25 passed</b>"],
                 ["End-to-end (Playwright, Chromium, real browser + real API with deterministic mock AI)", "driver capture (<300 KB) &gt; AI &gt; review &gt; correction &gt; approval &gt; billing queue &gt; CSV download &gt; audit; clean POD auto-verified; AI timeout; two retakes then review; authorization; dashboard; hired link; offline capture with network disabled, in-page reconnect sync, duplicate retry", "<b>9 passed</b>"],
                 ["Static checks", "ESLint, <font face='Courier'>tsc --noEmit</font> (strict), <font face='Courier'>next build</font>", "clean / clean / success"]], [44 * mm, W - 74 * mm, 30 * mm]),
          P("Testing found and fixed four real defects: (a) PostgreSQL enforced an insert-order foreign key (upload job before its POD) that SQLite hid; (b) the live model rejects forced tool_choice; and (1) a single-flight lock released before it was assigned when the queue flushed while offline, which would have blocked in-page auto-sync after reconnection; "
            "(2) dialogs re-grabbed focus on every keystroke, breaking reason entry. <b>Verified on PostgreSQL 16:</b> migration, idempotent seed, JSONB/NUMERIC/UUID column types and the full pytest suite. <b>Not tested:</b> the production service worker offline-navigation path, real Android devices, load/performance, and any cloud deployment. The Playwright suite uses SQLite and the mock model by design.", ASSUME)]

    s += [P("14. Deployment architecture", H1),
          P("Target: frontend on Vercel (or a second Render service) &rarr; FastAPI container on Render (<font face='Courier'>render.yaml</font>, health check <font face='Courier'>/health</font>) &rarr; managed PostgreSQL + persistent disk for images "
            "(or an S3-compatible private bucket via <font face='Courier'>STORAGE_PROVIDER=s3</font>). The container runs <font face='Courier'>alembic upgrade head</font>, an idempotent seed, then uvicorn. Render has no India region, "
            "so the blueprint uses Singapore; for India residency choose AWS ap-south-1 (Mumbai) storage/database. <b>Status: configuration and instructions are complete; nothing has been deployed or verified live.</b> "
            "A single instance is assumed (disk storage, in-memory rate limiter); scale-out needs S3 and a shared limiter."),
          P("15. Known limitations", H1),
          *B(["Live extraction was checked on only three synthetic documents; quality on real, messy photographs, latency and cost are unmeasured and the 0.85 threshold is uncalibrated.",
              "Cloud deployment and the GitHub URL are pending (see sections 2 and 14). The Alembic baseline uses metadata create-all; only incremental revisions are true diffs.",
              "JWT in browser storage is exposed to XSS; there is no refresh/revocation. In-memory rate limiting is per instance. No automated retention/deletion job.",
              "Camera access relies on the OS camera app through a file input (robust on basic Android, but no in-page live preview). PDFs and multi-page PODs are not supported; only JPEG/PNG/WebP.",
              "Dashboard aggregation loads filtered trips and computes in Python: fine at the stated volume, to be moved to SQL aggregates if volumes grow. Review queue paginates in memory.",
              "Hindi/Marathi strings were written by the developer and need native-speaker review; speech depends on installed browser voices.",
              "Background Sync cannot upload by itself while the app is closed (token is in the page)."]),
          P("16. Features deliberately excluded", H1),
          P("Real SMS delivery (mock adapter only), live Tally integration (CSV only), automatic invoice generation/sending, e-way bill or GPS-tracking integrations, signature/stamp authentication, payments, a third role, microservices, "
            "multi-tenant administration, and push notifications."),
          P("17. Future improvements", H1),
          *B(["Calibrate thresholds from a labelled sample of real PODs; track precision of auto-verification and reviewer-override rate.",
              "Short-lived access + refresh tokens with revocation; httpOnly cookies; shared rate limiter; malware scan on uploads.",
              "SQL-side aggregations and materialised metrics; background worker queue for AI jobs with retries and dead-lettering.",
              "On-device quality guidance (blur / glare / edge detection) before sending; multi-page capture; PDF support.",
              "Retention and deletion automation; field-level encryption for sensitive images; region-pinned storage; accessibility audit and native-speaker localisation review.",
              "Real SMS/WhatsApp provider, Tally import automation, and e-invoicing handled as separate, approved integrations."])]

    def footer(c, d):
        c.saveState()
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.HexColor("#777777"))
        c.drawString(17 * mm, 8 * mm, "RouteProof - Technical Design Document")
        c.drawRightString(A4[0] - 17 * mm, 8 * mm, f"Page {d.page}")
        c.restoreState()

    doc.build(s, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "Technical_Design_Document.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    build(out)
    print("wrote", out)
