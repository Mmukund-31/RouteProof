"use client";
import { use, useCallback, useEffect, useState } from "react";
import { startAutoSync } from "@/lib/sync";
import { DriverProvider, useDriver } from "@/hooks/use-driver";
import { CaptureFlow } from "@/components/driver/capture-flow";
import { Logo } from "@/components/logo";
import { LANGS } from "@/lib/i18n";
import { Skeleton } from "@/components/ui/states";
import { API_BASE, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Link2Off, WifiOff } from "lucide-react";
import type { PodStatus } from "@/types";

interface LinkInfo { lr_number: string; trip_reference: string; destination: string; pod_status: PodStatus; retakes_remaining: number }

async function fetchLink(token: string): Promise<LinkInfo> {
  let res: Response;
  try { res = await fetch(`${API_BASE}/api/v1/driver-links/${token}`); } catch { throw new ApiError(0, "network", "No internet connection"); }
  if (!res.ok) {
    const b = await res.json().catch(() => ({}));
    throw new ApiError(res.status, b?.error?.code ?? "error", b?.error?.message ?? "Link not available");
  }
  return res.json();
}

function Inner({ token }: { token: string }) {
  const { lang, setLang, online, tr } = useDriver();
  const [info, setInfo] = useState<LinkInfo | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const load = useCallback(async () => {
    try { setInfo(await fetchLink(token)); setErr(null); }
    catch (e) { setErr(e as ApiError); }
  }, [token]);
  useEffect(() => { void load(); return startAutoSync(); }, [load]);

  return (
    <div className="min-h-screen bg-canvas">
      <header className="bg-forest text-white">
        <div className="mx-auto flex max-w-lg items-center justify-between px-4 py-3">
          <Logo light />
          <div className="flex rounded-lg bg-white/10 p-0.5" role="group" aria-label="Language">
            {LANGS.map((l) => <button key={l.code} aria-pressed={lang === l.code} onClick={() => setLang(l.code)} className={cn("rounded-md px-2.5 py-1.5 text-sm font-medium", lang === l.code ? "bg-white text-forest" : "text-white/80")}>{l.label}</button>)}
          </div>
        </div>
        {!online && <div role="status" className="flex items-center justify-center gap-2 bg-amber py-1.5 text-sm font-medium text-forest"><WifiOff className="h-4 w-4" />{tr("offline")}</div>}
      </header>
      <main className="mx-auto max-w-lg px-4 pb-24 pt-5">
        {err && !info ? (
          err.code === "network" ? <p className="rounded-2xl bg-amber-50 p-6 text-center text-[#8a5f12]">{tr("offline")}</p> : (
            <div className="flex flex-col items-center gap-3 rounded-3xl bg-surface p-8 text-center ring-1 ring-line">
              <Link2Off className="h-12 w-12 text-muted" />
              <h1 className="text-xl font-bold text-forest">{err.status === 410 ? "This link has expired" : "This link is not valid"}</h1>
              <p className="text-muted">Please ask the transport office to send a new link.</p>
            </div>
          )
        ) : !info ? <Skeleton className="h-64 w-full" /> : (
          <CaptureFlow tripId={`link:${token.slice(0, 12)}`} tripRef={info.trip_reference} lr={info.lr_number} destination={info.destination}
            linkToken={token} podStatus={info.pod_status} retakesRemaining={info.retakes_remaining} refreshStatus={load} />
        )}
      </main>
    </div>
  );
}

export default function UploadLanding({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  return <DriverProvider initialLang="hi"><Inner token={token} /></DriverProvider>;
}
