"use client";
import { useState } from "react";
import Link from "next/link";
import { Card, PageHeader } from "@/components/ui/card";
import { Badge, PodBadge } from "@/components/ui/badge";
import { Select } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState, ErrorState, Skeleton, TableSkeleton } from "@/components/ui/states";
import { Kpi } from "@/components/kpi";
import { useAsync } from "@/hooks/use-async";
import { services } from "@/services";
import { d, hours, inr, inrCompact } from "@/lib/format";

export default function Operations() {
  const [client, setClient] = useState("");
  const [onlyOverdue, setOnlyOverdue] = useState(false);
  const opts = useAsync(() => services.options(), []);
  const miss = useAsync(() => services.missing({ client_id: client }), [client]);
  const m = useAsync(() => services.metrics({ client_id: client }), [client]);
  const items = (miss.data?.items ?? []).filter((i) => !onlyOverdue || i.overdue);

  return (
    <>
      <PageHeader title="Missing PODs" subtitle="Delivered trips that cannot be billed because no usable proof of delivery is on file — oldest first." />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {miss.data ? <>
          <Kpi label="Trips without POD" value={miss.data.items.length} tone={miss.data.items.length ? "amber" : "default"} />
          <Kpi label={`Overdue (> ${miss.data.overdue_after_days} days)`} value={miss.data.overdue_count} tone={miss.data.overdue_count ? "red" : "default"} />
          <Kpi label="Freight held back" value={inrCompact(miss.data.freight_blocked)} hint="Sum of freight on these trips" />
          <Kpi label="Pending reviews" value={miss.data.pending_reviews} href="/reviews" />
        </> : Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
        {m.data && <Kpi label="Avg POD upload time" value={hours(m.data.avg_delivery_to_upload_hours)} hint={`Upload → billing-ready ${hours(m.data.avg_upload_to_billing_ready_hours)}`} />}
      </div>
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b border-line p-4">
          <Select className="w-56" aria-label="Client" value={client} onChange={(e) => setClient(e.target.value)}><option value="">All clients</option>{opts.data?.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={onlyOverdue} onChange={(e) => setOnlyOverdue(e.target.checked)} />Overdue only</label>
        </div>
        {miss.loading && !miss.data ? <TableSkeleton cols={7} /> : miss.error ? <ErrorState message={miss.error} onRetry={miss.reload} /> :
          !items.length ? <EmptyState title="No missing PODs" text="Every delivered trip in this view has a POD on file." /> : (
            <Table>
              <THead><tr><TH>Trip / LR</TH><TH>Client</TH><TH>Driver / vehicle</TH><TH>Destination</TH><TH>Delivered</TH><TH num>Days waiting</TH><TH num>Freight</TH><TH>POD state</TH></tr></THead>
              <TBody>{items.map((i) => (
                <TR key={i.trip_id}>
                  <TD><Link href={`/trips/${i.trip_id}`} className="font-medium text-teal hover:underline">{i.trip_reference}</Link><div className="text-xs text-muted">{i.lr_number}</div></TD>
                  <TD>{i.client}</TD>
                  <TD>{i.driver ?? "—"}<div className="text-xs text-muted">{i.vehicle} <Badge tone={i.ownership === "hired" ? "amber" : "neutral"}>{i.ownership}</Badge></div></TD>
                  <TD>{i.destination}<div className="text-xs text-muted">{i.branch}</div></TD>
                  <TD className="whitespace-nowrap">{d(i.delivery_date)}</TD>
                  <TD num><span className={i.overdue ? "font-semibold text-danger" : ""}>{i.days_since_delivery}</span>{i.overdue && <div className="text-xs text-danger">overdue</div>}</TD>
                  <TD num>{inr(i.freight_amount)}</TD>
                  <TD><PodBadge status={i.pod_state} /></TD>
                </TR>
              ))}</TBody>
            </Table>
          )}
      </Card>
      <p className="mt-3 text-xs text-muted">{m.data?.data_source === "demo" ? "Seeded demo data. " : ""}Hired-vehicle trips can be sent an upload link from the trip page.</p>
    </>
  );
}
