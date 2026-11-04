"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, RefreshCw, Trash2 } from "lucide-react";
import { useDriver } from "@/hooks/use-driver";
import { StateIcon, type DState } from "@/components/driver/ui";
import { EmptyState } from "@/components/ui/states";
import { captureDb, type Capture } from "@/lib/offline-db";
import { flushQueue, retryCapture } from "@/lib/sync";
import { dt } from "@/lib/format";

function dstate(c: Capture, online: boolean): DState {
  switch (c.status) {
    case "UPLOADED": return c.serverStatus === "VERIFIED" ? "verified" : "uploaded";
    case "UPLOADING": return "uploading";
    case "FAILED": return "failed";
    case "RETRY_REQUIRED": return "retryRequired";
    default: return online ? "queued" : "waiting";
  }
}

function Thumb({ blob }: { blob?: Blob }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => { if (!blob) return; const u = URL.createObjectURL(blob); setUrl(u); return () => URL.revokeObjectURL(u); }, [blob]);
  // eslint-disable-next-line @next/next/no-img-element
  return url ? <img src={url} alt="" className="h-14 w-14 rounded-xl object-cover ring-1 ring-line" /> : null;
}

const LABEL: Record<DState, string> = {
  waiting: "waitingNetwork", queued: "pending", uploading: "uploading", uploaded: "uploaded", verified: "verified", failed: "failed", retryRequired: "retry",
  ready: "ready", processing: "processing", retake: "retakeRequired", review: "needsReview",
};

export default function QueuePage() {
  const { captures, online, tr } = useDriver();
  return (
    <>
      <div className="mb-4 flex items-center gap-3">
        <Link href="/driver" className="rounded-xl bg-surface px-3 py-2 shadow-sm ring-1 ring-line" aria-label="Back"><ArrowLeft className="h-5 w-5" /></Link>
        <h1 className="text-2xl font-bold text-forest">{tr("queue")}</h1>
        <button onClick={() => void flushQueue()} aria-label={tr("retry")} className="ml-auto rounded-xl bg-surface p-2.5 shadow-sm ring-1 ring-line"><RefreshCw className="h-5 w-5" /></button>
      </div>
      {!captures.length ? <EmptyState title={tr("noTrips")} /> : (
        <ul className="space-y-3" data-testid="queue">
          {captures.map((c) => {
            const s = dstate(c, online);
            const key = LABEL[s] as Parameters<typeof tr>[0];
            return (
              <li key={c.id} className="flex items-center gap-3 rounded-2xl bg-surface p-3 shadow-sm ring-1 ring-line" data-status={c.status} data-testid="queue-item">
                <StateIcon state={s} />
                <div className="min-w-0 flex-1">
                  <div className="text-lg font-bold text-forest">{c.lr}</div>
                  <div className="text-sm font-semibold">{tr(key)}</div>
                  <div className="text-xs text-muted">{dt(c.createdAt)} · {Math.round((c.compressedSize || 0) / 1024)} KB{c.retryCount > 0 ? ` · ×${c.retryCount}` : ""}</div>
                  {c.lastError && <div className="truncate text-xs text-danger">{c.lastError}</div>}
                </div>
                <Thumb blob={c.compressed} />
                {(c.status === "FAILED" || c.status === "RETRY_REQUIRED") && (
                  <div className="flex flex-col gap-2">
                    <button onClick={() => void retryCapture(c.id)} className="rounded-xl bg-forest p-2.5 text-white" aria-label={tr("retry")}><RefreshCw className="h-5 w-5" /></button>
                    {c.status === "FAILED" && <button onClick={() => void captureDb.remove(c.id)} className="rounded-xl border border-line p-2.5 text-danger" aria-label="Discard"><Trash2 className="h-5 w-5" /></button>}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
