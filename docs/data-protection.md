# RouteProof — data protection notes (DPDP Act awareness)

> **Not a compliance statement.** This document describes what RouteProof collects, why, who can see it, how long it is
> kept and which technical controls exist. Having these controls does not make a deployment compliant with the Digital
> Personal Data Protection Act, 2023 or any other law. A real deployment needs a legal and operational review: lawful
> purpose and notices, contracts with clients and processors, retention periods, grievance handling and breach response.

## 1. What is collected and why

| Data | Whose | Where it comes from | Purpose | Who can see it |
|---|---|---|---|---|
| Name, work email, role, preferred language, password hash (Argon2) | Staff and company drivers | Account set-up | Sign-in, role-based access, driver UI language | Billing executives see names; nobody sees password hashes |
| Driver phone number | Company drivers | Account set-up | Lets the operations team call a driver about a missing POD | Billing executives, only on the missing-POD list for company drivers |
| Hired-driver phone number | Hired drivers (no account) | Typed when sending an upload link | Sending the link (SMS is mocked in this build) | Stored **masked only** (last 4 digits); never stored or logged in full |
| POD photo (compressed + original) | Consignee staff (signature, stamp, handwriting), sometimes the driver | Driver capture | Delivery evidence for billing | Billing executives; the assigned driver; a client, only through a client link and only once verified |
| Device capture time, GPS coordinates or the reason they are missing | Driver | The phone at capture | Provenance of the evidence (not proof of presence) | Billing executives; the assigned driver |
| Extracted POD fields (LR, consignee name, quantity, date, remarks) | Consignee business; individuals only incidentally | AI extraction / human correction | Validation and billing | Billing executives |
| Trip, client, freight, invoice references | Business data | TMS / CSV import | Billing | Billing executives (drivers never see freight) |
| Audit log (who did what, when) | Staff, drivers, link users | The application | Accountability, dispute resolution | Billing executives |
| Client-link access records | Client staff (anonymous token holder) | Opening a client view link | Knowing who accessed evidence and when | Billing executives |

Not collected: Aadhaar, licence or vehicle-owner identity documents, continuous location tracking, contacts, device
identifiers, analytics or advertising trackers. There is no consent form on the driver capture screen by design: the
driver notice belongs in onboarding (company drivers: employment/contractor onboarding; hired drivers: the transport
contract and the SMS text), not in the one-button capture flow.

## 2. Access roles

| Action | Billing executive | Company driver | Hired driver (link) | Client (view link) | Anonymous |
|---|---|---|---|---|---|
| See trips | All | Own assigned trips | The one linked trip (LR, destination, status) | Linked trips/cycle of their own company | — |
| See POD images | All | Own trips | — | Verified PODs in scope | — |
| Upload a POD | Staff upload | Own trips | The one linked trip | — | — |
| Review, correct, approve, export | Yes | — | — | — | — |
| Freight, invoices, other clients | Yes | Never | Never | Never | — |

