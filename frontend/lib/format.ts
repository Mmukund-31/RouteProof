const TZ = "Asia/Kolkata";

export const inr = (v: string | number | null | undefined) =>
  v === null || v === undefined || v === "" ? "—" : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(v));

export const inrCompact = (v: number) =>
  v >= 1e7 ? `₹${(v / 1e7).toFixed(2)} Cr` : v >= 1e5 ? `₹${(v / 1e5).toFixed(1)} L` : inr(v);

/** Timestamps are stored in UTC and rendered in IST. */
export const dt = (iso: string | null | undefined) =>
  iso ? new Intl.DateTimeFormat("en-IN", { timeZone: TZ, day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(iso)) : "—";

export const d = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const date = iso.length === 10 ? new Date(iso + "T00:00:00") : new Date(iso);
  return new Intl.DateTimeFormat("en-IN", { timeZone: iso.length === 10 ? undefined : TZ, day: "2-digit", month: "short", year: "numeric" }).format(date);
};

/** "5 min ago", "3 h ago", "2 d ago" — for queues where waiting time matters more than the clock time. */
export const ago = (iso: string | null | undefined, now = Date.now()) => {
  if (!iso) return "—";
  const m = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} d ago`;
};

export const pct = (v: number) => `${Math.round(v * 100)}%`;
export const hours = (h: number | null) => (h === null ? "—" : h >= 48 ? `${(h / 24).toFixed(1)} d` : `${h.toFixed(1)} h`);
export const humanize = (s: string) => s.toLowerCase().replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

/** Plain-language names for audit actions. Unknown actions fall back to a humanised code, never to nothing. */
const ACTIONS: Record<string, string> = {
  "auth.login": "Signed in", "auth.login_failed": "Failed sign-in", "auth.logout": "Signed out",
  "billing.export_created": "Billing export created", "billing.export_downloaded": "Billing export downloaded",
  "client_link.created": "Client POD link created", "client_link.revoked": "Client POD link revoked", "client_link.expired": "Client POD link expired",
  "client_link.opened": "Client opened POD link", "client_link.image_viewed": "Client viewed a POD", "client_link.access_denied": "Client link access denied",
  "driver_link.created": "Driver upload link sent", "driver_link.revoked": "Driver upload link revoked", "driver_link.expired": "Driver upload link expired",
  "driver_link.opened": "Driver opened upload link", "driver_link.upload": "POD uploaded via driver link",
  "pod.uploaded": "POD uploaded", "pod.original_attached": "Full-resolution original received", "pod.upload_oversize": "Upload over size limit",
  "pod.processing_started": "AI extraction started", "pod.ai_processing_started": "AI extraction started", "pod.processing_finished": "AI extraction finished",
  "pod.ai_processed": "AI extraction finished", "pod.provider_retry": "AI provider retried", "pod.processing_error": "AI extraction error",
  "pod.ai_processing_failed": "AI extraction failed", "pod.processing_crashed": "AI extraction crashed", "pod.background_failed": "Background processing failed",
  "pod.recovery_sweep": "Stalled processing recovered", "pod.recover_failed": "Recovery failed",
  "pod.routed_to_review": "Sent to review", "pod.fields_corrected": "Fields corrected by reviewer", "pod.exception_approved": "Exception accepted",
  "pod.verified": "POD verified", "pod.rejected": "POD rejected", "pod.retake_requested": "Retake requested", "pod.images_purged": "POD images purged",
  "trip.imported": "Trip imported", "trip.delivery_date_confirmed": "Delivery date confirmed", "trip.billing_ready": "Trip billing-ready",
  "trip.exported": "Trip exported", "trip.invoiced_recorded": "Invoice recorded",
  "retention.access_logs_purged": "Access logs purged", "retention.pod_images_purged": "POD images purged (retention)",
};
export const actionLabel = (a: string) => ACTIONS[a] ?? humanize(a.replace(".", " · "));
/** Tone of an audit action, so problem events stand out in timelines. */
export const actionTone = (a: string): "good" | "bad" | "warn" | "plain" =>
  /verified|billing_ready|exception_approved|export_created|invoiced/.test(a) ? "good"
    : /rejected|failed|crashed|error|denied/.test(a) ? "bad"
      : /retake|routed_to_review|oversize|stalled|recover/.test(a) ? "warn" : "plain";
