# RouteProof — Deployment & Run Guide

> **Status of this guide (read first).** Everything in sections 1–9 was executed locally on Windows with SQLite for the automated tests.
> **Verified locally:** PostgreSQL 16 in Docker (migration, seed, full pytest suite) and live Claude extraction (`claude-sonnet-5-5`, three synthetic documents; an end-to-end upload auto-verified).
> **Not yet performed:** any cloud deployment. Section 10 gives the exact steps; no live URL exists yet and none is claimed.
> **Mocked by design:** Tally (CSV file only) and SMS (a development delivery log; nothing is sent).

GitHub repository: **https://github.com/Mmukund-31/RouteProof**
Live frontend URL: **`<not deployed yet>`** · Live backend health URL: **`<not deployed yet>`** (`/health`)

---

## 1. Prerequisites

| Tool | Version used | Notes |
|---|---|---|
| Python | 3.12+ (developed on 3.14) | `python -m venv` |
| Node.js | 20+ (developed on 24) | npm |
| PostgreSQL | 16 | via Docker or native; needed for production-like runs |
| Docker Desktop | optional | `docker compose up db` for Postgres |
| Anthropic API key | for live AI | https://console.anthropic.com |

## 2. Clone

```bash
git clone https://github.com/Mmukund-31/RouteProof.git routeproof
cd routeproof
```

## 3. Backend install

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## 4. PostgreSQL

```bash
# from repo root
docker compose up -d db          # postgres:16 on localhost:5433 (user/db: routeproof; 5433 avoids clashing with a local PostgreSQL)
# DATABASE_URL=postgresql://routeproof:routeproof_local_only@localhost:5433/routeproof
```
Local-only credentials are in `docker-compose.yml` (`routeproof_local_only`); change them for anything shared.
Without Docker you may run the backend against SQLite for development by leaving `DATABASE_URL=sqlite:///./routeproof_dev.db`
(JSONB columns fall back to JSON; this mode is for local convenience and unit tests only).

## 5. Environment variables

Copy `.env.example` to `backend/.env` (backend) and `frontend/.env.local` (frontend). **Names only — set your own values:**

`DATABASE_URL`, `JWT_SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `SESSION_MAX_HOURS`, `COOKIE_SAMESITE`, `COOKIE_SECURE`,
`TRUST_PROXY_HEADERS`, `AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL`, `AI_CONFIDENCE_THRESHOLD`, `AI_MAX_ATTEMPTS`, `AI_RETRY_BACKOFF_SECONDS`,
`AI_PROCESSING_STALE_MINUTES`, `MAINTENANCE_INTERVAL_SECONDS`, `ORPHAN_GRACE_HOURS`,
`STORAGE_PROVIDER`, `STORAGE_BUCKET`, `STORAGE_ENDPOINT`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`, `NEXT_PUBLIC_API_URL`, `API_PROXY_TARGET`,
`CORS_ALLOWED_ORIGINS`, `UPLOAD_MAX_SIZE_BYTES`, `UPLOAD_LINK_EXPIRY_MINUTES`, `PUBLIC_APP_URL`, `APP_ENV`, `LOG_LEVEL`, `LOG_FORMAT`, `DATA_MODE`.

Minimum for a local live-AI demo: `DATABASE_URL`, `AI_PROVIDER=claude`, `AI_API_KEY`, `NEXT_PUBLIC_API_URL=http://localhost:8000`.
With `APP_ENV=production` the backend refuses to start unless `JWT_SECRET_KEY` (≥32 chars), `AI_API_KEY` (when `AI_PROVIDER=claude`), a PostgreSQL `DATABASE_URL`
and (for `STORAGE_PROVIDER=s3`) bucket credentials are set, printing a clear configuration error.

## 6. Migrations

```bash
cd backend
alembic upgrade head
```

## 7. Seed data (idempotent — safe to run twice)

