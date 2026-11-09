# RouteProof — Proof of Delivery Intelligence Platform

AI-assisted proof-of-delivery (POD) capture, verification and billing-readiness for a full-truckload transporter.
Trip assigned → driver captures POD (works offline) → upload → **vision model extracts fields** → deterministic validation →
human review for exceptions → verified POD → billing queue → Tally-compatible CSV.
The original image stays the source of truth; the AI never authorises an invoice, and invoices are never issued by this system.

| | |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, TypeScript (strict), Tailwind v4, Lucide, Recharts, IndexedDB, PWA service worker |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy 2, Alembic, Argon2, JWT in an HttpOnly cookie (+ CSRF) |
| Data | PostgreSQL (JSONB, UUID, NUMERIC, constraints); SQLite only for unit tests / zero-setup dev |
| Storage | private local-disk adapter or S3-compatible adapter; images only served through authenticated endpoints |
| AI | `AIProvider` abstraction → Claude vision (Anthropic Messages API, forced tool-use JSON), `manual` fallback, deterministic `mock` for tests |

Read **[deployment.md](deployment.md)** to run, seed, demo and deploy. Layout: `backend/app/{api,core,models,schemas,repositories,services/{ai,pods,billing,uploads,notifications}}`,
`frontend/{app,components,hooks,lib,services,types,e2e,tests}`, `scripts/`, `docs/architecture/`.

## What is real and what is mocked
* **Real:** auth/RBAC with resource-level checks, offline capture + idempotent sync, image compression, state machines, deterministic validation,
  review corrections with preserved AI originals, billing eligibility, CSV export with duplicate protection, dashboards from SQL/ORM queries, audit log.
* **Mocked by design (per brief):** SMS delivery (writes a development delivery log; nothing is sent) and Tally (CSV file only, no integration).

## Billing export: what it is and is not
RouteProof produces a **Tally-compatible CSV** for manual or bulk import. It does **not** create invoices inside Tally, and it never
issues invoices itself. Each row links the invoice to its delivery evidence: `trip_reference`, `lr_number`, `eway_bill_number`,
`client_code`/`client_name`, `billing_cycle`, `delivery_date`, `freight_amount_inr`, `pod_reference` (the exact POD attempt, e.g.
`POD-TRP-66141-A2`), `pod_image_reference` (stable `PODIMG-<id>`), `pod_verified_date`, `pod_exceptions` (accepted shortage/damage) and
`pod_evidence_url` (the POD page in RouteProof; requires a staff login). No storage paths or public image URLs are ever written to the file.
To give the client the evidence itself, create a **client POD-view link** (billing queue → *Share PODs*, export history → *Client link*,
or *Client POD links*): read-only, expiring, revocable, scoped to one client's trips or billing cycle, showing only verified PODs, with
every view audited. It is a separate token type from the hired-driver upload link, which can only write.

## Turnaround metrics
The dashboard reports, from the delivery date (business time zone): delivery → POD received, → verified POD, → billing export, and
→ invoice recorded. The last uses the invoice date a billing executive enters when recording the invoice reference; an export is never
counted as an invoice. Every figure shows its sample size and delivery-date period, so averages over a few seeded trips are not mistaken
for operational KPIs.

## AI evaluation
`backend/app/services/ai/eval_set.py` holds a labelled set of 31 POD variants (printed/handwritten LRs, LR formats, Hindi/Marathi/English,
faint/partial/moved/missing stamps, `600 bags`/`600 BAG`/`6 MT`/`600 cartons`, shortage and damage remarks in different places, folded,
tilted, shadowed and blurred photos, missing dates, late uploads) with the expected fields and routing decision for each. CI checks the
routing of every case; `python scripts/evaluate_pods.py` runs the real model and reports field accuracy separately from the
auto-verification rate, including `auto_verified_with_misread_fields`, which must stay empty. Synthetic documents are not proof of real-world
accuracy: add consented, anonymised real photos with `--manifest` before changing the confidence threshold, and never lower it just to
auto-verify more PODs.
* **Needs your credentials:** the live vision model (`AI_API_KEY`), hosting, and a GitHub remote. See deployment.md for what was and was not verified.

## Tests
`backend`: 167 pytest (+1 opt-in live-model test) · `frontend`: 53 Vitest · e2e: 16 Playwright (offline capture surviving an app restart,
lost-response retry, server timeout, sign-out with unsent photos, hired-driver link journey, client view + revocation, review → CSV → audit,
retake cap, AI timeout, authorization).

**Still to do by hand on a real Android phone** (automation cannot prove camera or device-storage behaviour): the camera button opens the
rear camera; a capture taken in airplane mode survives killing the app and sends once after reconnecting; GPS denied still saves the photo;
the Hindi/Marathi voice prompts play (they need an installed hi-IN/mr-IN voice; otherwise the screen text is the fallback); and an
offline *reload* works against a production build (`npm run build && npm start`; the service worker is not active in `next dev`).
