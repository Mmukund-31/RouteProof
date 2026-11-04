"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { Lang } from "@/types";
import { captureDb, type Capture } from "@/lib/offline-db";
import { t as translate } from "@/lib/i18n";

interface Ctx { lang: Lang; setLang: (l: Lang) => void; online: boolean; captures: Capture[]; refresh: () => void; tr: (k: Parameters<typeof translate>[1]) => string }
const C = createContext<Ctx | null>(null);

export function useOnline() {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    setOnline(navigator.onLine);
    const on = () => setOnline(true), off = () => setOnline(false);
    window.addEventListener("online", on); window.addEventListener("offline", off);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);
  return online;
}

export function useCaptures() {
  const [captures, setCaptures] = useState<Capture[]>([]);
  const refresh = useCallback(() => { captureDb.all().then(setCaptures).catch(() => setCaptures([])); }, []);
  useEffect(() => {
    refresh();
    window.addEventListener("rp:queue", refresh);
    return () => window.removeEventListener("rp:queue", refresh);
  }, [refresh]);
  return { captures, refresh };
}

export function DriverProvider({ initialLang, children }: { initialLang: Lang; children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  const online = useOnline();
  const { captures, refresh } = useCaptures();
  useEffect(() => {
    try { const s = localStorage.getItem("rp_lang") as Lang | null; if (s) setLangState(s); } catch { /* ignore */ }
  }, []);
  const setLang = (l: Lang) => { setLangState(l); try { localStorage.setItem("rp_lang", l); } catch { /* ignore */ } };
  const tr = useCallback((k: Parameters<typeof translate>[1]) => translate(lang, k), [lang]);
  return <C.Provider value={{ lang, setLang, online, captures, refresh, tr }}>{children}</C.Provider>;
}

export function useDriver() {
  const c = useContext(C);
  if (!c) throw new Error("useDriver outside DriverProvider");
  return c;
}
