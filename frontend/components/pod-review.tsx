"use client";
import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, CircleSlash, HelpCircle, RotateCcw, ShieldQuestion, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Badge, CategoryBadge, PodBadge, PriorityBadge, ReasonBadge, REASON_LABELS } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { ImageViewer } from "@/components/auth-image";
import { services } from "@/services";
import { dt, pct } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Check, FlatValues, LocationStatus, Pod } from "@/types";

/** Business exceptions that can only be approved with a recorded rationale (mirrors backend EXCEPTION_REASONS). */
const EXCEPTION_REASONS = ["SHORTAGE", "DAMAGE", "QUANTITY_MISMATCH"];
const LOCATION_LABELS: Record<LocationStatus, string> = {
  captured: "Captured", permission_denied: "Permission denied on device", unavailable: "Device could not get a fix",
  timeout: "GPS timed out", unsupported: "No location support on device", not_provided: "No location information sent",
};
const STATUS_RANK: Record<string, number> = { fail: 3, missing: 2, na: 1, pass: 0 };

type FieldKey = keyof FlatValues;
interface Row { key: FieldKey; label: string; kind: "text" | "number" | "date" | "bool"; check?: string; conf?: string; expected: string }

const fmtBool = (v: unknown) => (v === true ? "Yes" : v === false ? "No" : "Unknown");
const show = (v: unknown, kind: Row["kind"]) => (v === null || v === undefined || v === "" ? "Not found" : kind === "bool" ? fmtBool(v) : String(v));

function CheckIcon({ s }: { s?: Check["status"] }) {
  if (s === "pass") return <CheckCircle2 className="h-4 w-4 text-teal" aria-label="Matches" />;
  if (s === "fail") return <XCircle className="h-4 w-4 text-danger" aria-label="Problem" />;
  if (s === "missing") return <AlertTriangle className="h-4 w-4 text-amber" aria-label="Missing" />;
  if (s === "na") return <CircleSlash className="h-4 w-4 text-muted" aria-label="Not compared" />;
  return <HelpCircle className="h-4 w-4 text-muted" />;
}

