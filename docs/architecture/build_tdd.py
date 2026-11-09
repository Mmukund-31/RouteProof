"""Builds Technical_Design_Document.pdf. Run: python docs/architecture/build_tdd.py <out.pdf>

Content mirrors what is implemented in this repository (backend/app/models/entities.py, app/api/v1, app/services and the
frontend). Items that were NOT verified (cloud deployment, real Android devices, accuracy on real PODs) are stated as such:
edit the constants below once they exist and rebuild.
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

# ---- update these when they change, then rebuild ----
GITHUB_URL = "https://github.com/Mmukund-31/RouteProof"
LIVE_URL = "NOT DEPLOYED - no live frontend exists yet"
HEALTH_URL = "NOT DEPLOYED - no live backend exists yet"
# Test counts from the last full run (see deployment.md section 11); keep in step with README.md.
BACKEND_TESTS, FRONTEND_TESTS, E2E_TESTS = "201 passed, 2 opt-in skipped (1 demo-generator test needs scripts/ beside backend/)", "57", "16 Playwright specs"
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
    d = Drawing(520, 262)
    left = [("Driver PWA (mobile)", ["IndexedDB queue + originals", "Canvas compression <300 KB", "Service worker, hi/mr voice"]),
            ("Billing workspace", ["Dashboard, trips, review,", "billing, client links, audit", "Session: HttpOnly cookie"]),
            ("Hired-driver page", ["/upload/{token}, no account", "Write-only, one trip", "Same capture + queue engine"]),
            ("Client POD view", ["/view/{token}, no account", "Read-only, one client", "Verified PODs only"])]
    for i, (t, l) in enumerate(left):
        box(d, 4, 196 - i * 62, 118, 54, t, l, CANVAS)
    box(d, 134, 14, 74, 236, "Next.js server", ["", "rewrite", "/api/v1/* ->", "FastAPI", "", "first-party", "cookies:", "rp_session", "(HttpOnly,", "SameSite=Lax)", "rp_csrf ->", "X-CSRF-Token", "header on", "every write", "", "CSP + security", "headers"],
        colors.HexColor("#EEF5F2"), TEAL, TEAL)
    box(d, 220, 14, 146, 236, "FastAPI modular monolith", [], colors.HexColor("#EEF5F2"), TEAL, TEAL)
    mods = [("api/v1 routers", "authN/Z, CSRF, rate limits, errors"), ("services/pods", "state machine, review, retake, recovery"),
            ("services/ai", "provider adapter + validation"), ("services/billing", "eligibility, CSV, exports"),
            ("client_links / driver_links", "hashed tokens, scoped, audited"), ("services/uploads + retention", "storage, originals, purge, hold"),
            ("repositories + models", "SQLAlchemy 2, Alembic, 15 tables")]
    for i, (t, l) in enumerate(mods):
        box(d, 227, 208 - i * 31, 132, 27, t, [l], colors.white, TEAL, FOREST)
    box(d, 406, 192, 110, 56, "Claude vision API", ["HTTPS REST, tool-use JSON", "Strict schema + confidence", "Provider is swappable"], colors.HexColor("#FBF3E1"), AMBER)
    box(d, 406, 104, 110, 56, "PostgreSQL 16", ["UUID, JSONB, NUMERIC", "CHECK / UNIQUE / FK", "audit_logs (append)"], colors.white)
    box(d, 406, 16, 110, 56, "Private object storage", ["Local disk or S3-compatible", "Never public; API-served", "Images + export CSVs"], colors.white)
    for i in range(4):
        arrow(d, 122, 223 - i * 62, 134, 223 - i * 62)
    arrow(d, 208, 132, 220, 132)
    arrow(d, 366, 165, 406, 220, "inference")
    arrow(d, 366, 132, 406, 132, "SQL")
    arrow(d, 366, 70, 406, 44, "put/get")
    return d


def er_diagram():
    d = Drawing(520, 300)
    T, ops = {}, []
    cols = [
        (4, 100, [("users", "users", ["id uuid PK", "email UNIQUE, role CHECK", "password_hash (argon2)", "phone, preferred_language", "is_active"]),
                  ("clients", "clients", ["id uuid PK", "client_code UNIQUE", "company_name", "billing_contact_email"]),
                  ("cvl", "client_view_links", ["token_hash UNIQUE (SHA-256)", "client_id FK, created_by FK", "scope trips | billing_cycle", "trip_ids JSON / billing_cycle", "expires_at, revoked_at/_by", "access_count, last_accessed_at"]),
                  ("vehicles", "vehicles", ["id uuid PK", "registration UNIQUE", "ownership owned|hired"])]),
        (142, 128, [("trips", "trips", ["id uuid PK", "trip_reference, lr_number UNIQUE", "eway_bill_number, branch", "client_id, vehicle_id, driver_id FK", "freight_amount NUMERIC(12,2)", "trip_status, billing_status CHECK", "delivery_date (+source), billing_cycle", "invoice_reference, invoice_date", "billing_ready/exported/invoiced_at"]),
                    ("pods", "pods", ["id uuid PK, UNIQUE(trip,attempt)", "trip_id FK, attempt_number, source", "uploaded_/original_image_path", "upload_bytes, original_bytes", "captured_at (device), server_received_at", "lat/lng/accuracy, location_status", "verification_status CHECK, method", "retake_count CHECK 0..2", "processing_started_at, attempts", "approved_exceptions, images_purged_at"]),
                    ("prr", "pod_review_reasons", ["pod_id FK (on delete cascade)", "reason, UNIQUE(pod, reason)", "category system|quality|business"])]),
        (298, 120, [("ext", "pod_extractions", ["pod_id FK", "extracted/confidence/validation", "provider, model, prompt/schema ver", "status, error, duration_ms", "processing_id, attempt_count"]),
                    ("rev", "pod_reviews", ["pod_id FK, reviewer_id FK", "original_values JSONB", "corrected_values JSONB", "correction/approval_reason", "accepted_exceptions, decision"]),
                    ("job", "upload_jobs", ["pod_id FK, trip_id FK", "idempotency_key UNIQUE", "retry_count, last_error"]),
                    ("link", "driver_links", ["token_hash UNIQUE (SHA-256)", "trip_id FK, created_by FK", "phone_masked, expires_at", "revoked(_at/_by), use_count"])]),
        (430, 86, [("exp", "billing_exports", ["export_reference UQ", "client_id FK, filters", "file_path, is_reexport", "reexport_reason", "created_by FK"]),
                   ("item", "billing_export_items", ["export_id FK, trip_id FK", "UNIQUE(export, trip)"]),
                   ("audit", "audit_logs", ["user_id FK (nullable)", "entity_type/id, action", "previous/new values", "metadata, timestamp"]),
                   ("sms", "sms_delivery_log", ["link_id FK", "provider = mock", "LOGGED_NOT_SENT"])]),
    ]
    for x, w, tables in cols:
        y_top = 278
        for key, name, fields in tables:
            h = 14 + 7.4 * len(fields)
            y = y_top - h
            T[key] = (x, y, w, h)
            ops.append((x, y, w, h, name, fields))
            y_top = y - 9

    def c(k, side):
        x, y, w, h = T[k]
        return {"l": (x, y + h / 2), "r": (x + w, y + h / 2), "t": (x + w / 2, y + h), "b": (x + w / 2, y)}[side]
    for a, sa, b, sb in [("users", "r", "trips", "l"), ("clients", "r", "trips", "l"), ("vehicles", "r", "trips", "l"), ("clients", "b", "cvl", "t"),
                         ("trips", "b", "pods", "t"), ("pods", "b", "prr", "t"), ("pods", "r", "ext", "l"), ("pods", "r", "rev", "l"),
                         ("pods", "r", "job", "l"), ("trips", "r", "link", "l"), ("link", "r", "sms", "l"), ("exp", "b", "item", "t"),
                         ("trips", "r", "item", "l"), ("clients", "r", "exp", "l")]:
        (x1, y1), (x2, y2) = c(a, sa), c(b, sb)
        d.add(Line(x1, y1, x2, y2, strokeColor=colors.HexColor("#9AA8A4"), strokeWidth=0.6))
    for (x, y, w, h, name, fields) in ops:  # tables drawn after the connector lines so text stays readable
        d.add(Rect(x, y, w, h, fillColor=colors.white, strokeColor=FOREST, strokeWidth=0.8))
        d.add(Rect(x, y + h - 10, w, 10, fillColor=FOREST, strokeColor=FOREST))
        d.add(String(x + 3, y + h - 7.6, name, fontName="Helvetica-Bold", fontSize=6.6, fillColor=colors.white))
        for i, f in enumerate(fields):
            d.add(String(x + 3, y + h - 17.5 - i * 7.4, f, fontName="Helvetica", fontSize=5.5, fillColor=colors.HexColor("#333333")))
    d.add(String(4, 292, "Lines = foreign keys (1:N). 15 tables, all with UUID primary keys. users.id is also referenced by pod_reviews.reviewer_id,",
                 fontName="Helvetica-Oblique", fontSize=6, fillColor=colors.HexColor("#555555")))
    d.add(String(4, 285.5, "*.created_by / revoked_by and audit_logs.user_id (lines omitted for legibility). JSON columns are JSONB on PostgreSQL.",
                 fontName="Helvetica-Oblique", fontSize=6, fillColor=colors.HexColor("#555555")))
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
            "Eight primary screens: (1) operations dashboard, (2) trips, (3) driver trip list, (4) POD capture, (5) result / retake, (6) review queue and review screen, (7) billing (queue, export history, client links), "
            "(8) POD viewer (staff review screen and the read-only client view link). Login, the hired-driver upload page, the full missing-POD list and audit history are supporting views."),
          P("2. GitHub and live deployment links", H1),
          P(f"GitHub: <b>{GITHUB_URL}</b>. Live frontend: <b>{LIVE_URL}</b>. Health endpoint: <b>{HEALTH_URL}</b>. "
            "The source is published at the GitHub URL above. The Dockerfile, <font face='Courier'>render.yaml</font> and step-by-step instructions are complete, but the application has <b>not</b> been deployed: "
            "no live frontend or backend exists yet and no deployment claim is made."),
          P("3. Client problem and product objectives", H1),
          P("Signed lorry receipts return 10&ndash;20 days after delivery; WhatsApp photos are lost; invoices cannot be raised without POD, so working capital is locked. Client-provided figures "
            "(<b>assumptions supplied by the client, not verified by us</b>): POD-to-invoice 18 days today, 4-day target; ~Rs 3.24 crore working capital released; ~Rs 38.9 lakh annual financing benefit; "
            "~Rs 63.36 lakh/yr lost to lost or disputed PODs; ~Rs 1.02 crore total opportunity. This build instruments the pipeline (upload latency, upload-to-billing-ready time) so that such figures can later be measured; "
            "it does <b>not</b> assert any achieved improvement."),
          *B(["Capture POD at the consignee with one obvious action, even with no network.", "Extract LR, consignee, quantity, date, signature/stamp visibility and shortage/damage remarks with a vision model; never trust confidence alone.",
              "Route every doubtful case to a person with the original image beside the AI values; preserve AI originals and every attempt.",
              "Make only verified trips billable; export a documented CSV; keep a complete audit trail."])]

    s += [P("4. Explicit assumptions", H1),
          A(1, "AI confidence threshold 0.85 on critical fields (LR, consignee, delivered quantity, date) is an implementation default, <b>not</b> a calibrated probability; it is configurable (<font face='Courier'>AI_CONFIDENCE_THRESHOLD</font>) and recorded with every extraction."),
          A(2, "When the model returns output and <i>all</i> deterministic checks pass (LR match, consignee match, plausible date, no shortage/damage, stamp and signature visible, confidences above threshold, quantity equal if an expected quantity exists), the POD is auto-verified (<i>verification_method = ai</i>) and the trip becomes billing-ready. A reviewer may prefer a mandatory human step; that is a one-line policy change."),
          A(3, "Consignee match = case/punctuation-insensitive substring or >= 0.70 sequence similarity. Date plausible = not in the future and within 7 days before to 30 days after the trip delivery date. LR compared after stripping non-alphanumerics."),
          A(4, "Trips carry an optional expected quantity + unit (added to the specified schema). Quantity is compared <i>only</i> when it exists; otherwise the check is reported as not compared."),
          A(5, "Missing stamp, missing signature, missing LR or an unreadable image request a retake (max 2); a mismatch, shortage, damage, quantity/date problem or low confidence goes to review. After 2 retakes everything goes to review."),
          A(6, "Two-stage upload: the compressed (&lt;300 KB) JPEG is sent first and processed by AI; once the server acknowledges it, the full-resolution original is attached separately (POST /pods/{id}/original, or the link equivalent) when the connection allows. The original stays in IndexedDB until that second upload is acknowledged; a failed original upload never removes the already-accepted compressed evidence or the copy on the phone."),
          A(7, "Client clocks and GPS are labelled as device-reported and are not proof; server receipt time is stored separately. Billing cycles are half-months (e.g. 2026-11-H1). A POD is 'overdue' after 3 days (configurable)."),
          A(8, "Browser sessions are a signed JWT in an <b>HttpOnly, SameSite=Lax cookie</b> (unreadable by page JavaScript) with a session-bound double-submit CSRF token (rp_csrf cookie echoed as X-CSRF-Token on every write). Sessions expire after <b>60 minutes idle</b> (sliding refresh) and <b>12 hours absolute</b> from login. Logout clears the cookies and is audited, but a copied token stays valid until it expires (no server-side denylist). Rate limiting is an in-memory per-instance sliding window. All seeded data and demo credentials are fictional and non-production.")]

    s += [P("5. Architecture and technology decisions", H1), arch_diagram(),
          table([["Decision", "Choice and reason"],
                 ["Modular monolith", "One deployable FastAPI service with strict module seams (api / services / repositories / adapters); microservices would add cost with no benefit at ~2,200 trips/month."],
                 ["Backend", "Python 3.12+, FastAPI, Pydantic v2 (strict extraction schema, request validation), SQLAlchemy 2, Alembic, Argon2 (passwords), PyJWT in an HttpOnly cookie + CSRF; the Next.js server proxies /api/v1 so cookies stay first-party."],
                 ["Frontend", "Next.js 16 App Router, React 19, strict TypeScript, Tailwind v4 with shadcn-style components (button, input, select, badge, card, table, dialog, dropdown, toast, empty/error/skeleton states), Lucide, Recharts."],
                 ["Persistence", "PostgreSQL (JSONB, UUID, NUMERIC money, CHECK/UNIQUE/FK). SQLite is used only for fast unit tests via portable column types. All timestamps are UTC; the UI renders IST."],
                 ["AI provider", "<font face='Courier'>AIProvider.analyze_pod()</font> interface; <font face='Courier'>ClaudeVisionProvider</font> calls the Anthropic Messages API directly over HTTPS with tool-use JSON, validated against a strict schema (the Python SDK was avoided because a native dependency was blocked by Windows Application Control during development); <font face='Courier'>manual</font> fallback; deterministic <font face='Courier'>mock</font> for tests only."],
                 ["Storage", "Adapter: local disk (dev / Render persistent disk) or private S3-compatible bucket. Images and CSVs are never public; they are streamed through authenticated endpoints with <i>Cache-Control: private, no-store</i>."]],
                [34 * mm, W - 34 * mm])]


    s += [P("API surface (versioned under /api/v1)", H2),
          table([["Area", "Endpoints (role)"],
                 ["Auth", "POST /auth/login (rate-limited; sets HttpOnly session + CSRF cookies), GET /auth/me, POST /auth/logout"],
                 ["Trips", "GET /trips (billing, search + filters + whitelisted sort + SQL pagination), GET /trips/{id} (billing; driver if assigned), POST /trips/import (billing, ?dry_run), GET /trips/{id}/history (billing), GET /meta/options"],
                 ["PODs", "POST /trips/{id}/pods (Idempotency-Key; driver own / billing), POST /pods/{id}/original (full-resolution original), GET /pods/{id}, GET /pods/{id}/image?variant=upload|original (authenticated stream; 410 after purge), POST /pods/{id}/process, POST /pods/{id}/retake, POST /pods/maintenance/recover (billing)"],
                 ["Review", "GET /reviews (status, reason, category, priority, client, search; filtered, ordered and paginated in SQL via pod_review_reasons), POST /pods/{id}/review (billing)"],
                 ["Driver", "GET /driver/trips, GET /driver/uploads, POST /driver/uploads/sync (acknowledges idempotency keys)"],
                 ["Hired driver", "POST /driver-links, GET /driver-links?trip_id=, POST /driver-links/{id}/revoke (billing); GET /driver-links/{token}, POST /driver-links/{token}/pods, POST /driver-links/{token}/pods/{pod_id}/original (token-scoped, no account)"],
                 ["Billing", "GET /billing/queue, POST /billing/exports, GET /billing/exports, GET /billing/exports/{id}/download, POST /billing/trips/{id}/invoiced (invoice_reference + invoice_date, recorded manually)"],
                 ["Client links (staff)", "POST /client-links (client + trip list or billing cycle, expiry 1-30 days), GET /client-links, POST /client-links/{id}/revoke (billing)"],
                 ["Client view (public)", "GET /client-view/{token} (scoped trip list, verified PODs only), GET /client-view/{token}/trips/{trip_id}/pod-image; 410 when expired or revoked; every access audited"],
                 ["Dashboard / audit", "GET /dashboard/metrics | pod-aging | client-breakdown | missing-pods | recent-activity, GET /audit-logs (billing). GET /health is unauthenticated."]],
                [26 * mm, W - 26 * mm]),
          P("Errors use one envelope, <font face='Courier'>{error:{code,message,details}}</font>, with 400/401/403/404/409/413/415/422/429 used consistently. Request bodies are Pydantic models; responses are explicit serializers that never expose storage paths or token hashes.", SMALL)]

    s += [PageBreak(), P("6. Database schema and ER diagram", H1), er_diagram(),
          P("Fifteen tables, matching backend/app/models/entities.py: users, clients, vehicles, trips, pods, <b>pod_review_reasons</b> (one row per POD and reason, so the review queue filters in SQL), pod_extractions, pod_reviews, upload_jobs, "
            "<b>driver_links</b> (hashed single-trip upload tokens), <b>client_view_links</b> (hashed read-only client tokens scoped to trips or a billing cycle), <b>sms_delivery_log</b> (mock provider log), billing_exports, <b>billing_export_items</b> and audit_logs. Added columns beyond the brief: trips.consignee_name, expected_quantity, quantity_unit, billing_cycle, invoice_reference; "
            "pods.verification_method, verified_at, review_reasons, review_priority, source. Constraints: unique LR/trip reference, unique (trip, attempt), unique idempotency key, retake_count 0..2, status CHECKs, NUMERIC(12,2) freight. "
            "Evidence is never overwritten: each retake is a new pods row, each AI run a new pod_extractions row, each human decision a pod_reviews row. "
            "The Alembic baseline revision materialises this schema; later changes should be incremental revisions."),
          P("7. Main workflows", H1), state_diagram(), *state_notes(),
          *B(["<b>Upload.</b> POST /trips/{id}/pods with an <i>Idempotency-Key</i>; the server validates the image by decoding it (type, size), stores it, writes pod + upload_job + audit in one transaction, returns 201 (or 200 with the original resource on a duplicate key), then processes asynchronously.",
              "<b>Review.</b> POST /pods/{id}/review (APPROVE | REJECT | RETAKE). Corrections are validated per field, require a reason, and are stored beside the untouched AI values; every decision writes audit rows. Only NEEDS_REVIEW can be reviewed; a rejected POD stays in history.",
              "<b>Billing.</b> Eligible = trip not cancelled, latest POD VERIFIED, LR / e-way bill / client / delivery date / freight present. POST /billing/exports writes a CSV, an export record with its trip list and marks trips EXPORTED. Re-exporting an exported trip is refused unless <i>reexport=true</i> with a reason. INVOICED can only be recorded manually with an external invoice reference and invoice date. Each CSV row carries evidence references: pod_reference (exact attempt), pod_image_reference (PODIMG-id), pod_verified_date, pod_exceptions and pod_evidence_url (staff login); no storage paths or public image URLs.",
              "<b>Client evidence sharing.</b> From the billing queue (<i>Share PODs</i>), export history (<i>Client link</i>) or <i>Client POD links</i>, a billing executive creates a read-only link for one client, scoped to selected trips or a billing cycle, expiring in 1-30 days. The client sees trip reference, LR, delivery date, POD status and reference and the verified image only; never driver, phone, freight, GPS or other clients' trips. Revocation or expiry returns 410; creation, opens, image views, denied attempts and revocation are audited. A client token can never resolve as a driver upload token (separate table and URL space).",
              "<b>Hired driver.</b> Billing creates a 256-bit random token (only its SHA-256 is stored), scoped to one trip, expiring (default 24 h). The /upload/{token} page needs no account, can only write a POD (and its original) for that one trip, and is revocable; opens and uploads are audited. A mock provider writes a delivery-log row; <b>no SMS is sent</b>."])]

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
              "<b>Compression and originals:</b> Canvas re-encode to JPEG, stepping quality then dimension until &lt;300 KB. The original and compressed blobs are separate IndexedDB fields. The compressed copy is uploaded first; after it is acknowledged the original is sent in a lower-priority pass (good connection only, 180 s timeout, up to 5 attempts) and released only when acknowledged. A failed original never affects the accepted POD and stays on the phone.",
              "<b>Queue:</b> record is persisted <i>before</i> any network call. Statuses: PENDING (shown as 'waiting for network' when offline), UPLOADING, UPLOADED, FAILED, RETRY_REQUIRED (after 3 transient failures; manual retry button). A single-flight flush runs on the browser <i>online</i> event, every 20 s, on tab focus, at start-up and via the retry button.",
              "<b>Idempotency:</b> the capture UUID is the Idempotency-Key on every attempt; the server enforces a unique key and returns the original POD on duplicates. Keys cannot be reused across trips.",
              "<b>Acknowledgement:</b> the compressed blob is released after its upload is acknowledged, the original only after its own upload is acknowledged. Permanent 4xx errors become FAILED with the server message instead of retrying forever.",
              "<b>PWA:</b> manifest + production service worker caching the app shell; Background Sync merely wakes open pages (uploads need the session cookie or link token), so manual and foreground retry are the guaranteed path."])]

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
                 ["Hired driver", "/upload/{token}", "mobile landing, no login, same capture engine"],
                 ["Client links / client view", "/client-links, /view/{token}", "create, list, revoke; read-only verified POD evidence for one client"]], [38 * mm, 42 * mm, W - 80 * mm])]

    s += [P("12. Security and data protection", H1),
          *B(["<b>AuthN/Z:</b> Argon2 hashes; JWT in an HttpOnly, SameSite cookie (not readable by page scripts, so an XSS bug cannot exfiltrate it) with a session-bound CSRF token required on every state-changing request; 60-min idle / 12-h absolute expiry; production refuses non-secure cookies. 401/403 enforced in FastAPI dependencies. Drivers are limited to assigned trips by a resource-level check that returns 404 (not 403) for others' trips, PODs and images; drivers receive no freight/billing fields. Billing-only endpoints return 403 to drivers (tested).",
              "<b>Input:</b> Pydantic validation, CSV size/row limits, image validated by decoding (not by Content-Type), 5 MB cap, CSV formula-injection neutralisation, safe error envelope without stack traces.",
              "<b>Abuse:</b> in-memory rate limits on login and link endpoints (per instance); unknown-user logins cost the same hash verification; CORS restricted to configured origins; security headers on the frontend.",
              "<b>Secrets:</b> environment variables only; production start-up fails with a clear message when required secrets are missing; .env is git-ignored; the browser never sees the AI key.",
              "<b>Audit:</b> state change and audit row commit in one transaction (uploads, AI runs, corrections, approvals, exports, link creation/open/upload, login/logout).",
              "<b>Privacy (DPDP-aware, not a compliance claim):</b> data minimisation (no Aadhaar or unrelated identifiers; phone numbers only masked in logs; fictional demo data); POD images and consignee details treated as sensitive; images private and served only to authorised users; "
              "<b>Retention:</b> verified images of invoiced trips 2,920 days, superseded attempts 365 days, access logs 365 days (configurable); <font face='Courier'>python -m app.services.retention</font> is a dry run, <i>--apply</i> purges, <i>--erase-pod</i> with a reason handles an approved erasure request. "
            "<b>Legal hold:</b> images of a trip not yet invoiced or with an open POD are never purged; erasing one needs <i>--override-hold</i>, which is recorded. Purged images answer 410, the record is kept, and every purge writes an <b>audit</b> row without the deleted content. Nothing is deleted on a timer. "
              "Sending images to a third-party model is a cross-border processing decision for the client's legal team. <b>A proper legal and security review is required before production use.</b>"])]

    s += [P("13. Testing strategy and actual results", H1),
          table([["Layer", "Scope", "Result (run in the authoring environment)"],
                 ["Backend unit + API (pytest, httpx TestClient, SQLite, mock AI)", "routing policy, thresholds, schema strictness, state machine, retake cap, eligibility, CSV escaping, idempotency, auth, RBAC, driver scoping, upload validation, duplicate upload, AI timeout/invalid output/unreadable, review corrections + audit, queue filters, export + duplicate protection + re-export, hired-link and client-link security (scoping, expiry, revocation, token separation, audit), retention/erasure, every-endpoint auth sweep, labelled AI-routing evaluation set (31 cases), dashboard, CSV import, Claude adapter contract", f"<b>{BACKEND_TESTS}</b> on SQLite and on PostgreSQL 16 (CI runs both)"],
                 ["Frontend (Vitest + Testing Library + fake-indexeddb)", "login, dashboard rendering and error state, trip search, verification highlighting, correction-reason rule, retake cap, billing export and re-export, offline queue (retry with same key, ack releases blobs, no concurrent flush, offline skip), i18n and voice fallback, compression policy", f"<b>{FRONTEND_TESTS} passed</b>"],
                 ["End-to-end (Playwright, Chromium, real browser + real API with deterministic mock AI)", "driver capture (<300 KB) &gt; AI &gt; review &gt; correction &gt; approval &gt; billing queue &gt; CSV download &gt; audit; clean POD auto-verified; AI timeout; two retakes then review; authorization; dashboard; hired-driver link journey, client view + revocation, offline capture surviving an app restart, lost-response retry, server timeout, sign-out with unsent photos", f"<b>{E2E_TESTS}</b>"],
                 ["Static checks", "ESLint, <font face='Courier'>tsc --noEmit</font> (strict), <font face='Courier'>next build</font>", "clean / clean / success"]], [44 * mm, W - 74 * mm, 30 * mm]),
          P("Testing found and fixed four real defects: (a) PostgreSQL enforced an insert-order foreign key (upload job before its POD) that SQLite hid; (b) the live model rejects forced tool_choice; and (1) a single-flight lock released before it was assigned when the queue flushed while offline, which would have blocked in-page auto-sync after reconnection; "
            "(2) dialogs re-grabbed focus on every keystroke, breaking reason entry. <b>Verified on PostgreSQL 16:</b> migration, idempotent seed, JSONB/NUMERIC/UUID column types and the full pytest suite. <b>Not tested:</b> the production service worker offline-navigation path, real Android devices, load/performance, and any cloud deployment. The Playwright suite uses SQLite, the mock model and the Next.js dev server by design. GitHub Actions (.github/workflows/ci.yml) runs backend tests on SQLite and PostgreSQL 16, frontend lint/typecheck/tests/build and Playwright on every push and pull request to main.", ASSUME)]

    s += [P("14. Deployment architecture", H1),
          P("Target: frontend on Vercel (or a second Render service) &rarr; FastAPI container on Render (<font face='Courier'>render.yaml</font>, health check <font face='Courier'>/health</font>) &rarr; managed PostgreSQL + persistent disk for images "
            "(or an S3-compatible private bucket via <font face='Courier'>STORAGE_PROVIDER=s3</font>). The container runs <font face='Courier'>alembic upgrade head</font>, an idempotent seed, then uvicorn. Render has no India region, "
            "so the blueprint uses Singapore; for India residency choose AWS ap-south-1 (Mumbai) storage/database. <b>Status: configuration and instructions are complete; nothing has been deployed or verified live.</b> "
            "A single instance is assumed (disk storage, in-memory rate limiter); scale-out needs S3 and a shared limiter."),
          P("15. Known limitations", H1),
          *B(["Live extraction was checked on only three synthetic documents; quality on real, messy photographs, latency and cost are unmeasured and the 0.85 threshold is uncalibrated.",
              "Cloud deployment is pending (see sections 2 and 14); the Render blueprint uses Singapore. The Alembic baseline uses metadata create-all; only incremental revisions are true diffs.",
              "Sessions are stateless JWT cookies: logout clears them but cannot revoke a copied token before expiry (no denylist). In-memory rate limiting is per instance. Retention runs on demand, not on a timer. AI runs in FastAPI BackgroundTasks with database-backed stale-job recovery, not a durable queue. Tally and SMS are mocked.",
              "Camera access relies on the OS camera app through a file input (robust on basic Android, but no in-page live preview). PDFs and multi-page PODs are not supported; only JPEG/PNG/WebP.",
              "Dashboard aggregation loads filtered trips and computes in Python: fine at the stated volume, to be moved to SQL aggregates if volumes grow. (The review queue already filters, orders and paginates in SQL.)",
              "Hindi/Marathi strings were written by the developer and need native-speaker review; speech depends on installed browser voices.",
              "Background Sync cannot upload by itself while the app is closed. Real-Android camera, airplane-mode, GPS-denied, voice and production offline-reload checks are still manual."]),
          P("16. Features deliberately excluded", H1),
          P("Real SMS delivery (mock adapter only), live Tally integration (CSV only), automatic invoice generation/sending, e-way bill or GPS-tracking integrations, signature/stamp authentication, payments, a third role, microservices, "
            "multi-tenant administration, and push notifications."),
          P("17. Future improvements", H1),
          *B(["Calibrate thresholds from a labelled sample of real PODs; track precision of auto-verification and reviewer-override rate.",
              "Server-side session revocation list; shared rate limiter; malware scan on uploads.",
              "SQL-side aggregations and materialised metrics; background worker queue for AI jobs with retries and dead-lettering.",
              "On-device quality guidance (blur / glare / edge detection) before sending; multi-page capture; PDF support.",
              "Scheduled retention runs; field-level encryption for sensitive images; region-pinned storage; accessibility audit and native-speaker localisation review.",
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
