"use client";
import { useState } from "react";
import { Card, PageHeader } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { Pagination, Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { useAsync, useDebounced } from "@/hooks/use-async";
import { services } from "@/services";
import { dt, humanize } from "@/lib/format";

export default function AuditPage() {
  const [action, setAction] = useState("");
  const [entity, setEntity] = useState("");
  const [page, setPage] = useState(1);
  const da = useDebounced(action);
  const res = useAsync(() => services.audit({ action: da, entity_type: entity, page, page_size: 25 }), [da, entity, page]);
  return (
    <>
      <PageHeader title="Audit history" subtitle="Append-only record of uploads, AI processing, corrections, approvals and exports." />
      <Card>
        <div className="grid gap-3 border-b border-line p-4 sm:grid-cols-3">
          <Input placeholder="Filter by action (e.g. pod.verified)" aria-label="Action" value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }} />
          <Select aria-label="Entity" value={entity} onChange={(e) => { setEntity(e.target.value); setPage(1); }}>
            <option value="">All entities</option>{["pod", "trip", "billing_export", "driver_link", "user"].map((x) => <option key={x} value={x}>{humanize(x)}</option>)}
          </Select>
        </div>
        {res.loading && !res.data ? <TableSkeleton cols={5} /> : res.error ? <ErrorState message={res.error} onRetry={res.reload} /> :
          !res.data?.items.length ? <EmptyState title="No audit entries" /> : (
            <>
              <Table>
                <THead><tr><TH>When</TH><TH>Who</TH><TH>Action</TH><TH>Entity</TH><TH>Details</TH></tr></THead>
                <TBody>{res.data.items.map((r) => (
                  <TR key={r.id}>
                    <TD className="whitespace-nowrap">{dt(r.timestamp)}</TD><TD>{r.user ?? "System / link"}</TD>
                    <TD className="font-medium">{r.action}</TD><TD>{humanize(r.entity_type)}<div className="text-xs text-muted">{r.entity_id.slice(0, 8)}</div></TD>
                    <TD className="max-w-md text-xs text-muted">
                      {(r.new_values || r.metadata) ? <details><summary className="cursor-pointer text-teal">View</summary><pre className="mt-1 whitespace-pre-wrap break-words">{JSON.stringify({ previous: r.previous_values, new: r.new_values, metadata: r.metadata }, null, 1)}</pre></details> : "—"}
                    </TD>
                  </TR>
                ))}</TBody>
              </Table>
              <Pagination page={page} pageSize={25} total={res.data.total} onPage={setPage} />
            </>
          )}
      </Card>
    </>
  );
}
