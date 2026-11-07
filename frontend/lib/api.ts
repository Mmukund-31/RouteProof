/**
 * API client.
 *
 * Authentication is an HttpOnly session cookie set by the backend: page JavaScript can never read the token, so an
 * XSS bug cannot exfiltrate it. State-changing requests carry the session-bound CSRF token (double-submit) from the
 * readable `rp_csrf` cookie. In production the frontend proxies /api/v1 to the backend (see next.config.ts) so the
 * cookie is first-party; set NEXT_PUBLIC_API_URL="" for that. In local development the API on localhost:8000 is
 * same-site with localhost:3000, so cookies work without the proxy.
 */
const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const CSRF_COOKIE = "rp_csrf";
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details: Record<string, unknown> = {},
    public requestId?: string) {
    super(message);
  }
  /** True for failures where retrying the same request cannot succeed. 401 is not permanent: signing in again fixes it. */
  get permanent() { return this.status >= 400 && this.status < 500 && ![401, 408, 429].includes(this.status); }
}

/** Fallback for the CSRF token when the cookie is not readable from this origin (cross-site API without the proxy). */
let csrfMemory: string | null = null;
export const csrf = {
  set: (t: string | null | undefined) => { csrfMemory = t ?? null; },
  get: (): string | null => {
    if (typeof document !== "undefined") {
      const hit = document.cookie.split("; ").find((c) => c.startsWith(`${CSRF_COOKIE}=`));
      if (hit) return decodeURIComponent(hit.slice(CSRF_COOKIE.length + 1));
    }
    return csrfMemory;
  },
};

type Q = Record<string, string | number | boolean | undefined | null>;
export const qs = (q?: Q) => {
  const p = new URLSearchParams();
  Object.entries(q ?? {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") p.set(k, String(v)); });
  const s = p.toString();
  return s ? `?${s}` : "";
};

async function raw(path: string, init: RequestInit = {}, auth = true): Promise<Response> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();
  if (UNSAFE.has(method)) {
    const t = csrf.get();
    if (t) headers.set("X-CSRF-Token", t);
  }
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`${BASE}/api/v1${path}`, { ...init, headers, credentials: "include" });
  } catch {
    throw new ApiError(0, "network", "Cannot reach the server. Check your connection.");
  }
  if (!res.ok) {
    let body: { error?: { code?: string; message?: string; details?: Record<string, unknown>; request_id?: string } } = {};
    try { body = await res.json(); } catch { /* non-JSON error */ }
    if (res.status === 401 && auth && typeof window !== "undefined" && !path.startsWith("/auth/login")) {
      window.dispatchEvent(new Event("rp:unauthorized"));
    }
    throw new ApiError(res.status, body.error?.code ?? "error", body.error?.message ?? `Request failed (${res.status})`,
      body.error?.details, body.error?.request_id ?? res.headers.get("X-Request-ID") ?? undefined);
  }
  return res;
}

export async function api<T>(path: string, init: RequestInit = {}, auth = true): Promise<T> {
  return (await raw(path, init, auth)).json() as Promise<T>;
}
export const get = <T,>(path: string, q?: Q) => api<T>(path + qs(q));
export const post = <T,>(path: string, body?: unknown) => api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

/** Authenticated binary fetch (images / CSV) so private files are only ever served through the API. */
export async function blob(path: string): Promise<Blob> {
  return (await raw(path)).blob();
}

export async function downloadFile(path: string, filename: string) {
  const b = await blob(path);
  const url = URL.createObjectURL(b);
  const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export const API_BASE = BASE;