Enforced in code: `backend/app/api/deps.py` (`require_roles`, `load_trip` resource checks, 404 instead of 403 so other
trips' existence is not revealed), `backend/app/api/v1/driver_links.py`, `backend/app/services/client_links.py`.
Verified by `backend/tests/test_security_data.py`, which calls **every** documented endpoint unauthenticated and as a
different driver.

## 3. Security controls

| Control | Where |
|---|---|
| Passwords hashed with Argon2; timing-equalised login for unknown emails | `app/core/security.py`, `app/api/v1/auth.py` |
| Browser session in an HttpOnly, SameSite cookie; session-bound CSRF token on every write; 60-min idle / 12-h absolute expiry | `app/api/deps.py`, `frontend/lib/api.ts` |
| Production refuses: weak JWT secret, SQLite, non-secure cookies, non-HTTPS app URL, wildcard or non-HTTPS CORS, demo accounts (unless `ALLOW_DEMO_ACCOUNTS=true`) | `app/core/config.py`, `app/services/seed.py` |
| Private storage; images only through authenticated endpoints with `Cache-Control: private, no-store` | `app/api/v1/pods.py`, `app/services/uploads/storage.py` |
| Upload and client-view links: 256-bit random tokens, stored as SHA-256 hashes, expiring, revocable, scoped (one trip / one client), rate-limited | `app/api/v1/driver_links.py`, `app/services/client_links.py`, `app/core/ratelimit.py` |
| Clients only ever see *verified* PODs of their own trips; no driver, phone, freight or GPS | `app/services/client_links.py` |
| Audit of uploads, reviews, corrections, exception approvals, exports, link creation, viewing, expiry, revocation and denied access | `app/services/audit.py` and callers |
| Logs: structured, allow-listed fields; link tokens, bearer tokens and phone numbers redacted from every log line (including uvicorn's); uvicorn access log disabled in the container | `app/core/observability.py`, `backend/Dockerfile` |
| Strict CSP and security headers (frontend and API); token pages send no Referer and are not indexed or cached | `frontend/next.config.ts`, `app/main.py` |
| Service worker never caches `/api/` (private images, CSVs) | `frontend/public/sw.js` |
| No secrets, databases, storage or generated artefacts in Git (checked by a test) | `.gitignore`, `backend/tests/test_security_data.py` |

## 4. Retention and deletion

Placeholders, to be set from legal and accounting advice (GST and commercial record-keeping rules may require years):

| Data | Default | Setting |
|---|---|---|
| Verified POD images of invoiced trips | 2,920 days (~8 years) after invoicing | `POD_IMAGE_RETENTION_DAYS` |
| Rejected / retaken POD attempts (never billing evidence) | 365 days after upload | `SUPERSEDED_IMAGE_RETENTION_DAYS` |
| Access records (link opened, image viewed, denied access) | 365 days | `ACCESS_LOG_RETENTION_DAYS` |
| Trip, POD metadata, extraction values, reviews, state-change audit | Kept with the business record | — |
| Expired client / driver links | Kept (hash only, no usable token) with their audit trail | — |

The deletion workflow is deliberately **manual and audited**; nothing is deleted on a timer:

```bash
cd backend
python -m app.services.retention                      # dry run: what the schedule would purge
python -m app.services.retention --apply              # purge images and access logs past retention
python -m app.services.retention --erase-pod <uuid> --reason "DPR-2026-014, approved by <name>"   # one POD
```

* Images are deleted from storage; the POD row records `images_purged_at` and the reason, image endpoints answer 410,
  and the client view stops offering the image. The rest of the record is kept.
* **Legal hold:** images of a trip that is not yet invoiced, or that has an open POD (uploaded, processing, in review),
  are never purged by the schedule. Targeted erasure of such a POD needs `--override-hold`, which is recorded.
* Every purge writes an audit row (`pod.images_purged`, `retention.access_logs_purged`) without the deleted content.
* Backups: purging the live store does not purge backups; align backup retention with the same periods.

## 5. Data-principal requests

A request (access, correction, erasure, grievance) is handled by a named person in the business, not by the app
automatically:

1. **Verify identity** outside the app (for a driver: employee/contractor records; for consignee staff: through the client).
2. **Access:** export what is held. The trip page, the POD page and `/api/v1/trips/{id}/history` show every record and
   audit event for a trip; driver account data is in the users table.
3. **Correction:** extracted values are corrected through the review screen (reason required, original preserved);
   account details by an administrator.
4. **Erasure:** decide first whether the record must be kept (billing, tax, disputes). If erasure is approved, run
   `--erase-pod` with the request reference as the reason. Account removal: deactivate the user (`is_active=false`)
   so the audit trail keeps its integrity.
5. **Record** the request, the decision and the date in the grievance register (outside the app).

## 6. Processors and transfers

* **AI provider:** when `AI_PROVIDER=claude`, each POD photo and the trip's LR number, consignee name and client name
  are sent to Anthropic's API for extraction. Review the provider's commercial data-processing terms and retention
  settings, and cover this in the client and driver notices. `AI_PROVIDER=manual` sends nothing out.
* **Hosting:** the Render blueprint uses Singapore (no India region). Data then resides outside India; do not describe
  such a deployment as India-resident. For residency, use an Indian region for the database and storage.
* **SMS:** mocked in this build (nothing is sent). A real SMS provider would receive hired drivers' phone numbers and the link.

## 7. Incidents

If a link, token, database or storage bucket may have leaked: revoke affected client and driver links (Billing →
Client POD links; trip page → upload links), rotate `JWT_SECRET_KEY` (this signs everyone out and invalidates all CSRF
tokens), rotate storage and AI keys, review the audit log for access in the period, and follow the business's breach
procedure for notification.
