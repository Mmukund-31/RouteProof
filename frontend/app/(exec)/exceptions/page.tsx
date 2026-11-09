"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { X } from "lucide-react";
import { Card, PageHeader, Segmented, Tabs, Toolbar } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { affectedFields, Badge, PriorityBadge, ReasonBadge, REASON_LABELS, reasonCategory } from "@/components/ui/badge";
import { SearchInput, Select } from "@/components/ui/input";
import { Pagination, Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { useAsync, useDebounced } from "@/hooks/use-async";
import { useSessionState } from "@/hooks/use-session-state";
import { services } from "@/services";
import { ago, d, dt } from "@/lib/format";
import type { Pod } from "@/types";

const PAGE = 20;
/** Resolution lifecycle of an exception, mapped onto the POD state machine. */
const STAGES = ["NEEDS_REVIEW", "RETAKE_REQUESTED", "VERIFIED", "REJECTED"] as const;
type Stage = (typeof STAGES)[number];
const STAGE_LABEL: Record<Stage, string> = { NEEDS_REVIEW: "Open", RETAKE_REQUESTED: "Awaiting retake", VERIFIED: "Accepted", REJECTED: "Rejected" };
const SCOPES = [["business", "Business exceptions"], ["document_quality", "Document quality"]] as const;
type Scope = (typeof SCOPES)[number][0];

/** The evidence behind the exception in one line: what the document says against what the trip expects. */
function evidence(p: Pod): string[] {
  const v = p.effective_values ?? {}, e = p.expected, out: string[] = [];
  const r = new Set(p.review_reasons);
  if ((r.has("QUANTITY_MISMATCH") || r.has("SHORTAGE")) && v.delivered_quantity != null && e?.expected_quantity != null)
    out.push(`Delivered ${v.delivered_quantity} of ${e.expected_quantity} ${e.quantity_unit ?? ""}`.trim());
  if (r.has("LR_MISMATCH") && v.lr_number) out.push(`POD shows ${v.lr_number}, trip is ${e?.lr_number ?? "—"}`);
  if (r.has("CONSIGNEE_MISMATCH") && v.consignee) out.push(`Consignee on POD: ${v.consignee}`);
  if ((r.has("DATE_DIFFERS_FROM_TRIP") || r.has("DATE_IMPLAUSIBLE")) && v.delivery_date) out.push(`Date on POD ${d(v.delivery_date)}${e?.delivery_date ? `, trip ${d(e.delivery_date)}` : ""}`);
  if (v.remarks) out.push(`Remark: “${v.remarks}”`);
  return out;
}

function Resolution({ p, stage }: { p: Pod; stage: Stage }) {
  const approval = [...(p.reviews ?? [])].reverse().find((r) => r.decision === "APPROVED");
  const superseded = p.trip.latest_pod_id && p.trip.latest_pod_id !== p.id;
  if (stage === "NEEDS_REVIEW") return <span className="text-[13px]">Awaiting decision<div className="text-xs text-muted" title={dt(p.server_received_at)}>raised {ago(p.server_received_at)}</div></span>;
  if (stage === "RETAKE_REQUESTED") return (
    <span className="text-[13px]">{superseded ? <Badge tone="info">New attempt received</Badge> : "Driver asked for a new photo"}
      <div className="text-xs text-muted">{p.retakes_remaining} retake(s) left</div></span>
  );
  if (stage === "VERIFIED") return (
    <span className="text-[13px]">{p.approved_exceptions?.length ? <>Accepted: {p.approved_exceptions.map((x) => REASON_LABELS[x] ?? x).join(", ")}</> : "Cleared after review"}
      {approval?.approval_reason && <div className="max-w-64 truncate text-xs text-muted" title={approval.approval_reason}>“{approval.approval_reason}”</div>}
      {p.verified_at && <div className="text-xs text-muted">{d(p.verified_at)}</div>}</span>
  );
  return <span className="text-[13px]">{superseded ? <Badge tone="info">New attempt received</Badge> : "Rejected"}<div className="max-w-64 truncate text-xs text-muted" title={p.rejection_reason ?? ""}>{p.rejection_reason}</div></span>;
}

export default function Exceptions() {
  const router = useRouter();
  const [stage, setStage] = useSessionState<Stage>("rp_exc_stage", "NEEDS_REVIEW");
  const [scope, setScope] = useSessionState<Scope>("rp_exc_scope", "business");
  const [q, setQ] = useSessionState("rp_exc_q", "");
  const [reason, setReason] = useSessionState("rp_exc_reason", "");
  const [client, setClient] = useSessionState("rp_exc_client", "");
  const [page, setPage] = useSessionState("rp_exc_page", 1);
  const dq = useDebounced(q);
  const opts = useAsync(() => services.options(), []);
  const res = useAsync(() => services.reviews({ status: stage, category: scope, reason, client_id: client, q: dq, page, page_size: PAGE }),
    [stage, scope, reason, client, dq, page]);
  const counts = useAsync(() => Promise.all(STAGES.map((s) => services.reviews({ status: s, category: scope, page_size: 1 }).then((r) => r.total))), [scope]);
  const reasons = Object.entries(REASON_LABELS).filter(([k]) => reasonCategory(k) === scope);
  const active = (q ? 1 : 0) + (reason ? 1 : 0) + (client ? 1 : 0);
  const clear = () => { setQ(""); setReason(""); setClient(""); setPage(1); };

  return (
    <>
      <PageHeader title="Exceptions"
        subtitle="Deliveries where the document disagrees with the trip — shortage, damage, quantity, LR, consignee or date — tracked from detection to resolution. Resolve each one from its review screen; every decision and its reason stay on record." />
      <Tabs value={stage} onChange={(v) => { setStage(v); setPage(1); }} items={STAGES.map((s, i) => [s, STAGE_LABEL[s], counts.data?.[i]] as const)} />
      <Card>
        <Toolbar className="gap-3">
          <Segmented label="Exception type" value={scope} onChange={(v) => { setScope(v); setReason(""); setPage(1); }} items={SCOPES} />
          <SearchInput className="w-full sm:w-64" label="Search exceptions" placeholder="Trip or LR number" value={q} onChange={(v) => { setQ(v); setPage(1); }} />
          <Select aria-label="Exception" className="w-auto min-w-40 flex-1 sm:flex-none" value={reason} onChange={(e) => { setReason(e.target.value); setPage(1); }}>
            <option value="">Any {scope === "business" ? "exception" : "issue"}</option>{reasons.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          <Select aria-label="Client" className="w-auto min-w-40 flex-1 sm:flex-none" value={client} onChange={(e) => { setClient(e.target.value); setPage(1); }}>
            <option value="">All clients</option>{opts.data?.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          {active > 0 && <Button variant="ghost" size="sm" className="text-teal-700" onClick={clear}><X className="h-3.5 w-3.5" />Clear</Button>}
        </Toolbar>
        {res.loading && !res.data ? <TableSkeleton cols={6} /> : res.error ? <ErrorState message={res.error} onRetry={res.reload} /> :
          !res.data?.items.length ? (
            <EmptyState title={stage === "NEEDS_REVIEW" && !active ? "No open exceptions" : "Nothing here"}
              text={stage === "NEEDS_REVIEW" && !active ? "When a POD disagrees with its trip, it appears here until someone resolves it." : active ? "Try clearing the filters." : undefined} />
          ) : (
            <>
              <Table>
                <THead><tr><TH>Severity</TH><TH>Trip</TH><TH>Exception</TH><TH className="hidden md:table-cell">What the document shows</TH><TH>Resolution</TH><TH><span className="sr-only">Open</span></TH></tr></THead>
                <TBody>{res.data.items.map((p) => {
                  const ev = evidence(p);
                  const own = p.review_reasons.filter((r) => reasonCategory(r) === scope);
                  return (
                    <TR key={p.id} className="cursor-pointer align-top" onClick={(e) => { if (!(e.target as HTMLElement).closest("a,button")) router.push(`/pods/${p.id}`); }}>
                      <TD className="whitespace-nowrap align-top"><PriorityBadge p={p.review_priority} /></TD>
                      <TD className="whitespace-nowrap align-top"><Link href={`/trips/${p.trip_id}`} className="font-medium hover:text-teal-700 hover:underline">{p.trip.trip_reference}</Link>
                        <div className="max-w-48 truncate text-xs text-muted">{p.trip.lr_number} · {p.trip.client.name}</div></TD>
                      <TD className="align-top"><div className="flex max-w-xs flex-wrap gap-1">{own.map((r) => <ReasonBadge key={r} code={r} />)}</div>
                        <div className="mt-1 text-xs text-muted">Affects: {affectedFields(own).join(", ") || "—"}</div></TD>
                      <TD className="hidden max-w-sm align-top text-[13px] md:table-cell">{ev.length ? <ul className="space-y-0.5">{ev.map((x) => <li key={x} className="truncate" title={x}>{x}</li>)}</ul> : <span className="text-muted">Open to inspect the image</span>}</TD>
                      <TD className="align-top"><Resolution p={p} stage={stage} /></TD>
                      <TD className="whitespace-nowrap text-right align-top"><Link href={`/pods/${p.id}`} className="text-[13px] font-medium text-teal-700 hover:underline">{stage === "NEEDS_REVIEW" ? "Resolve" : "View"}</Link></TD>
                    </TR>
                  );
                })}</TBody>
              </Table>
              <Pagination page={page} pageSize={PAGE} total={res.data.total} onPage={setPage} />
            </>
          )}
      </Card>
      <p className="mt-3 text-xs text-muted">
        Accepting an exception requires a recorded reason and keeps the original flag on the POD; the trip then becomes billing-ready.
        System errors (AI failures) are not exceptions — find them in the <Link href="/reviews" className="text-teal-700 hover:underline">review queue</Link>.
      </p>
    </>
  );
}
