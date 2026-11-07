# Graph Report - RouteProof  (2026-11-05)

## Corpus Check
- Corpus is ~44,914 words - fits in a single context window. You may not need a graph.

## Summary
- 954 nodes · 3132 edges · 45 communities (34 shown, 11 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 59 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Driver PWA Screens
- AI Provider Layer
- App Core & Mock AI
- Billing API & Exports
- DB Models (Alembic)
- API Routers & Auth Deps
- Resource-level Authorization
- POD Service & Audit
- TDD PDF Builder
- Dashboard API
- Docker Compose
- Frontend Services & Test Fixtures
- Render Blueprint
- Auth Endpoints
- Frontend Dependencies
- Security & Driver Links
- Link Resolution
- TypeScript Config
- API Client
- Driver Capture Flow
- Storage Adapters
- E2E Helpers
- Driver Context Hooks
- Runtime Dependencies
- POD Read Endpoints
- Compression & Offline DB
- Root Layout
- Hired-driver Landing
- Driver Queue Page
- NPM Scripts
- Error Handling
- Test Tooling Deps
- Vitest & Playwright Config
- Settings
- ESLint Config
- Service Worker

## God Nodes (most connected - your core abstractions)
1. `cn()` - 41 edges
2. `get_settings()` - 37 edges
3. `react` - 32 edges
4. `MockProvider` - 30 edges
5. `TripDetail()` - 28 edges
6. `Queue()` - 27 edges
7. `aware()` - 26 edges
8. `audit()` - 26 edges
9. `Button()` - 26 edges
10. `make_trip()` - 25 edges

## Surprising Connections (you probably didn't know these)
- `login()` --uses--> `AppError`  [INFERRED]
  backend/app/api/v1/auth.py → backend/app/core/errors.py
- `queue()` --uses--> `TripFilters`  [INFERRED]
  backend/app/api/v1/billing.py → backend/app/repositories/trips.py
- `make_export()` --uses--> `ExportIn`  [INFERRED]
  backend/app/api/v1/billing.py → backend/app/schemas/requests.py
- `invoiced()` --uses--> `InvoicedIn`  [INFERRED]
  backend/app/api/v1/billing.py → backend/app/schemas/requests.py
- `create_link()` --uses--> `DriverLinkIn`  [INFERRED]
  backend/app/api/v1/driver_links.py → backend/app/schemas/requests.py

## Import Cycles
- None detected.

## Communities (45 total, 11 thin omitted)

### Community 0 - "Driver PWA Screens"
Cohesion: 0.08
Nodes (105): CapturePage(), Bar(), DriverLayout(), AuditPage(), Billing(), History(), Queue(), doExport() (+97 more)

### Community 1 - "AI Provider Layer"
Cohesion: 0.05
Nodes (43): AIProvider, AIProviderError, TripContext, _api_message(), ClaudeVisionProvider, get_provider(), ManualProvider, result() (+35 more)

### Community 2 - "App Core & Mock AI"
Cohesion: 0.08
Nodes (49): reset(), create_app(), _uuid(), MockProvider, _f(), render_pod(), _get_or_create(), seed() (+41 more)

### Community 3 - "Billing API & Exports"
Cohesion: 0.12
Nodes (19): download(), _exp_out(), invoiced(), list_exports(), make_export(), queue(), _queue_row(), NotFound() (+11 more)

### Community 4 - "DB Models (Alembic)"
Cohesion: 0.14
Nodes (18): Base, AuditLog, BillingExport, BillingExportItem, Client, DriverLink, Pod, PodExtraction (+10 more)

### Community 5 - "API Routers & Auth Deps"
Cohesion: 0.16
Nodes (9): require_roles(), dep(), get_settings(), get_db(), AppError, Forbidden(), limit(), dep() (+1 more)

### Community 6 - "Resource-level Authorization"
Cohesion: 0.12
Nodes (17): current_user(), load_trip(), link_upload(), import_csv(), list_trips(), options(), parse_dt(), read_limited() (+9 more)

### Community 7 - "POD Service & Audit"
Cohesion: 0.15
Nodes (18): Conflict(), audit(), _apply_decision(), _coerce(), create_pod(), _dup(), _expected(), mark_verified() (+10 more)

### Community 8 - "TDD PDF Builder"
Cohesion: 0.09
Nodes (11): A(), arch_diagram(), arrow(), B(), box(), build(), er_diagram(), P() (+3 more)

### Community 9 - "Dashboard API"
Cohesion: 0.16
Nodes (19): aging(), audit_logs(), clients(), _F, metrics(), missing(), recent(), _avg() (+11 more)

### Community 10 - "Docker Compose"
Cohesion: 0.07
Nodes (27): build, depends_on, env_file, environment, ports, volumes, condition, environment (+19 more)

### Community 11 - "Frontend Services & Test Fixtures"
Cohesion: 0.11
Nodes (25): AuthCtx, Q, extracted, pod(), trip(), AuditRow, BillingRow, BillingStatus (+17 more)

### Community 12 - "Render Blueprint"
Cohesion: 0.07
Nodes (27): databases, databaseName, name, plan, region, user, mountPath, name (+19 more)

### Community 13 - "Auth Endpoints"
Cohesion: 0.11
Nodes (14): login(), logout(), me(), user_out(), my_trips(), my_uploads(), sync(), verify_password() (+6 more)

### Community 14 - "Frontend Dependencies"
Cohesion: 0.11
Nodes (25): devDependencies, jsdom@^30.1.3, @playwright/test@^1.64.1, tailwindcss@^4, @tailwindcss/turbopack@^4, @testing-library/dom@^10.4.2, @testing-library/user-event@^14.6.8, @types/node@^20 (+17 more)

### Community 15 - "Security & Driver Links"
Cohesion: 0.14
Nodes (9): create_link(), create_access_token(), decode_token(), hash_password(), hash_token(), new_link_token(), get_sms_provider(), mask_phone() (+1 more)

### Community 16 - "Link Resolution"
Cohesion: 0.17
Nodes (12): get_link(), _resolve(), _view(), aware(), _extraction_out(), pod_out(), trip_out(), effective_values() (+4 more)

### Community 17 - "TypeScript Config"
Cohesion: 0.11
Nodes (18): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+10 more)

