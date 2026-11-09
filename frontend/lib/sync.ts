import { API_BASE, ApiError, api } from "@/lib/api";
import { captureDb, type Capture, type DriverErrorKind } from "@/lib/offline-db";

/** Translate a technical failure into one of a few plain situations the driver can act on. */
export function driverErrorKind(e: unknown): DriverErrorKind {
  if (!(e instanceof ApiError)) return "generic";
  if (e.status === 0 || e.status === 408 || e.status === 429 || e.status >= 500) return "network";
  if (e.status === 401) return "session";
  if (e.status === 409) return "alreadySent";
  if (e.status === 410) return "linkExpired";
  if ([400, 413, 415, 422].includes(e.status)) return "badPhoto";
  return "generic";
}

/**
 * Offline upload queue.
 *
 * 1. A capture is written to IndexedDB (original + compressed blob + metadata) before any network call, with an
 *    idempotency key generated at capture time and reused on every retry, so it survives reloads, app restarts and
 *    "the server got it but the response was lost": the retry returns the same POD instead of creating another.
 * 2. The compressed copy (< 300 KB) is sent first. Once the server acknowledges it, the full-resolution original is
 *    sent as a second, lower-priority step; it is released from the phone only after that is acknowledged too.
 * 3. Captures belong to the driver who took them: they are only sent while that driver is signed in (or via the
 *    hired-driver link they were captured on), and signing out never deletes them.
 */
const MANUAL_RETRY_AFTER = 3;
const UPLOAD_TIMEOUT_MS = 60_000;
const ORIGINAL_TIMEOUT_MS = 180_000;
const MAX_ORIGINAL_ATTEMPTS = 5;
let running: Promise<void> | null = null;
let owner: string | null = null;

/** Called by the auth layer: whose captures may be uploaded right now (null = nobody signed in). */
export function setQueueOwner(userId: string | null) { owner = userId; }

/** May this capture be sent in the current session? Link captures carry their own credential. */
export function sendable(c: Capture, currentOwner: string | null = owner): boolean {
  if (c.linkToken) return true;
  if (!currentOwner) return false;
  return !c.userId || c.userId === currentOwner;
}

export function buildForm(c: Capture): FormData {
  const f = new FormData();
  f.append("file", c.compressed!, `${c.id}.jpg`);
  f.append("idempotency_key", c.id); // identical on every retry -> server returns the same POD
  f.append("captured_at", c.capturedAt);
  if (c.latitude !== undefined) f.append("latitude", String(c.latitude));
  if (c.longitude !== undefined) f.append("longitude", String(c.longitude));
  if (c.accuracy !== undefined) f.append("accuracy", String(c.accuracy));
  if (c.locationStatus) f.append("location_status", c.locationStatus);
  return f;
}

interface UploadResp { created: boolean; pod: { id: string; verification_status: string } }

function withTimeout(ms: number): { signal: AbortSignal; done: () => void } {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  return { signal: ctl.signal, done: () => clearTimeout(t) };
}

async function linkPost<T>(path: string, body: FormData, ms: number): Promise<T> {
  const to = withTimeout(ms);
  let res: Response;
  try { res = await fetch(`${API_BASE}/api/v1${path}`, { method: "POST", body, signal: to.signal }); }
  catch { throw new ApiError(0, "network", "Cannot reach the server"); }
  finally { to.done(); }
  if (!res.ok) {
    const b = await res.json().catch(() => ({}));
    throw new ApiError(res.status, b?.error?.code ?? "error", b?.error?.message ?? "Upload failed");
  }
  return res.json();
}

async function authedPost<T>(path: string, body: FormData, ms: number): Promise<T> {
  const to = withTimeout(ms);
  try { return await api<T>(path, { method: "POST", body, signal: to.signal }); }
  finally { to.done(); }
}

export async function uploadCapture(c: Capture): Promise<UploadResp> {
  // Hired-driver flow: no session, access is scoped by the link token to a single trip.
  return c.linkToken
    ? linkPost<UploadResp>(`/driver-links/${c.linkToken}/pods`, buildForm(c), UPLOAD_TIMEOUT_MS)
    : authedPost<UploadResp>(`/trips/${c.tripId}/pods`, buildForm(c), UPLOAD_TIMEOUT_MS);
}

export async function uploadOriginalCapture(c: Capture): Promise<unknown> {
  const f = new FormData();
  f.append("file", c.original!, `${c.id}-original.jpg`);
  return c.linkToken
    ? linkPost(`/driver-links/${c.linkToken}/pods/${c.podId}/original`, f, ORIGINAL_TIMEOUT_MS)
    : authedPost(`/pods/${c.podId}/original`, f, ORIGINAL_TIMEOUT_MS);
}

/** Originals are large: skip them on data-saver or 2G and try again on a better connection. */
export function goodConnectionForOriginal(): boolean {
  const n = (typeof navigator !== "undefined" ? navigator : undefined) as (Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }) | undefined;
  const c = n?.connection;
  return !(c?.saveData || c?.effectiveType === "slow-2g" || c?.effectiveType === "2g");
}

