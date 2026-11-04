"use client";
import { use, useCallback, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { CaptureFlow } from "@/components/driver/capture-flow";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { services } from "@/services";
import { useAsync } from "@/hooks/use-async";
import type { Trip } from "@/types";

export default function CapturePage({ params }: { params: Promise<{ tripId: string }> }) {
  const { tripId } = use(params);
  const [fresh, setFresh] = useState<Trip | null>(null);
  const trip = useAsync(async () => {
    try { return await services.trip(tripId); }
    catch (e) {
      // Offline: reuse the cached trip list so capture still works with no signal.
      try { const c = JSON.parse(localStorage.getItem("rp_driver_trips") ?? "[]") as Trip[]; const hit = c.find((t) => t.id === tripId); if (hit) return hit; } catch { /* ignore */ }
      throw e;
    }
  }, [tripId]);
  const refresh = useCallback(async () => { try { setFresh(await services.trip(tripId)); } catch { /* offline: keep local state */ } }, [tripId]);

  const t = fresh ?? trip.data;
  return (
    <>
      <Link href="/driver" className="mb-4 inline-flex items-center gap-2 rounded-xl bg-surface px-3 py-2 text-base font-semibold shadow-sm ring-1 ring-line"><ArrowLeft className="h-5 w-5" /></Link>
      {trip.error && !t ? <ErrorState message={trip.error} onRetry={trip.reload} /> : !t ? <Skeleton className="h-64 w-full" /> : (
        <CaptureFlow tripId={t.id} tripRef={t.trip_reference} lr={t.lr_number} destination={t.destination}
          podStatus={t.pod_status} retakesRemaining={t.retakes_remaining} refreshStatus={refresh} />
      )}
    </>
  );
}