```bash
python ../scripts/seed_data.py              # users, 3 clients, vehicles, 3 client scenarios + 34 fictional trips, exports, audit
python ../scripts/seed_data.py --users-only # users/clients/vehicles only (clean slate for real use)
python ../scripts/generate_demo_pods.py     # one photo per sample trip, printed with that trip's exact seeded values (date read from the DB)
python ../scripts/generate_demo_pods.py --lr LR-66162 --consignee "Nashik Retail Depot" --qty 600 --unit bags --date DD/MM/YYYY  # 6 scenarios for another trip
```
The seeded AI extraction rows are labelled `model_provider = seed-data` and the review screen says so (they are fixtures, not model
output). Documents you upload yourself are processed by the configured live model. Running the seed twice changes nothing.
In production the seed refuses to create the public demo accounts unless `ALLOW_DEMO_ACCOUNTS=true` (set only for a public demo);
the container seeds only when `SEED_ON_START=true`.

## 8. Run locally

```bash
# terminal 1
cd backend && uvicorn app.main:app --reload --port 8000     # http://localhost:8000/health , /docs
# terminal 2
cd frontend && npm install && npm run dev                    # http://localhost:3000
```

## 9. Demo credentials (public demo — **non-production**, fictional people)

| Role | Email | Password |
|---|---|---|
| Billing executive | `billing@routeproof.demo` | `Demo@12345` |
| Driver (Marathi default) | `driver1@routeproof.demo` | `Demo@12345` |
| Driver (Hindi default) | `driver3@routeproof.demo` (assigned TRP-66141) | `Demo@12345` |
| More drivers | `driver2…driver6@routeproof.demo` | `Demo@12345` |

Rotate or delete these accounts before any real use.

### Demonstrate the main workflow (≈5 minutes)

1. **Billing**: sign in → *Dashboard* (note the "Seeded demo data" badge) → *Missing PODs* → pick a trip with nothing on file (e.g. **TRP-66162**, Nashik, LR-66162).
   The three client scenarios are pre-seeded: **TRP-66120** verified, **TRP-66134** retake requested (stamp not visible), **TRP-66141** in review (short by 6 cartons).
