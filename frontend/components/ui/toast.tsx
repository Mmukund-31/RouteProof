"use client";
import { createContext, useCallback, useContext, useState } from "react";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

type Kind = "success" | "error" | "info";
interface T { id: number; kind: Kind; text: string }
const Ctx = createContext<(kind: Kind, text: string) => void>(() => {});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<T[]>([]);
  const push = useCallback((kind: Kind, text: string) => {
    const id = Date.now() + Math.random();
    setItems((s) => [...s, { id, kind, text }]);
    setTimeout(() => setItems((s) => s.filter((x) => x.id !== id)), 5000);
  }, []);
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={cn("pointer-events-auto flex items-start gap-2 rounded-lg border bg-surface px-3 py-2.5 text-sm shadow-lg",
            t.kind === "error" ? "border-danger/40" : t.kind === "success" ? "border-teal/40" : "border-line")}>
            {t.kind === "error" ? <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" /> : t.kind === "success" ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-teal" /> : <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted" />}
            <span className="flex-1">{t.text}</span>
            <button aria-label="Dismiss" onClick={() => setItems((s) => s.filter((x) => x.id !== t.id))}><X className="h-4 w-4 text-muted" /></button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useToast() {
  const push = useContext(Ctx);
  return { success: (m: string) => push("success", m), error: (m: string) => push("error", m), info: (m: string) => push("info", m) };
}
