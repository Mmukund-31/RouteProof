"use client";
import { AlertCircle, CheckCircle2, Clock, Loader2, RotateCcw, ScanSearch, WifiOff, Camera, Send } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Capture } from "@/lib/offline-db";
import type { Trip } from "@/types";

export type DState = "ready" | "queued" | "uploading" | "uploaded" | "processing" | "verified" | "retake" | "review" | "failed" | "retryRequired" | "waiting";

/** Merge server POD status with the newest local capture (local wins until the server acknowledges). */
export function stateFor(trip: Pick<Trip, "id" | "pod_status">, caps: Capture[], online: boolean): DState {
  const mine = caps.filter((c) => c.tripId === trip.id).sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0];
  if (mine && mine.status !== "UPLOADED") {
    if (mine.status === "UPLOADING") return "uploading";
    if (mine.status === "FAILED") return "failed";
    if (mine.status === "RETRY_REQUIRED") return "retryRequired";
    return online ? "queued" : "waiting";
  }
  switch (trip.pod_status) {
    case "VERIFIED": return "verified";
    case "RETAKE_REQUESTED": return "retake";
    case "NEEDS_REVIEW": return "review";
    case "UPLOADED": case "AI_PROCESSING": return "processing";
    case "REJECTED": return "retake";
    default: return mine ? "processing" : "ready";
  }
}

const META: Record<DState, { icon: React.ElementType; box: string; label: "ready" | "queuedOffline" | "uploading" | "uploaded" | "processing" | "verified" | "retakeRequired" | "needsReview" | "failed" | "retry" | "waitingNetwork"; spin?: boolean }> = {
  ready: { icon: Camera, box: "bg-forest text-white", label: "ready" },
  queued: { icon: Send, box: "bg-[#e8eef7] text-[#2f4f86]", label: "queuedOffline" },
  waiting: { icon: WifiOff, box: "bg-amber-50 text-[#8a5f12]", label: "waitingNetwork" },
  uploading: { icon: Loader2, box: "bg-[#e8eef7] text-[#2f4f86]", label: "uploading", spin: true },
  uploaded: { icon: CheckCircle2, box: "bg-teal-50 text-teal", label: "uploaded" },
  processing: { icon: ScanSearch, box: "bg-[#e8eef7] text-[#2f4f86]", label: "processing" },
  verified: { icon: CheckCircle2, box: "bg-teal text-white", label: "verified" },
  retake: { icon: RotateCcw, box: "bg-amber text-forest", label: "retakeRequired" },
  review: { icon: Clock, box: "bg-amber-50 text-[#8a5f12]", label: "needsReview" },
  failed: { icon: AlertCircle, box: "bg-danger text-white", label: "failed" },
  retryRequired: { icon: AlertCircle, box: "bg-danger-50 text-danger", label: "retry" },
};

export function StateIcon({ state, size = "md" }: { state: DState; size?: "md" | "lg" }) {
  const m = META[state]; const Icon = m.icon;
  return (
    <span className={cn("flex shrink-0 items-center justify-center rounded-2xl", m.box, size === "lg" ? "h-20 w-20" : "h-14 w-14")} aria-hidden>
      <Icon className={cn(size === "lg" ? "h-10 w-10" : "h-7 w-7", m.spin && "animate-spin")} />
    </span>
  );
}

export const stateLabelKey = (s: DState) => META[s].label;
