import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, csrf, get, post } from "@/lib/api";

afterEach(() => { vi.unstubAllGlobals(); document.cookie = "rp_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT"; csrf.set(null); });

const ok = () => vi.fn().mockImplementation(async () => new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }));

describe("api client (cookie session)", () => {
  it("sends credentials and never an Authorization header", async () => {
    const f = ok(); vi.stubGlobal("fetch", f);
    await get("/auth/me");
    const [, init] = f.mock.calls[0];
    expect(init.credentials).toBe("include");
    expect(new Headers(init.headers).has("Authorization")).toBe(false);
  });

  it("adds the CSRF token from the cookie to state-changing requests only", async () => {
    document.cookie = "rp_csrf=tok123";
    const f = ok(); vi.stubGlobal("fetch", f);
    await post("/auth/logout");
    await get("/trips");
    expect(new Headers(f.mock.calls[0][1].headers).get("X-CSRF-Token")).toBe("tok123");
    expect(new Headers(f.mock.calls[1][1].headers).has("X-CSRF-Token")).toBe(false);
  });

  it("treats an expired session as retryable, not permanent", () => {
    expect(new ApiError(401, "invalid_token", "x").permanent).toBe(false);
    expect(new ApiError(409, "pod_in_progress", "x").permanent).toBe(true);
  });

  it("keeps no token in localStorage", async () => {
    vi.stubGlobal("fetch", ok());
    await post("/auth/login", { email: "a", password: "b", mode: "cookie" });
    expect(Object.keys(localStorage).some((k) => k.includes("token"))).toBe(false);
  });
});
