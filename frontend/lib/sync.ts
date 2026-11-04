import { API_BASE, ApiError, api } from "@/lib/api";
import { captureDb, type Capture } from "@/lib/offline-db";

const MANUAL_RETRY_AFTER = 3;
let running: Promise<void> | null = null;

export function buildForm(c: Capture): FormData {
  const f = new FormData();
  f.append("file", c.compressed!, `${c.id}.jpg`);
  f.append("idempotency_key", c.id); // identical on every retry -> server returns the same POD
  f.append("captured_at", c.capturedAt);
  if (c.latitude !== undefined) f.append("latitude", String(c.latitude));
  if (c.longitude !== undefined) f.append("longitude", String(c.longitude));
  if (c.accuracy !== undefined) f.append("accuracy", String(c.accuracy));
  return f;
}

interface UploadResp { created: boolean; pod: { id: string; verification_status: string } }

export async function uploadCapture(c: Capture): Promise<UploadResp> {
  if (c.linkToken) {
    // Hired-driver flow: no bearer token, access is scoped by the link token to a single trip.
    let res: Response;
    try { res = await fetch(`${API_BASE}/api/v1/driver-links/${c.linkToken}/pods`, { method: "POST", body: buildForm(c) }); }
    catch { throw new ApiError(0, "network", "Cannot reach the server"); }
    if (!res.ok) {
      const b = await res.json().catch(() => ({}));
      throw new ApiError(res.status, b?.error?.code ?? "error", b?.error?.message ?? "Upload failed");
    }
    return res.json();
  }
  return api<UploadResp>(`/trips/${c.tripId}/pods`, { method: "POST", body: buildForm(c) });
}

/** Uploads every pending capture exactly once at a time. Safe to call from many triggers (online event, timer, button). */
export function flushQueue(upload: typeof uploadCapture = uploadCapture): Promise<void> {
  if (running) return running;
  const p: Promise<void> = (async () => {
    await Promise.resolve(); // guarantee `running` is assigned before any early return releases it
    {
      if (typeof navigator !== "undefined" && !navigator.onLine) return;
      const todo = (await captureDb.all()).filter((c) => c.status === "PENDING" || c.status === "UPLOADING" || c.status === "RETRY_REQUIRED").reverse();
      for (const c of todo) {
        if (typeof navigator !== "undefined" && !navigator.onLine) break;
        if (!c.compressed) { await captureDb.update(c.id, { status: "FAILED", lastError: "Image data missing" }); continue; }
        await captureDb.update(c.id, { status: "UPLOADING", lastError: undefined });
        try {
          const r = await upload(c);
          // Server acknowledged: release the full-resolution original and the upload artifact.
          await captureDb.update(c.id, {
            status: "UPLOADED", podId: r.pod.id, serverStatus: r.pod.verification_status, ackedAt: new Date().toISOString(),
            original: undefined, compressed: undefined,
          });
        } catch (e) {
          const err = e as ApiError;
          if (err instanceof ApiError && err.permanent) {
            await captureDb.update(c.id, { status: "FAILED", lastError: err.message, retryCount: c.retryCount + 1 });
          } else {
            const n = c.retryCount + 1;
            await captureDb.update(c.id, { status: n >= MANUAL_RETRY_AFTER ? "RETRY_REQUIRED" : "PENDING", retryCount: n, lastError: (e as Error).message });
          }
        }
      }
    }
  })();
  running = p;
  const release = () => { if (running === p) running = null; };
  p.then(release, release); // release the single-flight lock whether the run succeeded or threw
  return p;
}

export async function retryCapture(id: string) {
  await captureDb.update(id, { status: "PENDING", lastError: undefined, retryCount: 0 });
  return flushQueue();
}

export function startAutoSync(): () => void {
  const go = () => { void flushQueue(); };
  window.addEventListener("online", go);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) go(); });
  const timer = window.setInterval(go, 20000);
  // Background Sync is a progressive enhancement only: unsupported browsers rely on the foreground triggers above.
  navigator.serviceWorker?.addEventListener("message", (e) => { if (e.data === "rp-sync") go(); });
  go();
  return () => { window.removeEventListener("online", go); window.clearInterval(timer); };
}
