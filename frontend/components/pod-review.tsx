"use client";
import { useMemo, useState } from "react";
import { AlertTriangle, Bot, CheckCircle2, CircleSlash, HelpCircle, ListChecks, RotateCcw, ShieldQuestion, UserCheck, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Callout, Card, CardHeader } from "@/components/ui/card";
import { Badge, CategoryBadge, PodBadge, PriorityBadge, ReasonBadge, REASON_LABELS } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { ImageViewer } from "@/components/auth-image";
import { services } from "@/services";
import { dt, humanize, pct } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Check, FlatValues, LocationStatus, Pod } from "@/types";

/** Business exceptions that can only be approved with a recorded rationale (mirrors backend EXCEPTION_REASONS). */
const EXCEPTION_REASONS = ["SHORTAGE", "DAMAGE", "QUANTITY_MISMATCH"];
const LOCATION_LABELS: Record<LocationStatus, string> = {
  captured: "Captured", permission_denied: "Permission denied on device", unavailable: "Device could not get a fix",
  timeout: "GPS timed out", unsupported: "No location support on device", not_provided: "No location information sent",
};
const STATUS_RANK: Record<string, number> = { fail: 3, missing: 2, na: 1, pass: 0 };
const CHECK_LABELS: Record<string, string> = {
  lr_number: "LR number matches trip", consignee: "Consignee matches trip", quantity: "Quantity matches trip", quantity_reading: "Quantity is readable",
  delivery_date: "Delivery date is plausible", shortage: "No shortage remark", damage: "No damage remark", stamp_visible: "Consignee stamp visible",
  signature_visible: "Signature visible", confidence: "AI confidence above threshold", readable: "Document is readable", required_fields: "Required fields present",
};

type FieldKey = keyof FlatValues;
interface Row { key: FieldKey; label: string; kind: "text" | "number" | "date" | "bool"; check?: string; conf?: string; expected: string }

const fmtBool = (v: unknown) => (v === true ? "Yes" : v === false ? "No" : "Unknown");
const show = (v: unknown, kind: Row["kind"]) => (v === null || v === undefined || v === "" ? "Not found" : kind === "bool" ? fmtBool(v) : String(v));

function CheckIcon({ s }: { s?: Check["status"] }) {
  if (s === "pass") return <CheckCircle2 className="h-4 w-4 text-teal" aria-label="Matches" />;
  if (s === "fail") return <XCircle className="h-4 w-4 text-danger" aria-label="Problem" />;
  if (s === "missing") return <AlertTriangle className="h-4 w-4 text-amber" aria-label="Missing" />;
  if (s === "na") return <CircleSlash className="h-4 w-4 text-neutral" aria-label="Not compared" />;
  return <HelpCircle className="h-4 w-4 text-neutral" aria-label="No check" />;
}

/** Labels where a finding came from, so a rule result is never mistaken for an AI opinion or a human decision. */
function Source({ kind }: { kind: "rule" | "ai" | "human" }) {
  const m = { rule: { icon: ListChecks, label: "Rule check" }, ai: { icon: Bot, label: "AI reading" }, human: { icon: UserCheck, label: "Reviewer" } }[kind];
  return <span className="inline-flex shrink-0 items-center gap-1 rounded bg-surface-2 px-1.5 py-0.5 text-[11px] font-medium text-muted ring-1 ring-inset ring-line"><m.icon className="h-3 w-3" aria-hidden />{m.label}</span>;
}

