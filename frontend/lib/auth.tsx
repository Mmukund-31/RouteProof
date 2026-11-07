"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, csrf, post } from "@/lib/api";
import type { Role, User } from "@/types";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
}
const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    // The session is an HttpOnly cookie we cannot inspect, so ask the server who we are.
    api<User>("/auth/me").then((u) => live && setUser(u)).catch(() => {
      // Offline start: keep working with the cached (non-secret) profile so drivers can still capture.
      // Queued uploads simply wait until the session is valid again.
      try {
        const cached = localStorage.getItem("rp_user");
        if (cached && !navigator.onLine && live) setUser(JSON.parse(cached));
      } catch { /* storage blocked */ }
    }).finally(() => live && setLoading(false));
    const onUnauth = () => setUser(null);
    window.addEventListener("rp:unauthorized", onUnauth);
    return () => { live = false; window.removeEventListener("rp:unauthorized", onUnauth); };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api<{ csrf_token: string; user: User }>("/auth/login",
      { method: "POST", body: JSON.stringify({ email, password, mode: "cookie" }) }, false);
    csrf.set(r.csrf_token);
    try { localStorage.setItem("rp_user", JSON.stringify(r.user)); } catch { /* ignore */ }
    setUser(r.user);
    return r.user;
  }, []);

  const logout = useCallback(async () => {
    try { await post("/auth/logout"); } catch { /* best effort: the cookie also expires on its own */ }
    csrf.set(null);
    try { localStorage.removeItem("rp_user"); } catch { /* ignore */ }
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth must be used within AuthProvider");
  return c;
}

export const homeFor = (role: Role) => (role === "driver" ? "/driver" : "/dashboard");

/** Redirects unauthenticated users to /login and wrong-role users to /unauthorized. */
export function useRequireRole(role: Role) {
  const { user, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (loading) return;
    if (!user) router.replace("/login");
    else if (user.role !== role) router.replace("/unauthorized");
  }, [user, loading, role, router]);
  return { user: user && user.role === role ? user : null, loading };
}