### Community 18 - "API Client"
Cohesion: 0.19
Nodes (14): api(), API_BASE, ApiError, BASE, get(), post(), Q, qs() (+6 more)

### Community 19 - "Driver Capture Flow"
Cohesion: 0.30
Nodes (14): DriverHome(), CaptureFlow(), onFile(), send(), Geo, getPosition(), META, stateFor() (+6 more)

### Community 20 - "Storage Adapters"
Cohesion: 0.15
Nodes (3): LocalStorage, S3Storage, Storage

### Community 21 - "E2E Helpers"
Cohesion: 0.29
Nodes (10): API, apiToken(), asBilling(), asDriver(), captureAndSend(), login(), POD_IMAGE, Rec (+2 more)

### Community 22 - "Driver Context Hooks"
Cohesion: 0.25
Nodes (10): C, Ctx, DriverProvider(), useCaptures(), useOnline(), Key, T, t() (+2 more)

### Community 23 - "Runtime Dependencies"
Cohesion: 0.14
Nodes (14): dependencies, class-variance-authority@^0.7.1, clsx@^2.1.1, lucide-react@^1.68.0, next@16.4.5, react@19.3.0, react-dom@19.3.0, recharts@^3.10.1 (+6 more)

### Community 24 - "POD Read Endpoints"
Cohesion: 0.42
Nodes (7): get_image(), get_pod(), load_pod(), reprocess(), retake(), review(), review_queue()

### Community 25 - "Compression & Offline DB"
Cohesion: 0.22
Nodes (6): compressImage(), MAX_UPLOAD_BYTES, nextAttempt(), toBlob(), captureDb, CaptureStatus

### Community 26 - "Root Layout"
Cohesion: 0.31
Nodes (6): inter, metadata, RootLayout(), viewport, ServiceWorker(), ToastProvider()

### Community 27 - "Hired-driver Landing"
Cohesion: 0.33
Nodes (8): fetchLink(), Inner(), LinkInfo, UploadLanding(), Props, LANGS, startAutoSync(), PodStatus

### Community 28 - "Driver Queue Page"
Cohesion: 0.43
Nodes (7): dstate(), LABEL, QueuePage(), Thumb(), DState, flushQueue(), retryCapture()

### Community 29 - "NPM Scripts"
Cohesion: 0.25
Nodes (8): scripts, build, dev, lint, start, test, test:e2e, typecheck

### Community 30 - "Error Handling"
Cohesion: 0.43
Nodes (6): _body(), install_handlers(), _any(), _app(), _http(), _val()

### Community 31 - "Test Tooling Deps"
Cohesion: 0.29
Nodes (6): fake-indexeddb@^6.2.7, @testing-library/jest-dom@^7.0.1, @testing-library/react@^16.3.3, fake-indexeddb, @testing-library/jest-dom, @testing-library/react

### Community 32 - "Vitest & Playwright Config"
Cohesion: 0.29
Nodes (4): @vitejs/plugin-react@^6.2.1, vitest@^5.1.0, @vitejs/plugin-react, vitest

### Community 34 - "ESLint Config"
Cohesion: 0.33
Nodes (5): eslintConfig, eslint@^9, eslint-config-next@16.4.5, eslint, eslint-config-next

## Knowledge Gaps
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_settings()` connect `API Routers & Auth Deps` to `Settings`, `App Core & Mock AI`, `AI Provider Layer`, `Billing API & Exports`, `Resource-level Authorization`, `POD Service & Audit`, `Dashboard API`, `Security & Driver Links`, `Link Resolution`, `Storage Adapters`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **Are the 20 inferred relationships involving `MockProvider` (e.g. with `AIProviderError` and `TripContext`) actually correct?**
  _`MockProvider` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Should `Driver PWA Screens` be split into smaller, more focused modules?**
  _Cohesion score 0.07501630789302022 - nodes in this community are weakly interconnected._
- **Why does `react` connect `Driver PWA Screens` to `Frontend Dependencies`, `Driver Capture Flow`, `Driver Context Hooks`, `Runtime Dependencies`, `Root Layout`, `Hired-driver Landing`, `Driver Queue Page`, `Test Tooling Deps`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **Should `AI Provider Layer` be split into smaller, more focused modules?**
  _Cohesion score 0.05054945054945055 - nodes in this community are weakly interconnected._
- **Why does `lucide-react` connect `Driver PWA Screens` to `Frontend Dependencies`, `Driver Capture Flow`, `Runtime Dependencies`, `Hired-driver Landing`, `Driver Queue Page`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **Should `App Core & Mock AI` be split into smaller, more focused modules?**
  _Cohesion score 0.0782472613458529 - nodes in this community are weakly interconnected._