import type { ExtractedData, Pod, Trip } from "@/types";

export const trip = (over: Partial<Trip> = {}): Trip => ({
  id: "trip-1", trip_reference: "TRP-66141", lr_number: "LR-66141", eway_bill_number: "331000066141",
  client: { id: "c1", name: "Company D (Packaged Foods)", code: "CMPD" }, vehicle: { registration: "MH17 BY 3092", type: "Container 24ft", ownership: "hired" },
  driver: { id: "d1", name: "Imran Shaikh" }, origin: "Chhatrapati Sambhajinagar", destination: "Indore", branch: "Pune", commodity: "Packaged foods",
  consignee_name: "Indore Warehouse", expected_quantity: 100, quantity_unit: "cartons", delivery_date: "2026-11-02", trip_status: "POD_PENDING",
  pod_status: "NEEDS_REVIEW", latest_pod_id: "pod-1", retakes_remaining: 2, rejection_reason: null, freight_amount: "41200.00",
  billing_status: "NOT_READY", billing_cycle: "2026-11-H1", ...over,
});

const extracted: ExtractedData = {
  lr_number: { value: "LR-66141", confidence: 0.98 }, consignee: { value: "Indore Warehouse", confidence: 0.94 },
  delivered_quantity: { value: 94, unit: "cartons", confidence: 0.72 }, delivery_date: { value: "2026-11-02", confidence: 0.91 },
  signature_visible: true, stamp_visible: true, shortage_detected: true, damage_detected: false, remarks: "Short by 6 cartons",
  document_readable: true, observations: [],
};

export const pod = (over: Partial<Pod> = {}): Pod => ({
  id: "pod-1", trip_id: "trip-1", attempt_number: 1, verification_status: "NEEDS_REVIEW", upload_status: "UPLOADED", source: "sms_link",
  captured_at: "2026-11-03T09:30:00Z", captured_at_note: "Reported by the capturing device; not independently verified",
  server_received_at: "2026-11-03T09:31:00Z", latitude: 19.87, longitude: 75.34, location_accuracy: 18, location_note: "Device-reported GPS; not proof of presence",
  location_status: "captured", review_categories: ["business", "document_quality"], approved_exceptions: [], proposed_delivery_date: "2026-11-02",
  retake_count: 0, retakes_remaining: 2, review_reasons: ["SHORTAGE", "QUANTITY_MISMATCH", "LOW_CONFIDENCE"], review_priority: "high", verification_method: null,
  verified_at: null, rejection_reason: null, image_url: "/api/v1/pods/pod-1/image", has_separate_original: false, trip: trip(),
  extraction: {
    id: "e1", extracted_data: extracted, confidence_data: { lr_number: 0.98, consignee: 0.94, delivered_quantity: 0.72, delivery_date: 0.91 },
    validation_data: {
      checks: [
        { check: "lr_number", status: "pass", detail: "Matches trip LR" }, { check: "consignee", status: "pass", detail: "ok" },
        { check: "quantity", status: "fail", detail: "Delivered 94.0 vs expected 100" }, { check: "delivery_date", status: "pass", detail: "ok" },
        { check: "shortage", status: "fail", detail: "Shortage remark: Short by 6 cartons" }, { check: "damage", status: "pass", detail: "none" },
        { check: "stamp_visible", status: "pass", detail: "visible" }, { check: "signature_visible", status: "missing", detail: "Signature visibility unknown" },
        { check: "confidence", status: "fail", detail: "Below 0.85 on: delivered_quantity" },
      ], reasons: ["SHORTAGE"], decision: "NEEDS_REVIEW", priority: "high", confidence_threshold: 0.85,
    },
    model_provider: "anthropic", model_identifier: "claude-sonnet-5-5", prompt_version: "pod-extract-1.0", schema_version: "1.0",
    processing_status: "SUCCEEDED", processing_error: null, processing_duration_ms: 2100, created_at: "2026-11-03T09:31:05Z",
  },
  original_values: { lr_number: "LR-66141", consignee: "Indore Warehouse", delivered_quantity: 94, quantity_unit: "cartons", delivery_date: "2026-11-02", signature_visible: true, stamp_visible: true, shortage_detected: true, damage_detected: false, remarks: "Short by 6 cartons" },
  effective_values: { lr_number: "LR-66141", consignee: "Indore Warehouse", delivered_quantity: 94, quantity_unit: "cartons", delivery_date: "2026-11-02", signature_visible: true, stamp_visible: true, shortage_detected: true, damage_detected: false, remarks: "Short by 6 cartons" },
  expected: { lr_number: "LR-66141", consignee: "Indore Warehouse", delivery_date: "2026-11-02", expected_quantity: 100, quantity_unit: "cartons" },
  reviews: [], confidence_threshold: 0.85, ...over,
});
