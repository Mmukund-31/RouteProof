"use client";
import { useState } from "react";
import Link from "next/link";
import { Card, PageHeader } from "@/components/ui/card";
import { CATEGORY_LABELS, CategoryBadge, PodBadge, PriorityBadge, ReasonBadge, REASON_LABELS } from "@/components/ui/badge";
import { Input, Select } from "@/components/ui/input";
import { Pagination, Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { useAsync, useDebounced } from "@/hooks/use-async";
import { services } from "@/services";
import { dt } from "@/lib/format";

const TABS = [["NEEDS_REVIEW", "Needs review"], ["RETAKE_REQUESTED", "Retake requested"], ["REJECTED", "Rejected"]] as const;

export default function Reviews() {
  const [status, setStatus] = useState<string>("NEEDS_REVIEW");
  const [f, setF] = useState({ category: "", reason: "", priority: "", client_id: "" });
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const dq = useDebounced(q);
  const opts = useAsync(() => services.options(), []);
  const res = useAsync(() => services.reviews({ status, ...f, q: dq, page, page_size: 15 }), [status, f.category, f.reason, f.priority, f.client_id, dq, page]);
  const sf = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLSelectElement>) => { setF({ ...f, [k]: e.target.value }); setPage(1); };

  return (
    <>
      <PageHeader title="Human review queue" subtitle="Documents the system could not clear on its own, highest priority first." />
      <div className="mb-4 flex gap-1 rounded-lg bg-black/5 p-1 w-fit" role="tablist">
        {TABS.map(([v, l]) => (
          <button key={v} role="tab" aria-selected={status === v} onClick={() => { setStatus(v); setPage(1); }}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${status === v ? "bg-surface shadow-sm" : "text-muted"}`}>{l}</button>
        ))}
      </div>
      <Card>
        <div className="grid gap-3 border-b border-line p-4 sm:grid-cols-2 lg:grid-cols-5">
          <Input placeholder="Search trip or LR…" aria-label="Search" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          <Select aria-label="Category" value={f.category} onChange={sf("category")}><option value="">Any category</option>{Object.entries(CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
          <Select aria-label="Reason" value={f.reason} onChange={sf("reason")}><option value="">Any reason</option>{Object.entries(REASON_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
          <Select aria-label="Priority" value={f.priority} onChange={sf("priority")}><option value="">Any priority</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></Select>
          <Select aria-label="Client" value={f.client_id} onChange={sf("client_id")}><option value="">All clients</option>{opts.data?.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
        </div>
        {res.loading && !res.data ? <TableSkeleton cols={6} /> : res.error ? <ErrorState message={res.error} onRetry={res.reload} /> :
          !res.data?.items.length ? <EmptyState title="Nothing in this queue" text="New exceptions will appear here as drivers upload documents." /> : (
            <>
              <Table>
                <THead><tr><TH>Priority</TH><TH>Trip / LR</TH><TH>Client</TH><TH>Why it needs a person</TH><TH>Received</TH><TH>Status</TH><TH><span className="sr-only">Open</span></TH></tr></THead>
                <TBody>{res.data.items.map((p) => (
                  <TR key={p.id}>
                    <TD><PriorityBadge p={p.review_priority} /></TD>
                    <TD><div className="font-medium">{p.trip.trip_reference}</div><div className="text-xs text-muted">{p.trip.lr_number} · attempt #{p.attempt_number}</div></TD>
                    <TD>{p.trip.client.name}</TD>
                    <TD><div className="flex max-w-sm flex-wrap gap-1">{p.review_categories?.map((c) => <CategoryBadge key={c} c={c} />)}{p.review_reasons.map((r) => <ReasonBadge key={r} code={r} />)}</div></TD>
                    <TD className="whitespace-nowrap">{dt(p.server_received_at)}</TD>
                    <TD><PodBadge status={p.verification_status} /></TD>
                    <TD><Link className="font-medium text-teal hover:underline" href={`/pods/${p.id}`}>Review</Link></TD>
                  </TR>
                ))}</TBody>
              </Table>
              <Pagination page={page} pageSize={15} total={res.data.total} onPage={setPage} />
            </>
          )}
      </Card>
    </>
  );
}