export function PodReview({ pod, onChanged }: { pod: Pod; onChanged: (p: Pod) => void }) {
  const toast = useToast();
  const ex = pod.extraction;
  const allChecks = useMemo(() => ex?.validation_data?.checks ?? [], [ex]);
  const checks = useMemo(() => Object.fromEntries(allChecks.map((c) => [c.check, c])), [allChecks]);
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
    { key: "delivery_date", label: "Delivery date", kind: "date", check: "delivery_date", conf: "delivery_date", expected: e?.delivery_date ? `${e.delivery_date} (trip record)` : "Not on trip record yet" },
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

  // Findings, grouped by where they come from.
  const ruleProblems = allChecks.filter((c) => c.status === "fail" || c.status === "missing").sort((a, b) => STATUS_RANK[b.status] - STATUS_RANK[a.status]);
  const lowConf = Object.entries(ex?.confidence_data ?? {}).filter(([, v]) => v < thr);
  const observations = ex?.extracted_data?.observations ?? [];
  const unreadable = ex?.extracted_data && ex.extracted_data.document_readable === false;

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
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      {/* Evidence */}
      <div className="space-y-4 xl:sticky xl:top-20">
        <Card className="p-3">
          <div className="mb-2 flex items-center justify-between gap-2 px-1">
            <h2 className="text-sm font-semibold">Original document</h2>
            {pod.has_separate_original && (
              <div className="inline-flex rounded-md border border-line bg-surface-2 p-0.5 text-xs" role="radiogroup" aria-label="Image version">
                {(["upload", "original"] as const).map((v) => (
                  <button key={v} type="button" role="radio" aria-checked={variant === v} onClick={() => setVariant(v)}
                    className={cn("rounded px-2 py-1 font-medium", variant === v ? "bg-surface text-ink shadow-[0_1px_2px_rgba(23,51,46,0.1)]" : "text-muted hover:text-ink")}>
                    {v === "upload" ? "Uploaded" : "Full resolution"}
                  </button>
                ))}
              </div>
            )}
          </div>
          <ImageViewer key={variant} path={`/pods/${pod.id}/image?variant=${variant}`} alt={`POD for ${pod.trip.trip_reference}, attempt ${pod.attempt_number}`} />
          <p className="mt-2 px-1 text-xs text-muted">The image is the source of truth. AI output is advisory and never approves a document on its own.</p>
        </Card>
        <Card>
          <details className="group">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm [&::-webkit-details-marker]:hidden">
              <span className="font-semibold">Capture provenance</span>
              <span className="truncate text-xs text-muted">Received {dt(pod.server_received_at)} · GPS {pod.latitude !== null ? "captured" : "not available"}<span className="ml-1 group-open:hidden">· Show</span></span>
            </summary>
            <dl className="grid grid-cols-2 gap-3 border-t border-line-soft p-4 text-[13px]">
              <div><dt className="text-xs text-muted">Server received</dt><dd>{dt(pod.server_received_at)}</dd></div>
              <div><dt className="text-xs text-muted">Device-reported time</dt><dd>{dt(pod.captured_at)}</dd></div>
              <div><dt className="text-xs text-muted">Device GPS</dt><dd data-testid="gps">{pod.latitude !== null ? `${pod.latitude?.toFixed(4)}, ${pod.longitude?.toFixed(4)} (±${Math.round(pod.location_accuracy ?? 0)} m)` : LOCATION_LABELS[pod.location_status] ?? "Not shared"}</dd></div>
              <div><dt className="text-xs text-muted">Source</dt><dd>{humanize(pod.source)}</dd></div>
              <div><dt className="text-xs text-muted">Upload size</dt><dd data-testid="upload-size">{pod.upload_bytes ? `${Math.round(pod.upload_bytes / 1024)} KB` : "—"}
                {pod.upload_size_policy === "OVERSIZE" && <Badge tone="amber" className="ml-1">over {Math.round((pod.upload_limit_bytes ?? 307200) / 1024)} KB limit</Badge>}</dd></div>
              <div><dt className="text-xs text-muted">Full-resolution original</dt><dd>{pod.has_separate_original ? `Received${pod.original_bytes ? ` (${(pod.original_bytes / 1048576).toFixed(1)} MB)` : ""}` : pod.upload_bytes ? "Not received yet" : "Single image on file"}</dd></div>
              <p className="col-span-2 text-xs text-muted">{pod.captured_at_note}. {pod.location_note}.</p>
            </dl>
          </details>
        </Card>
      </div>

      <div className="min-w-0 space-y-4">
        {/* Findings */}
        <Card>
          <CardHeader title="Verification findings" action={<><PriorityBadge p={pod.review_priority} /><PodBadge status={pod.verification_status} /></>} />
          <div className="space-y-3 p-4 text-sm">
            {pod.verification_status === "VERIFIED" && (
              <p className="flex items-start gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-teal" aria-hidden />
                <span>Verified by <strong>{pod.verification_method === "ai" ? "automated checks (all validations passed)" : "a billing executive"}</strong> on {dt(pod.verified_at)}.</span></p>
            )}
            {pod.verification_status === "VERIFIED" && pod.approved_exceptions?.length > 0 && (
              <Callout tone="warning" data-testid="approved-exception">
                Approved <strong>with exception</strong> ({pod.approved_exceptions.map((x) => REASON_LABELS[x] ?? x).join(", ")}){lastApproval?.approval_reason ? `: “${lastApproval.approval_reason}”` : ""}
              </Callout>
            )}
            {pod.verification_status === "REJECTED" && <Callout tone="error" title="Rejected">{pod.rejection_reason}</Callout>}
            {pod.verification_status === "RETAKE_REQUESTED" && <Callout tone="warning" title="Retake requested">The driver has been asked for a new photo. {pod.retakes_remaining} retake(s) left.</Callout>}

            {pod.review_reasons.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-muted">{canReview ? "Routed to review because" : "Reasons recorded"}</p>
                <div className="flex flex-wrap gap-1.5">
                  {pod.review_categories?.map((c) => <CategoryBadge key={c} c={c} />)}
                  {pod.review_reasons.map((r) => <ReasonBadge key={r} code={r} />)}
                </div>
              </div>
            )}
            {pod.review_categories?.includes("system") && (
              <Callout tone="info">This is a system failure, not a problem with the document or the delivery. Re-run the extraction, or review the image manually.</Callout>
            )}
            {ex?.model_provider === "seed-data" && (
              <Callout tone="info" data-testid="seed-fixture">Seeded demo fixture — these values were written by the seed script, not predicted by an AI model. Upload a POD to see a live extraction.</Callout>
            )}

            {ex && (
              <ul className="divide-y divide-line-soft rounded-lg border border-line-soft">
                {ruleProblems.length === 0 && allChecks.length > 0 && (
                  <li className="flex items-start gap-2.5 px-3 py-2.5"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-teal" aria-hidden /><span className="flex-1">All {allChecks.length} rule checks passed</span><Source kind="rule" /></li>
                )}
                {ruleProblems.map((c) => (
                  <li key={c.check} className="flex items-start gap-2.5 px-3 py-2.5">
                    <span className="mt-0.5"><CheckIcon s={c.status} /></span>
                    <div className="min-w-0 flex-1"><div className="font-medium">{CHECK_LABELS[c.check] ?? humanize(c.check)}</div><div className="text-xs text-muted">{c.detail}</div></div>
                    <Source kind="rule" />
                  </li>
                ))}
                {lowConf.length > 0 && (
                  <li className="flex items-start gap-2.5 px-3 py-2.5">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber" aria-hidden />
                    <div className="min-w-0 flex-1"><div className="font-medium">Low-confidence reading</div>
                      <div className="text-xs text-muted">The AI is less than {pct(thr)} sure about: {lowConf.map(([k, v]) => `${humanize(k)} (${pct(v)})`).join(", ")}. Check these against the image.</div></div>
                    <Source kind="ai" />
                  </li>
                )}
                {unreadable && (
                  <li className="flex items-start gap-2.5 px-3 py-2.5"><XCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-hidden />
                    <div className="flex-1"><div className="font-medium">Document reported as unreadable</div><div className="text-xs text-muted">Consider requesting a retake.</div></div><Source kind="ai" /></li>
                )}
                {observations.map((o, i) => (
                  <li key={i} className="flex items-start gap-2.5 px-3 py-2.5"><Bot className="mt-0.5 h-4 w-4 shrink-0 text-neutral" aria-hidden /><span className="flex-1 text-[13px]">{o}</span><Source kind="ai" /></li>
                ))}
                {lastApproval && (
                  <li className="flex items-start gap-2.5 px-3 py-2.5"><UserCheck className="mt-0.5 h-4 w-4 shrink-0 text-teal" aria-hidden />
                    <span className="flex-1 text-[13px]">Approved on {dt(lastApproval.reviewed_at)}{lastApproval.correction_reason ? ` — ${lastApproval.correction_reason}` : ""}</span><Source kind="human" /></li>
                )}
              </ul>
            )}
            {ex?.processing_status === "FAILED" && <Callout tone="error">AI processing failed: {ex.processing_error}</Callout>}
            {!ex && <p className="text-muted">No extraction yet.</p>}

            <p className="flex items-start gap-2 text-xs text-muted"><ShieldQuestion className="mt-px h-4 w-4 shrink-0 text-amber" aria-hidden /><span>Signature and stamp are reported as <em>visible</em> only. RouteProof does not authenticate them.</span></p>

            {ex && (
              <details className="text-xs text-muted">
                <summary className="cursor-pointer select-none font-medium text-teal-700 hover:underline">Technical details</summary>
                <p className="mt-1.5 leading-relaxed">
                  {(ex.validation_data?.attempt_errors?.length ?? 0) > 0 && <span>Provider retried {ex.validation_data!.attempt_errors!.length}× ({ex.validation_data!.attempt_errors!.join("; ")}). </span>}
                  {pod.processing && pod.processing.attempts > 1 && <span>Processing runs: {pod.processing.attempts}. </span>}
                  Model {ex.model_provider}/{ex.model_identifier} · prompt {ex.prompt_version} · schema {ex.schema_version} · {ex.processing_duration_ms ?? 0} ms · confidence threshold {pct(thr)} (configurable assumption)
                </p>
              </details>
            )}
          </div>
        </Card>

        {/* Comparison */}
        <Card>
          <CardHeader title="Extracted fields vs trip record" subtitle={canReview ? "Edit a value to correct it. The AI original is always preserved." : "Values read from the document, compared with the trip record"} />
          <div className="hidden grid-cols-[1.25rem_minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,1.2fr)] gap-x-3 border-b border-line-soft bg-surface-2 px-4 py-2 text-xs font-medium text-muted md:grid" aria-hidden>
            <span /><span>Field</span><span>Trip record</span><span>Read from POD</span>
          </div>
          <div className="divide-y divide-line-soft">
            {rows.map((r) => {
              // Quantity has two checks: could it be read at all, and does it match the trip. Show the worse one.
              const chks = [r.check ? checks[r.check] : undefined, r.key === "delivered_quantity" ? checks["quantity_reading"] : undefined].filter(Boolean) as Check[];
              const chk = [...chks].sort((a, b) => (STATUS_RANK[b.status] ?? 0) - (STATUS_RANK[a.status] ?? 0))[0];
              const conf = r.conf ? ex?.confidence_data?.[r.conf] : undefined;
              const o = orig[r.key]; const cur = eff[r.key];
              const corrected = JSON.stringify(cur ?? null) !== JSON.stringify(o ?? null);
              const low = conf !== undefined && o != null && conf < thr;
              const editVal = edits[r.key];
              return (
                <div key={r.key} className={cn("px-4 py-3 text-sm", chk?.status === "fail" && "bg-danger-50/50", chk?.status === "missing" && "bg-amber-50/50")} data-testid={`row-${r.key}`}>
                  <div className="grid grid-cols-[1.25rem_minmax(0,1fr)] gap-x-3 gap-y-1 md:grid-cols-[1.25rem_minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,1.2fr)]">
                    <div className="pt-0.5"><CheckIcon s={chk?.status} /></div>
                    <div className="flex flex-wrap items-center gap-1.5 font-medium">{r.label}{corrected && <Badge tone="info">Corrected</Badge>}</div>
                    <div className="col-start-2 md:col-start-auto"><span className="text-xs text-muted md:hidden">Trip record: </span>{r.expected}</div>
                    <div className="col-start-2 md:col-start-auto">
                      <span className="text-xs text-muted md:hidden">AI read: </span>
                      <span className={cn(o == null && "text-amber-700")}>{show(o, r.kind)}</span>
                      {conf !== undefined && <Badge tone={low ? "amber" : "neutral"} className="ml-1.5">{pct(conf)} confidence{low ? " · low" : ""}</Badge>}
                    </div>
                  </div>
                  <div className="ml-[2rem] md:ml-[2rem]">
                    {corrected && <div className="mt-1 text-xs">Current value: <strong>{show(cur, r.kind)}</strong></div>}
                    {chks.filter((c) => c.status !== "pass").map((c) => <div key={c.check} className="mt-1 text-xs text-muted">{c.detail}</div>)}
                    {r.key === "delivery_date" && canReview && <div className="mt-1 text-xs text-muted">The date on the document (not the upload date) becomes the trip&apos;s delivery date once approved.</div>}
                    {canReview && (
                      <div className="mt-2 max-w-sm">
                        {r.kind === "bool" ? (
                          <Select aria-label={`Correct ${r.label}`} className="h-8" value={editVal ?? (cur === true ? "yes" : cur === false ? "no" : "unknown")}
                            onChange={(ev) => setEdits({ ...edits, [r.key]: ev.target.value })}>
                            <option value="yes">Yes</option><option value="no">No</option><option value="unknown">Unknown</option>
                          </Select>
                        ) : (
                          <Input aria-label={`Correct ${r.label}`} className="h-8" type={r.kind === "date" ? "date" : r.kind === "number" ? "number" : "text"}
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

        {/* Decision */}
        {canReview && (
          <Card className="border-forest/25">
            <CardHeader title="Decision" subtitle={changed ? `${changed} field(s) corrected — the AI originals stay on record` : "No corrections"} />
            <div className="space-y-4 p-4">
              <div>
                <Label htmlFor="reason" hint={changed ? "(required for corrections)" : "(required for reject)"}>Reason / note</Label>
                <Textarea id="reason" value={reason} onChange={(ev) => setReason(ev.target.value)} placeholder="e.g. Stamp is on the reverse side; LR digit misread by AI" />
              </div>
              {openExceptions.length > 0 && (
                <div className="space-y-2 rounded-lg bg-amber-50 p-3 ring-1 ring-inset ring-[#efdcb4]" data-testid="exception-box">
                  <p className="text-[13px] text-amber-700"><strong>Open exception:</strong> {openExceptions.map((x) => REASON_LABELS[x] ?? x).join(", ")}. Approving accepts it for billing; the original flag stays on record.</p>
                  <div>
                    <Label htmlFor="approval" hint="(required to approve)">Why is this exception accepted?</Label>
                    <Textarea id="approval" value={approval} onChange={(ev) => setApproval(ev.target.value)} placeholder="e.g. Client confirmed by email that the 6-carton shortage is accepted" />
                  </div>
                </div>
              )}
              {missingDate && <Callout tone="error">No delivery date on file for this POD — enter the date shown on the document above before approving.</Callout>}
              <div className="flex flex-wrap gap-2 border-t border-line-soft pt-4">
                <Button variant="accent" onClick={() => setConfirm("APPROVE")}><CheckCircle2 className="h-4 w-4" />Approve</Button>
                <Button variant="outline" disabled={pod.retakes_remaining <= 0} title={pod.retakes_remaining <= 0 ? "Retake limit reached" : "Ask the driver for a new photo"} onClick={() => setConfirm("RETAKE")}>
                  <RotateCcw className="h-4 w-4" />Request retake ({pod.retakes_remaining} left)
                </Button>
                <Button variant="danger-outline" className="sm:ml-auto" onClick={() => setConfirm("REJECT")}><XCircle className="h-4 w-4" />Reject</Button>
              </div>
              {pod.retakes_remaining <= 0 && <p className="text-xs text-muted">Two retakes have already been requested; this document must be resolved by review.</p>}
            </div>
          </Card>
        )}

        {(pod.reviews?.length ?? 0) > 0 && (
          <Card>
            <CardHeader title="Review history" subtitle="Human decisions on this attempt" />
            <ul className="divide-y divide-line-soft text-sm">{pod.reviews!.map((r) => (
              <li key={r.id} className="px-4 py-3">
                <div className="flex items-center justify-between gap-2"><span className="flex items-center gap-2 font-medium"><UserCheck className="h-4 w-4 text-neutral" aria-hidden />{humanize(r.decision)}</span><span className="text-xs text-muted">{dt(r.reviewed_at)}</span></div>
                {r.correction_reason && <div className="mt-1 text-[13px] text-muted">{r.correction_reason}</div>}
                {r.accepted_exceptions && r.accepted_exceptions.length > 0 && (
                  <div className="mt-1.5 text-xs"><Badge tone="amber">Exception accepted: {r.accepted_exceptions.map((x) => REASON_LABELS[x] ?? x).join(", ")}</Badge> {r.approval_reason}</div>
                )}
                {r.corrected_values && Object.entries(r.corrected_values).map(([k, v]) => (
                  <div key={k} className="mt-1 text-xs"><span className="text-muted">{humanize(k)}:</span> <span className="line-through">{String((r.original_values as Record<string, unknown>)?.[k] ?? "null")}</span> → <strong>{String(v)}</strong></div>
                ))}
              </li>
            ))}</ul>
          </Card>
        )}
      </div>

      <ConfirmDialog open={confirm !== null} onClose={() => setConfirm(null)} loading={busy} danger={confirm === "REJECT"}
        title={confirm === "APPROVE" ? "Approve this POD?" : confirm === "REJECT" ? "Reject this POD?" : "Request a retake?"}
        confirmLabel={confirm === "APPROVE" ? "Approve" : confirm === "REJECT" ? "Reject" : "Request retake"}
        message={confirm === "APPROVE" ? <>The trip becomes billing-ready{changed ? ` with ${changed} corrected field(s)` : ""}{openExceptions.length ? " and the exception is accepted" : ""}. Invoices are still issued outside RouteProof.</>
          : confirm === "REJECT" ? "The rejection stays in the trip history and the driver can upload a new attempt." : "The driver will be asked to capture a new photo."}
        onConfirm={() => { if (blocker) { toast.error(blocker.toast); return; } void submit(confirm!); }}>
        {blocker && <Callout tone="error" className="mt-3">{blocker.detail}</Callout>}
      </ConfirmDialog>
    </div>
  );
}
