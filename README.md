# RouteProof — Proof of Delivery Intelligence Platform

AI-assisted proof-of-delivery (POD) capture, verification and billing-readiness for a full-truckload transporter.
Trip assigned → driver captures POD (works offline) → upload → **vision model extracts fields** → deterministic validation →
human review for exceptions → verified POD → billing queue → Tally-compatible CSV.
The original image stays the source of truth; the AI never authorises an invoice, and invoices are never issued by this system.

| | |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, TypeScript (strict), Tailwind v4, Lucide, Recharts, IndexedDB, PWA service worker |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy 2, Alembic, Argon2, JWT |
| Data | PostgreSQL (JSONB, UUID, NUMERIC, constraints); SQLite only for unit tests / zero-setup dev |
| Storage | private local-disk adapter or S3-compatible adapter; images only served through authenticated endpoints |
| AI | `AIProvider` abstraction → Claude vision (Anthropic Messages API, forced tool-use JSON), `manual` fallback, deterministic `mock` for tests |

Read **[deployment.md](deployment.md)** to run, seed, demo and deploy. Layout: `backend/app/{api,core,models,schemas,repositories,services/{ai,pods,billing,uploads,notifications}}`,
`frontend/{app,components,hooks,lib,services,types,e2e,tests}`, `scripts/`, `docs/architecture/`.

## What is real and what is mocked
* **Real:** auth/RBAC with resource-level checks, offline capture + idempotent sync, image compression, state machines, deterministic validation,
  review corrections with preserved AI originals, billing eligibility, CSV export with duplicate protection, dashboards from SQL/ORM queries, audit log.
* **Mocked by design (per brief):** SMS delivery (writes a development delivery log; nothing is sent) and Tally (CSV file only, no integration).
* **Needs your credentials:** the live vision model (`AI_API_KEY`), hosting, and a GitHub remote. See deployment.md for what was and was not verified.

## Tests
`backend`: 58 pytest · `frontend`: 25 Vitest · e2e: 9 Playwright (offline mode, reconnection, duplicate retry, review → CSV → audit, retake cap, AI timeout, authorization).
