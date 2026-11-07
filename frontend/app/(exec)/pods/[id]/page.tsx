"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/card";
import { PodBadge } from "@/components/ui/badge";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { PodReview } from "@/components/pod-review";
import { useAsync } from "@/hooks/use-async";
import { services } from "@/services";
import type { Pod } from "@/types";

export default function PodPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const res = useAsync(() => services.pod(id), [id]);
  const [pod, setPod] = useState<Pod | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  useEffect(() => { if (res.data) setPod(res.data); }, [res.data]);

  // While the AI is still working, poll until the decision lands.
  const status = pod?.verification_status;
  useEffect(() => {
    if (status !== "UPLOADED" && status !== "AI_PROCESSING") return;
    const t = setInterval(res.reload, 2500);
    return () => clearInterval(t);
  }, [status, res.reload]);

  if (res.error && !pod) return <Card><ErrorState message={res.error} onRetry={res.reload} /></Card>;
  if (!pod) return <Skeleton className="h-[32rem] w-full" />;

  async function rerun() {
    setBusy(true);
    try { setPod(await services.reprocess(pod!.id)); toast.success("Re-processed"); }
    catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  }
  // A POD stuck in AI_PROCESSING past the stale window can be recovered and re-run from here too.
  const canRerun = pod.verification_status === "NEEDS_REVIEW" || pod.verification_status === "UPLOADED" || !!pod.processing?.stale;

  return (
    <>
      <Link href={`/trips/${pod.trip_id}`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="h-4 w-4" />{pod.trip.trip_reference}</Link>
      <PageHeader title={`POD verification · ${pod.trip.lr_number}`}
        subtitle={<span className="flex flex-wrap items-center gap-2">{pod.trip.client.name} · {pod.trip.destination} · attempt #{pod.attempt_number}<PodBadge status={pod.verification_status} /></span>}
        actions={canRerun && <Button variant="outline" loading={busy} onClick={rerun}><RefreshCw className="h-4 w-4" />Re-run AI extraction</Button>} />
      {(status === "UPLOADED" || status === "AI_PROCESSING") && !pod.processing?.stale && <p className="mb-4 rounded-lg bg-[#e8eef7] px-4 py-2 text-sm text-[#2f4f86]" role="status">AI is reading the document… this page updates automatically.</p>}
      {pod.processing?.stale && <p className="mb-4 rounded-lg bg-amber-50 px-4 py-2 text-sm text-[#8a5f12]" role="status">Processing appears stalled (started {pod.processing.started_at ? new Date(pod.processing.started_at).toLocaleString() : "unknown"}). Use “Re-run AI extraction” to recover it.</p>}
      <PodReview pod={pod} onChanged={setPod} />
    </>
  );
}