2. Make photos that match that trip, then switch to the **Driver**:
   `python scripts/generate_demo_pods.py --lr LR-66162 --consignee "Nashik Retail Depot" --qty 600 --unit bags --client "Company B (Cement)" --vehicle "MH20 EF 3303" --date 31/10/2026`
   (values come from the trip's detail page: LR, consignee, expected quantity/unit, delivery date; the six files in `demo_pods/` are the clear, missing-stamp, blurred, wrong-LR, shortage and damage scenarios).
   Sign in as the trip's driver (phone or Chrome device mode, second browser profile) → tap the trip → *Take photo* → pick `demo_pods/5_shortage_remark.jpg` → *Send*.
   The photo is compressed to <300 KB in the browser. Switch Chrome DevTools → Network → *Offline* before *Send* to see "saved, will send when online"; switch back to *No throttling* and it syncs by itself.
3. The **live vision model** reads the document; a shortage remark routes it to **Review queue** (never auto-approved). `1_clear_signed_stamped.jpg` should verify with no human step.
4. **Billing** → *Review queue* → *Review* → compare Expected vs AI-read, correct a field (a reason is mandatory; the AI original stays visible) → **Approve**.
5. *Billing queue* → the trip appears (verified only) → select → **Export CSV** (downloads). Try exporting it again: refused unless you explicitly re-export with a reason.
6. *Audit history* shows each step.
7. Photos to try from `demo_pods/`: clear, missing stamp (→ retake), blurred (→ retake), wrong LR (→ review), shortage (→ review), damage (→ review).

### Hired-driver upload link (no driver account)

8. **Billing** → *Trips* → open a hired-vehicle trip with no POD (or **TRP-66141**-style hired trip) → *Hired-driver upload links* → enter a phone number → **Create link**.
   The link is shown once (only its SHA-256 hash is stored); the mock SMS log row says *LOGGED_NOT_SENT* — nothing is sent.
9. Copy the `/upload/<token>` URL and open it in a **private/incognito window** (no session cookie). The page shows only that trip's LR and destination.
10. *Take photo* → pick a photo from `demo_pods/` → *Send*. The POD uploads without any login, is processed by AI and appears on the trip page and
    in the review queue (source: SMS link). The full-resolution original follows as a second upload. Revoking the link (*Revoke*) makes the page answer "expired".

### Client POD-view link (read-only evidence for a client)

11. **Billing** → *Billing* → select one or more verified trips of one client (e.g. **TRP-66120**) → **Share PODs** (or *Export history* → *Client link*) → choose expiry → **Create**. Copy the `/view/<token>` URL.
12. Open it in a **separate private window**. Without logging in, the client sees trip reference, LR, delivery date and POD reference, and can open the
    **verified POD image**. No driver name, phone, GPS, freight or other clients' trips appear; unverified trips show *Pending* with no image.
13. Back in the workspace → *Client POD links* → the access count has gone up (every open and image view is audited) → **Revoke**.
14. Reload the client window: access is rejected (*this link has expired or was withdrawn*, HTTP 410), and the denied attempt is recorded in the audit log.

## 10. Production deployment

The repository ships a Render blueprint (`render.yaml`) for the **API + managed PostgreSQL + persistent disk**, and the frontend is a standard Next.js app (Vercel or a second Render web service).
**Hosting region:** Render has no India region; the blueprint uses Singapore, the closest. *Do not describe a deployment as India-resident unless you move storage and database to an Indian region* (e.g. AWS ap-south-1 via `STORAGE_PROVIDER=s3`, managed Postgres in Mumbai).

1. Push the repo to GitHub.
2. **Render** → *New → Blueprint* → select the repo → set secrets: `AI_API_KEY` (Anthropic), `CORS_ALLOWED_ORIGINS` and `PUBLIC_APP_URL` (your frontend URL).
   `JWT_SECRET_KEY` is generated. The container runs `alembic upgrade head`, then the idempotent seed (set `SEED_ON_START=false` once real data exists), then uvicorn.
   Health check path: `/health`.
3. **Vercel** (or Render static/web) for `frontend/`: set `API_PROXY_TARGET=https://<your-api>.onrender.com` and `NEXT_PUBLIC_API_URL=` (empty).
   The browser session is an **HttpOnly cookie**; proxying `/api/v1` through the frontend keeps it first-party (`*.onrender.com` and
   `*.vercel.app` are different sites, so a direct cross-site API would have its cookie blocked). On the API set `TRUST_PROXY_HEADERS=true`
   so login rate limits see the real client address, and keep `CORS_ALLOWED_ORIGINS` = the frontend URL.
4. Verify from a clean browser profile: open `<API>/health` → `{"status":"ok","database":true,...}`; log in with the demo accounts; upload one POD end to end.
5. Optional S3-compatible private storage: `STORAGE_PROVIDER=s3`, `STORAGE_BUCKET`, `STORAGE_ENDPOINT`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY` (bucket must be private; images are only served through authenticated API calls).
6. Render's persistent disk requires a single instance; for multiple instances use S3 storage and a shared rate limiter (the in-memory limiter is per-instance).

### Operations

| Task | How |
|---|---|
| Schema upgrade after pulling | `alembic upgrade head` (`0002`: provenance/processing/exception columns + backfill; `0003`: client view links, upload sizes, invoice date, driver-link revocation; both safe to re-run) |
| Stuck POD (AI_PROCESSING) | Swept automatically every `MAINTENANCE_INTERVAL_SECONDS`; stale ones go to *Needs review* as `PROCESSING_STALLED`, never-started uploads are re-processed. On demand: `POST /api/v1/pods/maintenance/recover`, or *Re-run AI extraction* on the POD |
| Orphaned files | `python -m app.services.uploads.cleanup` (dry run) then `--delete`. Failed uploads/exports already delete their own files; this catches crashes in between |
| Evaluate extraction on labelled PODs | `python ../scripts/evaluate_pods.py [--manifest real/labels.json]`; `--render-only DIR` writes the synthetic documents to look at |
| Revoke a shared link | Client links: *Client POD links* → Revoke. Hired-driver links: trip page → *Hired-driver upload links* → Revoke |
| Calibrate the confidence threshold | `python ../scripts/calibrate_confidence.py --samples 120 --out calibration.json` (real model; prints coverage and error rate per threshold) |
| Retention and erasure | `python -m app.services.retention` (dry run) / `--apply` / `--erase-pod <uuid> --reason "<request ref>"`; see docs/data-protection.md |
| Trace one request | Every response has `X-Request-ID` (also in error bodies); AI runs log a `processing_id` that is stored on the extraction row |

**Known limitations.** Sessions are stateless JWTs in an HttpOnly cookie: logout clears the cookie, but a stolen token stays valid until it
expires (≤ `ACCESS_TOKEN_EXPIRE_MINUTES` idle, ≤ `SESSION_MAX_HOURS` total); a server-side denylist would be needed for instant revocation.
The CSP allows `'unsafe-inline'` scripts (required by Next.js without nonces); the app renders no raw HTML. Export row-locking (`SELECT … FOR UPDATE`)
is enforced on PostgreSQL; SQLite (dev/tests only) serialises writes instead. AI processing runs in-process (FastAPI BackgroundTasks) with
database-backed recovery, not a durable queue.

## 11. Tests

```bash
cd backend  && python -m pytest -q                 # 204 collected: 201 passed, 2 opt-in skipped, 1 see note (SQLite, mock AI); RUN_LIVE_AI_EVAL=1 adds the real-model evaluation
cd backend  && TEST_DATABASE_URL=postgresql://routeproof:routeproof_local_only@localhost:5433/routeproof_test python -m pytest -q   # same suite on PostgreSQL (create that DB first)
cd frontend && npm run test                        # 57 Vitest tests
cd frontend && npx playwright install chromium && npm run test:e2e   # 16 e2e tests (own servers on :8100/:3100, mock AI)
cd frontend && npm run lint && npm run typecheck && npm run build
```

Last local run (2026-11-10, Docker `python:3.12-slim`): backend 201 passed / 2 skipped on SQLite **and** on PostgreSQL 16; frontend 57/57 Vitest.
`test_demo_document_generator_prints_the_seeded_values` failed only because that run copied `backend/` without the sibling `scripts/` folder; run from a full checkout.
The 16 Playwright specs were not re-run for this revision. CI (`.github/workflows/ci.yml`) runs all of these on every push and pull request to `main`.

## 12. Troubleshooting

| Symptom | Fix |
|---|---|
| `Invalid configuration: JWT_SECRET_KEY must be set…` | `APP_ENV=production` requires real secrets; see §5 |
| Uploaded POD lands in *Needs review* with `AI_ERROR … not_configured` | `AI_API_KEY` missing/invalid (or `AI_PROVIDER=manual`). Fix and use *Re-run AI extraction* on the POD |
| Browser shows CORS errors | add the exact frontend origin to `CORS_ALLOWED_ORIGINS` (no trailing slash) |
| Login works but pages bounce to `/login` | The session is an **HttpOnly cookie** (`rp_session`), not browser storage. It expires after 60 min idle (`ACCESS_TOKEN_EXPIRE_MINUTES`, refreshed while in use) or 12 h after login (`SESSION_MAX_HOURS`); sign in again. If it happens immediately, the browser is dropping the cookie: in production set `API_PROXY_TARGET` on the frontend and leave `NEXT_PUBLIC_API_URL` empty so `/api/v1` is proxied first-party (a cross-site API cookie is blocked), and set `COOKIE_SECURE=true` behind HTTPS |
| Writes fail with `403 csrf_failed` | Every POST from the browser must send `X-CSRF-Token` matching the readable `rp_csrf` cookie (the app does this). Usually the cookie came from another origin or an old session: sign out and back in, and use the proxied same-origin `/api/v1` |
| Camera button does nothing on desktop | desktop browsers open a file picker; on phones it opens the camera app. GPS/camera need HTTPS (or localhost) |
| Offline queue never syncs | check the *Upload queue* screen for the error; `FAILED` items (e.g. a POD already verified) need *Discard*; transient items retry every 20 s and on reconnect |
| `psycopg` build errors on exotic Python versions | use Python 3.12 (the Dockerfile does) |
| Windows: DLL blocked by Application Control | the app avoids the Anthropic SDK for this reason; it calls the REST API over `httpx` |
