"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, RefreshCw } from "lucide-react";
import { Button, buttonClass } from "@/components/ui/button";
import { Callout, Card, PageHeader } from "@/components/ui/card";
import { PodBadge } from "@/components/ui/badge";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { PodReview } from "@/components/pod-review";
import { useAsync } from "@/hooks/use-async";
import { services } from "@/services";
import { dt } from "@/lib/format";
import type { Pod } from "@/types";

export default function PodPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const res = useAsync(() => services.pod(id), [id]);
  const [pod, setPod] = useState<Pod | null>(null);
  const [busy, setBusy] = useState(false);
  const [decided, setDecided] = useState(false);
  const [next, setNext] = useState<Pod | null | undefined>(undefined);
  const toast = useToast();
  useEffect(() => { if (res.data) setPod(res.data); }, [res.data]);
  useEffect(() => { setDecided(false); setNext(undefined); }, [id]);

  // While the AI is still working, poll until the decision lands.
  const status = pod?.verification_status;
  useEffect(() => {
    if (status !== "UPLOADED" && status !== "AI_PROCESSING") return;
    const t = setInterval(res.reload, 2500);
    return () => clearInterval(t);
  }, [status, res.reload]);

  if (res.error && !pod) return <Card><ErrorState message={res.error} onRetry={res.reload} /></Card>;
  if (!pod) return <div role="status" aria-label="Loading POD" className="space-y-4"><Skeleton className="h-16 w-1/2" /><Skeleton className="h-[32rem] w-full" /></div>;

  // Called only after a human decision is submitted: find the next document waiting in the queue.
  function afterDecision(p: Pod) {
    setPod(p);
    setDecided(true);
    setNext(undefined);
    services.reviews({ status: "NEEDS_REVIEW", page_size: 2 })
      .then((r) => setNext(r.items.find((x) => x.id !== id) ?? null))
      .catch(() => setNext(null));
  }

  async function rerun() {
    setBusy(true);
    try { setPod(await services.reprocess(pod!.id)); toast.success("AI extraction re-run"); }
    catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  }
  // A POD stuck in AI_PROCESSING past the stale window can be recovered and re-run from here too.
  const canRerun = pod.verification_status === "NEEDS_REVIEW" || pod.verification_status === "UPLOADED" || !!pod.processing?.stale;

  return (
    <>
      <PageHeader
        crumbs={[{ label: "Review queue", href: "/reviews" }, { label: pod.trip.trip_reference, href: `/trips/${pod.trip_id}` }, { label: `POD attempt #${pod.attempt_number}` }]}
        title={`POD verification · ${pod.trip.lr_number}`}
        meta={<><span>{pod.trip.trip_reference}</span><span aria-hidden>·</span><span>{pod.trip.client.name}</span><span aria-hidden>·</span><span>{pod.trip.destination}</span><span aria-hidden>·</span><span>attempt #{pod.attempt_number}</span><PodBadge status={pod.verification_status} /></>}
        actions={<>
          <Link href={`/trips/${pod.trip_id}`} className={buttonClass({ variant: "ghost", size: "md" })}>Open trip</Link>
          {canRerun && <Button variant="outline" loading={busy} onClick={rerun}><RefreshCw className="h-4 w-4" />Re-run AI extraction</Button>}
        </>} />

      {decided && (
        <Callout tone="success" className="mb-4" data-testid="next-in-queue" title="Decision recorded"
          action={next === undefined ? null : next ? (
            <Link href={`/pods/${next.id}`} className={buttonClass({ size: "sm" })}>Review next · {next.trip.trip_reference}<ArrowRight className="h-3.5 w-3.5" /></Link>
          ) : <Link href="/reviews" className={buttonClass({ size: "sm", variant: "outline" })}>Back to queue</Link>}>
          {next === null ? "The review queue is now clear." : next ? "The next highest-priority POD is ready." : "Finding the next POD…"}
        </Callout>
      )}
      {(status === "UPLOADED" || status === "AI_PROCESSING") && !pod.processing?.stale && <Callout tone="info" className="mb-4" role="status">AI is reading the document… this page updates automatically.</Callout>}
      {pod.processing?.stale && <Callout tone="warning" className="mb-4" role="status">Processing appears stalled (started {pod.processing.started_at ? dt(pod.processing.started_at) : "at an unknown time"}). Use “Re-run AI extraction” to recover it.</Callout>}
      <PodReview pod={pod} onChanged={afterDecision} />
    </>
  );
}
