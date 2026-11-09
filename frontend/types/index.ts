export type Role = "driver" | "billing_executive";
export type Lang = "en" | "hi" | "mr";

export interface User { id: string; name: string; email: string; role: Role; preferred_language: Lang }

export type PodStatus =
  | "PENDING" | "UPLOADED" | "AI_PROCESSING" | "NEEDS_REVIEW" | "RETAKE_REQUESTED" | "VERIFIED" | "REJECTED";
export type BillingStatus = "NOT_READY" | "BILLING_READY" | "EXPORTED" | "INVOICED";

export interface Trip {
  id: string; trip_reference: string; lr_number: string; eway_bill_number: string;
  client: { id: string; name: string; code: string };
  vehicle: { registration: string; type: string; ownership: "owned" | "hired" };
  driver: { id: string; name: string } | null;
  origin: string; destination: string; branch: string | null; commodity: string | null; consignee_name: string | null;
  expected_quantity: number | null; quantity_unit: string | null; delivery_date: string | null;
  /** Where delivery_date came from. Never the upload date. */
  delivery_date_source?: "import" | "pod_ai" | "pod_human" | null; delivery_date_confirmed_at?: string | null;
  trip_status: string; pod_status: PodStatus; latest_pod_id: string | null; retakes_remaining: number;
  rejection_reason: string | null;
  freight_amount?: string; billing_status?: BillingStatus; billing_cycle?: string | null; invoice_reference?: string | null;
  billing_ready_at?: string | null; exported_at?: string | null; invoiced_at?: string | null; invoice_date?: string | null;
  pods?: Pod[]; billing_history?: { export_id: string; export_reference: string; is_reexport: boolean; created_at: string }[];
}

export interface Check { check: string; status: "pass" | "fail" | "missing" | "na"; detail: string }
export type ReviewCategory = "system" | "document_quality" | "business";
export type LocationStatus = "captured" | "permission_denied" | "unavailable" | "timeout" | "unsupported" | "not_provided";

export interface Extraction {
  id: string; extracted_data: ExtractedData | null; confidence_data: Record<string, number> | null;
  validation_data: {
    checks: Check[]; reasons: string[]; decision: string; priority: string | null; confidence_threshold: number;
    categories?: ReviewCategory[]; error_kind?: string | null; attempt_errors?: string[];
  } | null;
  model_provider: string; model_identifier: string; prompt_version: string; schema_version: string;
  processing_status: "SUCCEEDED" | "FAILED"; processing_error: string | null; processing_duration_ms: number | null; created_at: string;
  processing_id?: string | null; attempt_count?: number | null;
}

export interface ExtractedData {
  lr_number: { value: string | null; confidence: number };
  consignee: { value: string | null; confidence: number };
  delivered_quantity: { value: number | null; unit: string | null; confidence: number };
  delivery_date: { value: string | null; confidence: number };
  signature_visible: boolean | null; stamp_visible: boolean | null;
  shortage_detected: boolean | null; damage_detected: boolean | null;
  remarks: string | null; document_readable: boolean; observations: string[];
}

export type FlatValues = Partial<{
  lr_number: string | null; consignee: string | null; delivered_quantity: number | null; quantity_unit: string | null;
  delivery_date: string | null; signature_visible: boolean | null; stamp_visible: boolean | null;
  shortage_detected: boolean | null; damage_detected: boolean | null; remarks: string | null;
}>;

export interface Review {
  id: string; reviewer_id: string; decision: string; original_values: FlatValues | null;
  corrected_values: FlatValues | null; correction_reason: string | null; reviewed_at: string;
  approval_reason?: string | null; accepted_exceptions?: string[];
}

export interface Pod {
  id: string; trip_id: string; attempt_number: number; verification_status: PodStatus; upload_status: string; source: string;
  captured_at: string | null; captured_at_note: string; server_received_at: string;
  latitude: number | null; longitude: number | null; location_accuracy: number | null; location_note: string;
  location_status: LocationStatus;
  retake_count: number; retakes_remaining: number; review_reasons: string[]; review_priority: "high" | "medium" | "low" | null;
  review_categories: ReviewCategory[]; approved_exceptions: string[]; proposed_delivery_date: string | null;
  verification_method: "ai" | "human" | null; verified_at: string | null; rejection_reason: string | null; image_url: string;
  has_separate_original: boolean;
  upload_bytes?: number | null; original_bytes?: number | null; upload_size_policy?: "OK" | "OVERSIZE" | null; upload_limit_bytes?: number;
  trip: Trip;
  extraction?: Extraction | null; original_values?: FlatValues; effective_values?: FlatValues;
  expected?: { lr_number: string; consignee: string | null; delivery_date: string | null; expected_quantity: number | null; quantity_unit: string | null };
  extractions_history?: Extraction[]; reviews?: Review[]; confidence_threshold?: number;
  processing?: { attempts: number; last_error: string | null; started_at: string | null; stale: boolean };
}