const offline = () => typeof navigator !== "undefined" && !navigator.onLine;

/** Uploads pending captures one at a time, single-flight. Safe to call from many triggers (online event, timer, button). */
export function flushQueue(upload: typeof uploadCapture = uploadCapture,
  uploadOriginal: typeof uploadOriginalCapture = uploadOriginalCapture): Promise<void> {
  if (running) return running;
  const p: Promise<void> = (async () => {
    await Promise.resolve(); // guarantee `running` is assigned before any early return releases it
    if (offline()) return;
    const all = (await captureDb.all()).filter((c) => sendable(c));
    // Oldest first, so a driver's captures reach the office in the order they were taken.
    const todo = all.filter((c) => c.status === "PENDING" || c.status === "UPLOADING" || c.status === "RETRY_REQUIRED").reverse();
    for (const c of todo) {
      if (offline()) return;
      if (!c.compressed) { await captureDb.update(c.id, { status: "FAILED", lastError: "Image data missing" }); continue; }
      await captureDb.update(c.id, { status: "UPLOADING", lastError: undefined, lastErrorKind: undefined });
      try {
        const r = await upload(c);
        // Server acknowledged the compressed copy: release it; keep the original until it is acknowledged as well.
        await captureDb.update(c.id, {
          status: "UPLOADED", podId: r.pod.id, serverStatus: r.pod.verification_status, ackedAt: new Date().toISOString(),
          compressed: undefined, originalStatus: c.original ? "PENDING" : undefined,
        });
      } catch (e) {
        const err = e as ApiError;
        if (err instanceof ApiError && err.status === 401) {
          // Session expired while the capture waited offline: keep it (and its original) until the driver signs in.
          await captureDb.update(c.id, { status: "RETRY_REQUIRED", lastError: "Sign in again to send this photo", lastErrorKind: "session" });
          return;
        }
        if (err instanceof ApiError && err.permanent) {
          await captureDb.update(c.id, { status: "FAILED", lastError: err.message, lastErrorKind: driverErrorKind(err), retryCount: c.retryCount + 1 });
        } else {
          const n = c.retryCount + 1;
          await captureDb.update(c.id, { status: n >= MANUAL_RETRY_AFTER ? "RETRY_REQUIRED" : "PENDING", retryCount: n, lastError: (e as Error).message,
            lastErrorKind: driverErrorKind(e) });
        }
      }
    }
    // Second, lower-priority pass: full-resolution originals for PODs the server already holds.
    if (!goodConnectionForOriginal()) return;
    const originals = (await captureDb.all()).filter((c) => sendable(c) && c.status === "UPLOADED" && c.podId && c.original
      && (c.originalStatus === "PENDING" || c.originalStatus === undefined)).reverse();
    for (const c of originals) {
      if (offline()) return;
      try {
        await uploadOriginal(c);
        await captureDb.update(c.id, { original: undefined, originalStatus: "UPLOADED" });
      } catch (e) {
        const err = e as ApiError;
        if (err instanceof ApiError && err.status === 401) return;
        const n = (c.originalAttempts ?? 0) + 1;
        // Give up quietly after repeated or permanent failures: the verified compressed copy is already on file,
        // and the original stays on the phone (visible in the queue) rather than being thrown away.
        const stop = (err instanceof ApiError && err.permanent) || n >= MAX_ORIGINAL_ATTEMPTS;
        await captureDb.update(c.id, { originalAttempts: n, originalStatus: stop ? "FAILED" : "PENDING" });
      }
    }
  })();
  running = p;
  const release = () => { if (running === p) running = null; };
  p.then(release, release); // release the single-flight lock whether the run succeeded or threw
  return p;
}

export async function retryCapture(id: string) {
  await captureDb.update(id, { status: "PENDING", lastError: undefined, lastErrorKind: undefined, retryCount: 0 });
  return flushQueue();
}

/** Captures still waiting for the server (used to warn before signing out). */
export async function pendingFor(userId: string | null): Promise<number> {
  return (await captureDb.all()).filter((c) => !c.linkToken && c.status !== "UPLOADED" && (!c.userId || c.userId === userId)).length;
}

export function startAutoSync(): () => void {
  const go = () => { void flushQueue(); };
  const vis = () => { if (!document.hidden) go(); };
  window.addEventListener("online", go);
  document.addEventListener("visibilitychange", vis);
  const timer = window.setInterval(go, 20000);
  // Background Sync is a progressive enhancement only: unsupported browsers rely on the foreground triggers above.
  navigator.serviceWorker?.addEventListener("message", (e) => { if (e.data === "rp-sync") go(); });
  go();
  return () => { window.removeEventListener("online", go); document.removeEventListener("visibilitychange", vis); window.clearInterval(timer); };
}