export function PodReview({ pod, onChanged }: { pod: Pod; onChanged: (p: Pod) => void }) {
  const toast = useToast();
  const ex = pod.extraction;
  const checks = useMemo(() => Object.fromEntries((ex?.validation_data?.checks ?? []).map((c) => [c.check, c])), [ex]);
  const thr = pod.confidence_threshold ?? 0.85;
  const orig = pod.original_values ?? {};
  const eff = pod.effective_values ?? {};
  const canReview = pod.verification_status === "NEEDS_REVIEW";
  const [edits, setEdits] = useState<Partial<Record<FieldKey, string>>>({});
  const [reason, setReason] = useState("");
  const [approval, setApproval] = useState("");
  const [confirm, setConfirm] = useState<null | "REJECT" | "RETAKE" | "APPROVE">(null);
  const [busy, setBusy] = useState(false);
  const [variant, setVariant] = useState<"upload" | "original">("upload");

  const e = pod.expected;
  const rows: Row[] = [
    { key: "lr_number", label: "LR number", kind: "text", check: "lr_number", conf: "lr_number", expected: e?.lr_number ?? "—" },
    { key: "consignee", label: "Consignee", kind: "text", check: "consignee", conf: "consignee", expected: e?.consignee ?? "Not on trip record" },
    { key: "delivered_quantity", label: "Delivered quantity", kind: "number", check: "quantity", conf: "delivered_quantity", expected: e?.expected_quantity != null ? String(e.expected_quantity) : "Not on trip record" },
    { key: "quantity_unit", label: "Quantity unit", kind: "text", expected: e?.quantity_unit ?? "—" },
    { key: "delivery_date", label: "Delivery date", kind: "date", check: "delivery_date", conf: "delivery_date", expected: e?.delivery_date ? `around ${e.delivery_date}` : "—" },
    { key: "signature_visible", label: "Signature visible", kind: "bool", check: "signature_visible", expected: "Visibility only" },
    { key: "stamp_visible", label: "Consignee stamp visible", kind: "bool", check: "stamp_visible", expected: "Visibility only" },
    { key: "shortage_detected", label: "Shortage remark", kind: "bool", check: "shortage", expected: "None expected" },
    { key: "damage_detected", label: "Damage remark", kind: "bool", check: "damage", expected: "None expected" },
    { key: "remarks", label: "Remarks (verbatim)", kind: "text", expected: "—" },
  ];

  function corrections() {
    const out: Record<string, unknown> = {};
    for (const r of rows) {
      const raw = edits[r.key];
      if (raw === undefined) continue;
      const val = r.kind === "bool" ? (raw === "yes" ? true : raw === "no" ? false : null) : raw === "" ? null : r.kind === "number" ? Number(raw) : raw;
      if (val !== (eff[r.key] ?? null)) out[r.key] = val;
    }
    return out;
  }
  const changed = Object.keys(corrections()).length;
  const finalValues: FlatValues = { ...eff, ...(corrections() as FlatValues) };
  // Same rule as the server: exceptions the checks raised, plus any shortage/damage flag on the final values.
  const openExceptions = [...new Set([
    ...pod.review_reasons.filter((r) => EXCEPTION_REASONS.includes(r)),
    ...(finalValues.shortage_detected ? ["SHORTAGE"] : []), ...(finalValues.damage_detected ? ["DAMAGE"] : []),
  ])].sort();
  const missingDate = !finalValues.delivery_date;
  const lastApproval = [...(pod.reviews ?? [])].reverse().find((r) => r.decision === "APPROVED");

  async function submit(decision: "APPROVE" | "REJECT" | "RETAKE") {
    setBusy(true);
    try {
      const body = decision === "APPROVE"
        ? { decision, corrections: corrections(), correction_reason: reason || undefined, approval_reason: approval.trim() || undefined }
        : { decision, rejection_reason: reason || undefined };
      const p = await services.review(pod.id, body);
      toast.success(decision === "APPROVE" ? "Approved — trip is now billing-ready" : decision === "REJECT" ? "POD rejected" : "Retake requested");
      setConfirm(null); setEdits({}); setReason(""); setApproval("");
      onChanged(p);
    } catch (err) { toast.error((err as Error).message); setConfirm(null); } finally { setBusy(false); }
  }

  const reasonNeeded = (confirm === "APPROVE" && changed > 0) || confirm === "REJECT";
  const approvalNeeded = confirm === "APPROVE" && openExceptions.length > 0;
  const blocker: null | { toast: string; detail: string } =
    reasonNeeded && !reason.trim() ? { toast: "Please enter a reason", detail: "A reason is required — enter it in the Decision box first." }
    : approvalNeeded && !approval.trim() ? { toast: "Please record why the exception is accepted", detail: "Record why this exception is being accepted (Decision box) before approving." }
    : confirm === "APPROVE" && missingDate ? { toast: "Please enter the delivery date", detail: "Enter the delivery date shown on the POD; it becomes the trip's delivery date." }
    : null;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <div className="space-y-4">
        <Card className="p-3">
          <div className="mb-2 flex items-center justify-between px-1">
            <h2 className="text-sm font-semibold">Original document</h2>
            {pod.has_separate_original && (
              <div className="flex gap-1 text-xs">
                {(["upload", "original"] as const).map((v) => <button key={v} onClick={() => setVariant(v)} className={cn("rounded-md px-2 py-1", variant === v ? "bg-forest text-white" : "bg-canvas")}>{v === "upload" ? "Uploaded" : "Original"}</button>)}
              </div>
            )}
          </div>
          <ImageViewer key={variant} path={`/pods/${pod.id}/image?variant=${variant}`} alt={`POD for ${pod.trip.trip_reference}, attempt ${pod.attempt_number}`} />
          <p className="mt-2 px-1 text-xs text-muted">The image is the source of truth. AI output is advisory and never approves a document on its own.</p>
        </Card>
        <Card>
          <CardHeader title="Capture provenance" />
          <dl className="grid grid-cols-2 gap-3 p-4 text-sm">
            <div><dt className="text-xs text-muted">Server received</dt><dd>{dt(pod.server_received_at)}</dd></div>
            <div><dt className="text-xs text-muted">Device-reported time</dt><dd>{dt(pod.captured_at)}</dd></div>
            <div><dt className="text-xs text-muted">Device GPS</dt><dd data-testid="gps">{pod.latitude !== null ? `${pod.latitude?.toFixed(4)}, ${pod.longitude?.toFixed(4)} (±${Math.round(pod.location_accuracy ?? 0)} m)` : LOCATION_LABELS[pod.location_status] ?? "Not shared"}</dd></div>
            <div><dt className="text-xs text-muted">Source</dt><dd>{pod.source.replace("_", " ")}</dd></div>
          </dl>
          <p className="border-t border-line px-4 py-2 text-xs text-muted">{pod.captured_at_note}. {pod.location_note}.</p>
        </Card>
      </div>

      <div className="space-y-4">
        <Card>
          <CardHeader title="Processing decision" action={<div className="flex items-center gap-2"><PriorityBadge p={pod.review_priority} /><PodBadge status={pod.verification_status} /></div>} />
          <div className="space-y-3 p-4 text-sm">
            {pod.review_categories?.length > 0 && <div className="flex flex-wrap gap-1.5">{pod.review_categories.map((c) => <CategoryBadge key={c} c={c} />)}</div>}
            {pod.review_reasons.length > 0 && <div className="flex flex-wrap gap-1.5">{pod.review_reasons.map((r) => <ReasonBadge key={r} code={r} />)}</div>}
            {pod.review_categories?.includes("system") && (
              <p className="rounded-lg bg-[#e8eef7] p-2 text-xs text-[#2f4f86]">This is a system failure, not a problem with the document or the delivery. Re-run the extraction, or review the image manually.</p>
            )}
            {pod.verification_status === "VERIFIED" && <p>Verified by <strong>{pod.verification_method === "ai" ? "automated checks (all validations passed)" : "a billing executive"}</strong> on {dt(pod.verified_at)}.</p>}
            {pod.verification_status === "VERIFIED" && pod.approved_exceptions?.length > 0 && (
              <p className="rounded-lg bg-amber-50 p-2 text-xs text-[#8a5f12]" data-testid="approved-exception">
                Approved <strong>with exception</strong> ({pod.approved_exceptions.map((e) => REASON_LABELS[e] ?? e).join(", ")}){lastApproval?.approval_reason ? `: “${lastApproval.approval_reason}”` : ""}
              </p>
            )}
            {pod.verification_status === "REJECTED" && <p className="text-danger">Rejected: {pod.rejection_reason}</p>}
            {ex ? (
              <p className="text-xs text-muted">
                {ex.processing_status === "FAILED" ? <span className="text-danger">AI processing failed: {ex.processing_error}. </span> : null}
                {(ex.validation_data?.attempt_errors?.length ?? 0) > 0 && <span>Provider retried {ex.validation_data!.attempt_errors!.length}× ({ex.validation_data!.attempt_errors!.join("; ")}). </span>}
                {pod.processing && pod.processing.attempts > 1 && <span>Processing runs: {pod.processing.attempts}. </span>}
                Model {ex.model_provider}/{ex.model_identifier} · prompt {ex.prompt_version} · schema {ex.schema_version} · {ex.processing_duration_ms ?? 0} ms · confidence threshold {pct(thr)} (configurable assumption)
              </p>
            ) : <p className="text-muted">No extraction yet.</p>}
            <p className="flex items-start gap-2 rounded-lg bg-amber-50 p-2 text-xs text-[#8a5f12]"><ShieldQuestion className="mt-0.5 h-4 w-4 shrink-0" />Signature and stamp are reported as <em>visible</em> only. RouteProof does not authenticate them.</p>
          </div>
        </Card>

        <Card>
          <CardHeader title="Extracted fields vs trip record" subtitle={canReview ? "Edit a value to correct it. The AI original is always preserved." : undefined} />
          <div className="divide-y divide-line">
            {rows.map((r) => {
              // Quantity has two checks: could it be read at all, and does it match the trip. Show the worse one.
              const chks = [r.check ? checks[r.check] : undefined, r.key === "delivered_quantity" ? checks["quantity_reading"] : undefined].filter(Boolean) as Check[];
              const chk = chks.sort((a, b) => (STATUS_RANK[b.status] ?? 0) - (STATUS_RANK[a.status] ?? 0))[0];
              const conf = r.conf ? ex?.confidence_data?.[r.conf] : undefined;
              const o = orig[r.key]; const cur = eff[r.key];
              const corrected = JSON.stringify(cur ?? null) !== JSON.stringify(o ?? null);
              const low = conf !== undefined && o != null && conf < thr;
              const editVal = edits[r.key];
              return (
                <div key={r.key} className={cn("grid grid-cols-[1.2rem_1fr] gap-x-3 px-4 py-3 text-sm", chk?.status === "fail" && "bg-danger-50/50", chk?.status === "missing" && "bg-amber-50/60")} data-testid={`row-${r.key}`}>
                  <div className="pt-0.5"><CheckIcon s={chk?.status} /></div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium">{r.label}</span>
                      <span className="flex items-center gap-1.5">
                        {conf !== undefined && <Badge tone={low ? "amber" : "neutral"}>{pct(conf)} confidence{low ? " · low" : ""}</Badge>}
                        {corrected && <Badge tone="blue">Corrected</Badge>}
                      </span>
                    </div>
                    <div className="mt-1 grid gap-x-4 gap-y-1 sm:grid-cols-2">
                      <div><span className="text-xs text-muted">Expected: </span>{r.expected}</div>
                      <div><span className="text-xs text-muted">AI read: </span><span className={cn(o == null && "text-amber")}>{show(o, r.kind)}</span></div>
                    </div>
                    {corrected && <div className="mt-1 text-xs">Current value: <strong>{show(cur, r.kind)}</strong></div>}
                    {chks.filter((c) => c.status !== "pass").map((c) => <div key={c.check} className="mt-1 text-xs text-muted">{c.detail}</div>)}
                    {r.key === "delivery_date" && canReview && <div className="mt-1 text-xs text-muted">The date on the document (not the upload date) becomes the trip&apos;s delivery date once approved.</div>}
                    {canReview && (
                      <div className="mt-2">
                        {r.kind === "bool" ? (
                          <Select aria-label={`Correct ${r.label}`} className="h-9" value={editVal ?? (cur === true ? "yes" : cur === false ? "no" : "unknown")}
                            onChange={(ev) => setEdits({ ...edits, [r.key]: ev.target.value })}>
                            <option value="yes">Yes</option><option value="no">No</option><option value="unknown">Unknown</option>
                          </Select>
                        ) : (
                          <Input aria-label={`Correct ${r.label}`} className="h-9" type={r.kind === "date" ? "date" : r.kind === "number" ? "number" : "text"}
                            value={editVal ?? (cur == null ? "" : String(cur))} onChange={(ev) => setEdits({ ...edits, [r.key]: ev.target.value })} />
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        {canReview && (
          <Card>
            <CardHeader title="Decision" subtitle={changed ? `${changed} field(s) corrected` : "No corrections"} />
            <div className="space-y-4 p-4">
              <div>
                <Label htmlFor="reason" hint={changed ? "(required for corrections)" : "(required for reject)"}>Reason / note</Label>
                <Textarea id="reason" value={reason} onChange={(ev) => setReason(ev.target.value)} placeholder="e.g. Stamp is on the reverse side; LR digit misread by AI" />
              </div>
              {openExceptions.length > 0 && (
                <div className="rounded-lg border border-amber/40 bg-amber-50 p-3" data-testid="exception-box">
                  <p className="text-sm text-[#8a5f12]"><strong>Open exception:</strong> {openExceptions.map((e) => REASON_LABELS[e] ?? e).join(", ")}. Approving accepts it for billing; the original flag stays on record.</p>
                  <Label htmlFor="approval" hint="(required to approve)">Why is this exception accepted?</Label>
                  <Textarea id="approval" value={approval} onChange={(ev) => setApproval(ev.target.value)} placeholder="e.g. Client confirmed by email that the 6-carton shortage is accepted" />
                </div>
              )}
              {missingDate && <p className="text-xs text-danger">No delivery date on file for this POD — enter the date shown on the document above before approving.</p>}
              <div className="flex flex-wrap gap-2">
                <Button variant="accent" onClick={() => setConfirm("APPROVE")}><CheckCircle2 className="h-4 w-4" />Approve</Button>
                <Button variant="warn" disabled={pod.retakes_remaining <= 0} title={pod.retakes_remaining <= 0 ? "Retake limit reached" : undefined} onClick={() => setConfirm("RETAKE")}>
                  <RotateCcw className="h-4 w-4" />Request retake ({pod.retakes_remaining} left)
                </Button>
                <Button variant="danger" onClick={() => setConfirm("REJECT")}><XCircle className="h-4 w-4" />Reject</Button>
              </div>
              {pod.retakes_remaining <= 0 && <p className="text-xs text-muted">Two retakes have already been requested; this document must be resolved by review.</p>}
            </div>
          </Card>
        )}

        {(pod.reviews?.length ?? 0) > 0 && (
          <Card>
            <CardHeader title="Review history" />
            <ul className="divide-y divide-line text-sm">{pod.reviews!.map((r) => (
              <li key={r.id} className="px-4 py-3">
                <div className="flex justify-between"><strong>{r.decision.replace("_", " ")}</strong><span className="text-xs text-muted">{dt(r.reviewed_at)}</span></div>
                {r.correction_reason && <div className="text-muted">{r.correction_reason}</div>}
                {r.accepted_exceptions && r.accepted_exceptions.length > 0 && (
                  <div className="mt-1 text-xs"><Badge tone="amber">Exception accepted: {r.accepted_exceptions.map((e) => REASON_LABELS[e] ?? e).join(", ")}</Badge> {r.approval_reason}</div>
                )}
                {r.corrected_values && Object.entries(r.corrected_values).map(([k, v]) => (
                  <div key={k} className="mt-1 text-xs"><code>{k}</code>: <span className="line-through">{String((r.original_values as Record<string, unknown>)?.[k] ?? "null")}</span> → <strong>{String(v)}</strong></div>
                ))}
              </li>
            ))}</ul>
          </Card>
        )}
      </div>

      <ConfirmDialog open={confirm !== null} onClose={() => setConfirm(null)} loading={busy} danger={confirm === "REJECT"}
        title={confirm === "APPROVE" ? "Approve this POD?" : confirm === "REJECT" ? "Reject this POD?" : "Request a retake?"}
        confirmLabel={confirm === "APPROVE" ? "Approve" : confirm === "REJECT" ? "Reject" : "Request retake"}
        message={confirm === "APPROVE" ? "The trip becomes billing-ready. Invoices are still issued outside RouteProof." : confirm === "REJECT" ? "The rejection stays in the trip history and the driver can upload a new attempt." : "The driver will be asked to capture a new photo."}
        onConfirm={() => { if (blocker) { toast.error(blocker.toast); return; } void submit(confirm!); }}>
        {blocker && <p className="mt-3 text-xs text-danger">{blocker.detail}</p>}
      </ConfirmDialog>
    </div>
  );
}
