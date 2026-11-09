import { get, post, api } from "@/lib/api";
import type { AuditRow, BillingRow, ClientLink, DriverLinkRow, ExportRecord, Metrics, MissingPod, Options, Page, Pod, Trip } from "@/types";

type Q = Record<string, string | number | boolean | undefined | null>;

export const services = {
  options: () => get<Options>("/meta/options"),
  metrics: (q: Q) => get<Metrics>("/dashboard/metrics", q),
  recent: () => get<{ items: { id: string; action: string; entity_type: string; entity_id: string; user: string; timestamp: string }[] }>("/dashboard/recent-activity"),
  missing: (q: Q) => get<{ items: MissingPod[]; overdue_count: number; overdue_after_days: number; freight_blocked: number; pending_reviews: number; filters: Record<string, string | number | null> }>("/dashboard/missing-pods", q),
  trips: (q: Q) => get<Page<Trip>>("/trips", q),
  trip: (id: string) => get<Trip>(`/trips/${id}`),
  tripHistory: (id: string) => get<{ items: AuditRow[] }>(`/trips/${id}/history`),
  importTrips: (file: File, dryRun: boolean) => {
    const f = new FormData();
    f.append("file", file);
    return api<{ fatal: string | null; dry_run: boolean; created: number; duplicates: { row: number; trip_reference: string }[]; errors: { row: number; message: string }[]; unknown_columns?: string[] }>(
      `/trips/import?dry_run=${dryRun}`, { method: "POST", body: f });
  },
  pod: (id: string) => get<Pod>(`/pods/${id}`),
  reprocess: (id: string) => post<Pod>(`/pods/${id}/process`),
  retake: (id: string) => post<Pod>(`/pods/${id}/retake`),
  recoverStale: () => post<{ recovered: string[]; requeued: number }>("/pods/maintenance/recover"),
  review: (id: string, body: { decision: "APPROVE" | "REJECT" | "RETAKE"; corrections?: Record<string, unknown>; correction_reason?: string; rejection_reason?: string; approval_reason?: string }) =>
    post<Pod>(`/pods/${id}/review`, body),
  reviews: (q: Q) => get<Page<Pod>>("/reviews", q),
  driverLink: (trip_id: string, phone?: string) =>
    post<{ url: string; expires_at: string; sms: { provider: string; status: string; to: string; note: string } }>("/driver-links", { trip_id, phone: phone || undefined }),
  billingQueue: (q: Q) => get<Page<BillingRow> & { total_freight: string }>("/billing/queue", q),
  exports: (q: Q) => get<Page<ExportRecord>>("/billing/exports", q),
  createExport: (body: { trip_ids: string[]; billing_period?: string; filters?: Record<string, unknown>; reexport?: boolean; reexport_reason?: string }) =>
    post<ExportRecord>("/billing/exports", body),
  markInvoiced: (tripId: string, invoice_reference: string, invoice_date?: string) =>
    post(`/billing/trips/${tripId}/invoiced`, { invoice_reference, invoice_date: invoice_date || undefined }),
  clientLinks: (q: Q) => get<Page<ClientLink>>("/client-links", q),
  createClientLink: (body: { client_id: string; trip_ids?: string[]; billing_cycle?: string; expires_in_days?: number; label?: string }) =>
    post<ClientLink & { url: string }>("/client-links", body),
  revokeClientLink: (id: string) => post<ClientLink>(`/client-links/${id}/revoke`),
  driverLinks: (trip_id: string) => get<{ items: DriverLinkRow[] }>("/driver-links", { trip_id }),
  revokeDriverLink: (id: string) => post<DriverLinkRow>(`/driver-links/${id}/revoke`),
  audit: (q: Q) => get<Page<AuditRow>>("/audit-logs", q),
  driverTrips: () => get<{ items: Trip[] }>("/driver/trips"),
  driverUploads: () => get<{ items: Pod[] }>("/driver/uploads"),
  sync: (keys: string[]) =>
    post<{ items: { idempotency_key: string; received: boolean; pod_id: string | null; verification_status: string | null }[] }>("/driver/uploads/sync", { keys }),
};
