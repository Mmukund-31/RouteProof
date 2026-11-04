const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const TOKEN_KEY = "rp_token";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details: Record<string, unknown> = {}) {
    super(message);
  }
  /** True for failures where retrying the same request cannot succeed. */
  get permanent() { return this.status >= 400 && this.status < 500 && this.status !== 408 && this.status !== 429; }
}

export const tokenStore = {
  get: () => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } },
  set: (t: string) => { try { localStorage.setItem(TOKEN_KEY, t); } catch { /* storage blocked */ } },
  clear: () => { try { localStorage.removeItem(TOKEN_KEY); } catch { /* storage blocked */ } },
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
  const t = auth ? tokenStore.get() : null;
  if (t) headers.set("Authorization", `Bearer ${t}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`${BASE}/api/v1${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "network", "Cannot reach the server. Check your connection.");
  }
  if (!res.ok) {
    let body: { error?: { code?: string; message?: string; details?: Record<string, unknown> } } = {};
    try { body = await res.json(); } catch { /* non-JSON error */ }
    if (res.status === 401 && auth && typeof window !== "undefined" && !path.startsWith("/auth/login")) {
      tokenStore.clear();
      window.dispatchEvent(new Event("rp:unauthorized"));
    }
    throw new ApiError(res.status, body.error?.code ?? "error", body.error?.message ?? `Request failed (${res.status})`, body.error?.details);
  }
  return res;
}

export async function api<T>(path: string, init: RequestInit = {}, auth = true): Promise<T> {
  return (await raw(path, init, auth)).json() as Promise<T>;
}
export const get = <T,>(path: string, q?: Q) => api<T>(path + qs(q));
export const post = <T,>(path: string, body?: unknown) => api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

/** Authenticated binary fetch (images / CSV) since <img> and <a> cannot send the bearer token. */
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