export interface Page<T> { items: T[]; total: number; page: number; page_size: number }

export type TurnaroundKey = "delivery_to_pod_received" | "delivery_to_pod_verified" | "delivery_to_billing_export" | "delivery_to_invoice_recorded";
export interface TurnaroundStat { avg_days: number | null; median_days: number | null; count: number; period: { from: string; to: string } | null }

export interface Metrics {
  data_source: "demo" | "live"; total_trips: number; in_transit: number; delivered: number; pods_pending: number;
  pods_uploaded: number; ai_verified: number; human_verified: number; needs_review: number; retake_requests: number;
  billing_ready: number; exported: number; invoiced: number; trips_without_pod: number;
  avg_delivery_to_upload_hours: number | null; avg_upload_to_billing_ready_hours: number | null; pods_within_24h_pct: number | null;
  avg_billing_ready_to_export_hours?: number | null; approved_with_exception?: number; metric_definitions?: Record<string, string>;
  turnaround?: Record<TurnaroundKey, TurnaroundStat>; filters?: Record<string, string | null>;
  clients: ClientRow[]; branches: BranchRow[]; aging: { bucket: string; count: number; freight: number }[];
}
interface GroupRow { trips: number; pending_pod: number; needs_review: number; billing_ready: number; exported: number; freight_awaiting_pod: number }
export interface ClientRow extends GroupRow { client: string }
export interface BranchRow extends GroupRow { branch: string }

export interface MissingPod {
  trip_id: string; trip_reference: string; lr_number: string; client: string; driver: string | null; vehicle: string;
  ownership: string; destination: string; branch: string | null; delivery_date: string; days_since_delivery: number;
  overdue: boolean; freight_amount: number; pod_state: PodStatus;
  client_id?: string; billing_cycle?: string | null; driver_phone?: string | null; suggested_action?: "send_upload_link" | "call_driver";
}

export interface BillingRow {
  id: string; trip_reference: string; lr_number: string; eway_bill_number: string; client: { id: string; name: string };
  destination: string; vehicle: string; freight_amount: string; delivery_date: string | null; billing_cycle: string | null;
  pod_reference: string; pod_verified_at: string | null; verification_method: string | null;
  export_status: "EXPORTED" | "NOT_EXPORTED"; billing_status: BillingStatus;
  approved_exceptions?: string[]; delivery_date_source?: string | null; pod_id?: string; pod_image_reference?: string;
}

export interface ExportRecord {
  id: string; export_reference: string; client: string; billing_period: string | null; trip_count: number; total_freight: string;
  is_reexport: boolean; reexport_reason: string | null; created_at: string; trip_references: string[];
  trip_ids?: string[]; client_id?: string | null;
}

export interface ClientLink {
  id: string; client: { id: string; name: string }; label: string | null; scope: "trips" | "billing_cycle";
  billing_cycle: string | null; trip_count: number | null; state: "active" | "expired" | "revoked"; expires_at: string;
  created_at: string; revoked_at: string | null; access_count: number; last_accessed_at: string | null; url?: string;
}

export interface DriverLinkRow {
  id: string; trip_id: string; state: "active" | "expired" | "revoked"; phone_masked: string | null; created_at: string;
  expires_at: string; revoked_at: string | null; use_count: number;
  sms_log: { to: string; provider: string; status: string; created_at: string }[];
}

export interface ClientView {
  client: string; label: string | null; scope: string; billing_cycle: string | null; expires_at: string; note: string;
  trips: { trip_id: string; trip_reference: string; lr_number: string; delivery_date: string | null; destination: string;
    pod_status: "VERIFIED" | "PENDING"; pod_reference: string | null; pod_verified_at: string | null; has_image: boolean }[];
}

export interface AuditRow {
  id: string; user: string | null; entity_type: string; entity_id: string; action: string;
  previous_values: unknown; new_values: unknown; metadata: unknown; timestamp: string;
}

export interface Options { clients: { id: string; name: string; code: string }[]; branches: string[]; billing_cycles: string[]; data_source: "demo" | "live" }
