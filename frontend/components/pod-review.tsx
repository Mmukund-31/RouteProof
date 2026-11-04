"use client";
import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, CircleSlash, HelpCircle, RotateCcw, ShieldQuestion, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Badge, PodBadge, PriorityBadge, ReasonBadge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { ImageViewer } from "@/components/auth-image";
import { services } from "@/services";
import { dt, pct } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Check, FlatValues, Pod } from "@/types";

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

  async function submit(decision: "APPROVE" | "REJECT" | "RETAKE") {
    setBusy(true);
    try {
      const body = decision === "APPROVE"
        ? { decision, corrections: corrections(), correction_reason: reason || undefined }
        : { decision, rejection_reason: reason || undefined };
      const p = await services.review(pod.id, body);
      toast.success(decision === "APPROVE" ? "Approved — trip is now billing-ready" : decision === "REJECT" ? "POD rejected" : "Retake requested");
      setConfirm(null); setEdits({}); setReason("");
      onChanged(p);
    } catch (err) { toast.error((err as Error).message); setConfirm(null); } finally { setBusy(false); }
  }

  const reasonNeeded = (confirm === "APPROVE" && changed > 0) || confirm === "REJECT";

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
            <div><dt className="text-xs text-muted">Device GPS</dt><dd>{pod.latitude !== null ? `${pod.latitude?.toFixed(4)}, ${pod.longitude?.toFixed(4)} (±${Math.round(pod.location_accuracy ?? 0)} m)` : "Not shared"}</dd></div>
            <div><dt className="text-xs text-muted">Source</dt><dd>{pod.source.replace("_", " ")}</dd></div>
          </dl>
          <p className="border-t border-line px-4 py-2 text-xs text-muted">{pod.captured_at_note}. {pod.location_note}.</p>
        </Card>
      </div>

      <div className="space-y-4">
        <Card>
          <CardHeader title="Processing decision" action={<div className="flex items-center gap-2"><PriorityBadge p={pod.review_priority} /><PodBadge status={pod.verification_status} /></div>} />
          <div className="space-y-3 p-4 text-sm">
            {pod.review_reasons.length > 0 && <div className="flex flex-wrap gap-1.5">{pod.review_reasons.map((r) => <ReasonBadge key={r} code={r} />)}</div>}
            {pod.verification_status === "VERIFIED" && <p>Verified by <strong>{pod.verification_method === "ai" ? "automated checks (all validations passed)" : "a billing executive"}</strong> on {dt(pod.verified_at)}.</p>}
            {pod.verification_status === "REJECTED" && <p className="text-danger">Rejected: {pod.rejection_reason}</p>}
            {ex ? (
              <p className="text-xs text-muted">
                {ex.processing_status === "FAILED" ? <span className="text-danger">AI processing failed: {ex.processing_error}. </span> : null}
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
              const chk = r.check ? checks[r.check] : undefined;
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
                    {chk && chk.status !== "pass" && <div className="mt-1 text-xs text-muted">{chk.detail}</div>}
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
        onConfirm={() => { if (reasonNeeded && !reason.trim()) { toast.error("Please enter a reason"); return; } void submit(confirm!); }}>
        {reasonNeeded && !reason.trim() && <p className="mt-3 text-xs text-danger">A reason is required — enter it in the Decision box first.</p>}
      </ConfirmDialog>
    </div>
  );
}
