"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { X } from "lucide-react";
import { Card, PageHeader, Segmented, Tabs, Toolbar } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { affectedFields, CategoryBadge, PriorityBadge, ReasonBadge, REASON_LABELS } from "@/components/ui/badge";
import { SearchInput, Select } from "@/components/ui/input";
import { Pagination, Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { useAsync, useDebounced } from "@/hooks/use-async";
import { useSessionState } from "@/hooks/use-session-state";
import { services } from "@/services";
import { ago, dt } from "@/lib/format";

const PAGE = 20;
const TABS = ["NEEDS_REVIEW", "RETAKE_REQUESTED", "REJECTED"] as const;
type Status = (typeof TABS)[number];
const TAB_LABEL: Record<Status, string> = { NEEDS_REVIEW: "Needs review", RETAKE_REQUESTED: "Retake requested", REJECTED: "Rejected" };
const CATS = ["", "business", "document_quality", "system"] as const;
const CAT_LABEL: Record<(typeof CATS)[number], string> = { "": "All", business: "Business exceptions", document_quality: "Document quality", system: "System errors" };
const EMPTY = { reason: "", priority: "", client_id: "" };

export default function Reviews() {
  const router = useRouter();
  const [status, setStatus] = useSessionState<Status>("rp_rev_status", "NEEDS_REVIEW");
  const [category, setCategory] = useSessionState<string>("rp_rev_cat", "");
  const [f, setF] = useSessionState("rp_rev_filters", EMPTY);
  const [q, setQ] = useSessionState("rp_rev_q", "");
  const [page, setPage] = useSessionState("rp_rev_page", 1);
  const dq = useDebounced(q);
  const opts = useAsync(() => services.options(), []);
  const res = useAsync(() => services.reviews({ status, category, ...f, q: dq, page, page_size: PAGE }), [status, category, f.reason, f.priority, f.client_id, dq, page]);
  // Counts: one tiny request per tab and per category, so the numbers always match what the table would show.
  const tabCounts = useAsync(() => Promise.all(TABS.map((s) => services.reviews({ status: s, page_size: 1 }).then((r) => r.total))), []);
  const catCounts = useAsync(() => Promise.all(CATS.map((c) => services.reviews({ status, category: c, page_size: 1 }).then((r) => r.total))), [status]);
  const sf = (k: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLSelectElement>) => { setF({ ...f, [k]: e.target.value }); setPage(1); };
  const active = Object.values(f).filter(Boolean).length + (q ? 1 : 0) + (category ? 1 : 0);
  const clear = () => { setF(EMPTY); setQ(""); setCategory(""); setPage(1); };

  return (
    <>
      <PageHeader title="Review queue" subtitle="PODs the system could not clear on its own, highest priority and longest waiting first. Open one to inspect the document and decide." />
      <Tabs value={status} onChange={(v) => { setStatus(v); setPage(1); }} items={TABS.map((s, i) => [s, TAB_LABEL[s], tabCounts.data?.[i]] as const)} />
      <Card>
        <Toolbar className="gap-3">
          <SearchInput className="w-full sm:w-72" label="Search" placeholder="Trip or LR number" value={q} onChange={(v) => { setQ(v); setPage(1); }} />
          <Segmented label="Category" value={category} onChange={(v) => { setCategory(v); setPage(1); }} items={CATS.map((c, i) => [c, CAT_LABEL[c], catCounts.data?.[i]] as const)} />
        </Toolbar>
        <Toolbar className="gap-2 bg-surface-2/60 py-2.5">
          <Select aria-label="Reason" className="w-auto min-w-40 flex-1 sm:flex-none" value={f.reason} onChange={sf("reason")}><option value="">Any reason</option>{Object.entries(REASON_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
          <Select aria-label="Priority" className="w-auto min-w-32 flex-1 sm:flex-none" value={f.priority} onChange={sf("priority")}><option value="">Any priority</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></Select>
          <Select aria-label="Client" className="w-auto min-w-40 flex-1 sm:flex-none" value={f.client_id} onChange={sf("client_id")}><option value="">All clients</option>{opts.data?.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
          {active > 0 && <Button variant="ghost" size="sm" className="text-teal-700" onClick={clear}><X className="h-3.5 w-3.5" />Clear all</Button>}
          <span className="ml-auto text-[13px] text-muted" aria-live="polite">{res.data ? `${res.data.total} POD${res.data.total === 1 ? "" : "s"}` : ""}</span>
        </Toolbar>
        {res.loading && !res.data ? <TableSkeleton cols={6} /> : res.error ? <ErrorState message={res.error} onRetry={res.reload} /> :
          !res.data?.items.length ? (
            <EmptyState title={active ? "Nothing matches these filters" : status === "NEEDS_REVIEW" ? "Review queue is clear" : "Nothing in this list"}
              text={active ? "Try clearing the filters." : status === "NEEDS_REVIEW" ? "New exceptions will appear here as drivers upload documents." : undefined}
              action={active ? <Button variant="outline" size="sm" onClick={clear}>Clear filters</Button> : undefined} />
          ) : (
            <>
              <Table>
                <THead><tr><TH>Priority</TH><TH>Trip / LR</TH><TH>Why it needs a person</TH><TH className="hidden lg:table-cell">Affected</TH><TH>Waiting</TH><TH><span className="sr-only">Open</span></TH></tr></THead>
                <TBody>{res.data.items.map((p) => {
                  const fields = affectedFields(p.review_reasons);
                  return (
                    <TR key={p.id} className="cursor-pointer" onClick={(e) => { if (!(e.target as HTMLElement).closest("a,button")) router.push(`/pods/${p.id}`); }}>
                      <TD className="whitespace-nowrap"><PriorityBadge p={p.review_priority} /></TD>
                      <TD className="whitespace-nowrap"><div className="font-medium">{p.trip.trip_reference}</div><div className="max-w-56 truncate text-xs text-muted">{p.trip.lr_number} · {p.trip.client.name} · #{p.attempt_number}</div></TD>
                      <TD><div className="flex max-w-md flex-wrap gap-1">{p.review_categories?.map((c) => <CategoryBadge key={c} c={c} />)}{p.review_reasons.map((r) => <ReasonBadge key={r} code={r} />)}</div>
                        {status === "REJECTED" && p.rejection_reason && <div className="mt-1 max-w-md truncate text-xs text-muted" title={p.rejection_reason}>Rejected: {p.rejection_reason}</div>}</TD>
                      <TD className="hidden max-w-48 text-xs text-muted lg:table-cell">{fields.length ? fields.join(", ") : "—"}</TD>
                      <TD className="whitespace-nowrap" title={dt(p.server_received_at)}>{ago(p.server_received_at)}</TD>
                      <TD className="text-right"><Link className="text-[13px] font-medium text-teal-700 hover:underline" href={`/pods/${p.id}`}>{status === "NEEDS_REVIEW" ? "Review" : "Open"}</Link></TD>
                    </TR>
                  );
                })}</TBody>
              </Table>
              <Pagination page={page} pageSize={PAGE} total={res.data.total} onPage={setPage} />
            </>
          )}
      </Card>
    </>
  );
}
