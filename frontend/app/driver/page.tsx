"use client";
import Link from "next/link";
import { useEffect } from "react";
import { ChevronRight, ListChecks, Volume2 } from "lucide-react";
import { useAsync } from "@/hooks/use-async";
import { useDriver } from "@/hooks/use-driver";
import { StateIcon, stateFor, stateLabelKey } from "@/components/driver/ui";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { services } from "@/services";
import { speak, speechSupported } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { Trip } from "@/types";

const CACHE = "rp_driver_trips";

export default function DriverHome() {
  const { lang, online, captures, tr } = useDriver();
  const trips = useAsync(async () => {
    try {
      const r = await services.driverTrips();
      try { localStorage.setItem(CACHE, JSON.stringify(r.items)); } catch { /* ignore */ }
      return r.items;
    } catch (e) {
      // Offline: fall back to the last list so the driver can still pick a trip and capture.
      try { const c = localStorage.getItem(CACHE); if (c) return JSON.parse(c) as Trip[]; } catch { /* ignore */ }
      throw e;
    }
  }, [online]);
  // Refresh server status when captures sync.
  useEffect(() => { const h = () => trips.reload(); window.addEventListener("rp:queue", h); return () => window.removeEventListener("rp:queue", h); }, [trips]);
  const open = captures.filter((c) => c.status !== "UPLOADED").length;

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-forest">{tr("myTrips")}</h1>
        <Link href="/driver/queue" className="flex items-center gap-1.5 rounded-xl bg-surface px-3 py-2 text-sm font-semibold shadow-sm ring-1 ring-line">
          <ListChecks className="h-5 w-5 text-teal" />{tr("queue")}{open > 0 && <span className="rounded-full bg-amber px-2 text-xs text-forest">{open}</span>}
        </Link>
      </div>
      {trips.loading && !trips.data ? <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-28" />)}</div> :
        trips.error && !trips.data ? <ErrorState message={trips.error} onRetry={trips.reload} /> :
        !trips.data?.length ? <EmptyState title={tr("noTrips")} /> : (
          <ul className="space-y-3">
            {trips.data.map((t) => {
              const s = stateFor(t, captures, online);
              const label = tr(stateLabelKey(s));
              return (
                <li key={t.id}>
                  <Link href={`/driver/capture/${t.id}`} className="flex items-center gap-4 rounded-2xl bg-surface p-4 shadow-sm ring-1 ring-line active:scale-[0.99]" data-testid={`trip-${t.trip_reference}`}>
                    <StateIcon state={s} />
                    <div className="min-w-0 flex-1">
                      <div className="text-xl font-bold tracking-tight text-forest">{t.lr_number}</div>
                      <div className="truncate text-base text-ink">{t.destination}</div>
                      <div className={cn("mt-0.5 text-sm font-semibold", s === "verified" ? "text-teal" : s === "retake" || s === "review" || s === "waiting" ? "text-[#8a5f12]" : s === "failed" ? "text-danger" : "text-muted")}>{label}</div>
                    </div>
                    <ChevronRight className="h-6 w-6 text-muted" />
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      {speechSupported() && trips.data?.length ? (
        <button onClick={() => speak(`${tr("myTrips")}: ${trips.data!.length}`, lang)} className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl border border-line bg-surface py-3 text-base font-medium">
          <Volume2 className="h-5 w-5" />{tr("listen")}
        </button>
      ) : null}
    </>
  );
}
