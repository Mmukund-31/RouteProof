"use client";
import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Link2, Phone } from "lucide-react";
import { Card, PageHeader } from "@/components/ui/card";
import { Badge, PodBadge } from "@/components/ui/badge";
import { Label, Select } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState, ErrorState, Skeleton, TableSkeleton } from "@/components/ui/states";
import { Kpi } from "@/components/kpi";
import { useAsync } from "@/hooks/use-async";
import { FilterBar, useSharedFilters } from "@/hooks/use-shared-filters";
import { services } from "@/services";
import { d, inr, inrCompact } from "@/lib/format";

const AGE = [["", "Any age"], ["1", "1+ days"], ["3", "3+ days"], ["7", "7+ days"], ["15", "15+ days"], ["30", "30+ days"]] as const;

export default function Operations() {
  const [f, setF] = useSharedFilters();
  const [minDays, setMinDays] = useState("");
  const opts = useAsync(() => services.options(), []);
  // One request: the KPIs below are totals of exactly these rows, never of a different filter scope.
  const miss = useAsync(() => services.missing({ ...f, min_days: minDays || undefined }),
    [f.date_from, f.date_to, f.client_id, f.branch, f.billing_cycle, minDays]);
  const items = miss.data?.items ?? [];

  return (
    <>
      <Link href="/dashboard" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="h-4 w-4" />Dashboard</Link>
      <PageHeader eyebrow="Overview" title="Missing PODs" subtitle="Delivered trips that cannot be billed because no usable proof of delivery is on file — oldest first." />
      <Card className="mb-4 p-4">
        <FilterBar f={f} onChange={setF} opts={opts.data} extra={
          <div><Label htmlFor="age">Days waiting</Label>
            <Select id="age" value={minDays} onChange={(e) => setMinDays(e.target.value)}>{AGE.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></div>
        } />
        <p className="mt-2 text-xs text-muted">Same filters as the dashboard (shared while this tab is open).</p>
      </Card>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {miss.data ? <>
          <Kpi label="Trips without POD" value={items.length} tone={items.length ? "amber" : "default"} />
          <Kpi label={`Overdue (> ${miss.data.overdue_after_days} days)`} value={miss.data.overdue_count} tone={miss.data.overdue_count ? "red" : "default"} />
          <Kpi label="Freight awaiting POD" value={inrCompact(miss.data.freight_blocked)} hint="Sum of freight on the rows below" />
          <Kpi label="Pending reviews" value={miss.data.pending_reviews} hint="In the same filter scope" href="/reviews" />
        </> : Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
      </div>
      <Card>
        {miss.loading && !miss.data ? <TableSkeleton cols={8} /> : miss.error ? <ErrorState message={miss.error} onRetry={miss.reload} /> :
          !items.length ? <EmptyState title="No missing PODs" text="Every delivered trip in this view has a POD on file." /> : (
            <Table>
              <THead><tr><TH>Trip</TH><TH>Client · cycle</TH><TH>Branch · destination</TH><TH>Driver · vehicle</TH><TH num>Waiting</TH><TH num>Freight</TH><TH>POD</TH><TH>Action</TH></tr></THead>
              <TBody>{items.map((i) => (
                <TR key={i.trip_id}>
                  <TD className="whitespace-nowrap"><Link href={`/trips/${i.trip_id}`} className="font-medium text-teal hover:underline">{i.trip_reference}</Link><div className="text-xs text-muted">{i.lr_number}</div></TD>
                  <TD className="max-w-32"><div className="truncate" title={i.client}>{i.client}</div><div className="text-xs text-muted">{i.billing_cycle ?? "—"}</div></TD>
                  <TD className="max-w-32"><div className="truncate" title={i.branch ?? "Unassigned"}>{i.branch ?? "Unassigned"}</div><div className="truncate text-xs text-muted">{i.destination}</div></TD>
                  <TD className="whitespace-nowrap">{i.driver ?? "—"}<div className="flex items-center gap-1.5 text-xs text-muted">{i.vehicle}<Badge tone={i.ownership === "hired" ? "amber" : "neutral"}>{i.ownership}</Badge></div></TD>
                  <TD num className="whitespace-nowrap">
                    <span className={i.overdue ? "inline-flex min-w-9 justify-center rounded-md bg-danger-50 px-1.5 py-0.5 font-semibold text-danger" : "inline-flex min-w-9 justify-center px-1.5"}>{i.days_since_delivery} d</span>
                    <div className="text-xs text-muted">since {d(i.delivery_date)}</div>
                  </TD>
                  <TD num className="whitespace-nowrap font-medium">{inr(i.freight_amount)}</TD>
                  <TD className="whitespace-nowrap"><PodBadge status={i.pod_state} /></TD>
                  <TD className="whitespace-nowrap">
                    {i.suggested_action === "send_upload_link" || !i.driver_phone ? (
                      <Link href={`/trips/${i.trip_id}?link=1`} title="Send the hired driver an upload link" className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-1 text-[13px] font-medium text-teal hover:bg-surface-2"><Link2 className="h-3.5 w-3.5" />Send link</Link>
                    ) : (
                      <a href={`tel:${i.driver_phone}`} title={`Call ${i.driver ?? "driver"}`} className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-1 text-[13px] font-medium text-teal hover:bg-surface-2"><Phone className="h-3.5 w-3.5" />Call</a>
                    )}
                  </TD>
                </TR>
              ))}</TBody>
            </Table>
          )}
      </Card>
      <p className="mt-3 text-xs text-muted">Hired-vehicle trips get an upload link; company drivers can be called directly. Open a trip for its full history.</p>
    </>
  );
}
