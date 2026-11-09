"use client";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardHeader, PageHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { Kpi } from "@/components/kpi";
import { useAsync } from "@/hooks/use-async";
import { services } from "@/services";
import { d as fmtDate, dt, hours, humanize, inrCompact } from "@/lib/format";
import { FilterBar, useSharedFilters } from "@/hooks/use-shared-filters";
import type { Metrics, TurnaroundKey } from "@/types";

const TURNAROUND: { key: TurnaroundKey; label: string; empty: string }[] = [
  { key: "delivery_to_pod_received", label: "Delivery → POD received", empty: "No PODs received yet" },
  { key: "delivery_to_pod_verified", label: "Delivery → verified POD", empty: "No verified PODs yet" },
  { key: "delivery_to_billing_export", label: "Delivery → billing export", empty: "Nothing exported yet" },
  { key: "delivery_to_invoice_recorded", label: "Delivery → invoice recorded", empty: "No invoice dates recorded yet" },
];

/** Business-cycle turnaround in days, each with the sample it is based on, so a figure from three demo trips reads as that. */
function Turnaround({ m }: { m: Metrics }) {
  if (!m.turnaround) return null;
  return (
    <section aria-label="Turnaround" className="mt-6">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">Delivery-to-cash turnaround</h2>
        <p className="text-xs text-muted">Days from the start of the delivery date. Exporting a CSV is not invoicing: the last figure only counts invoice dates a billing executive recorded.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {TURNAROUND.map(({ key, label, empty }) => {
          const s = m.turnaround![key];
          return (
            <div key={key} data-testid={`tat-${key}`} title={m.metric_definitions?.[key]}>
              <Kpi label={label} value={s.avg_days === null ? "—" : `${s.avg_days} d`}
                hint={s.count ? `median ${s.median_days} d · n=${s.count} trip${s.count === 1 ? "" : "s"} · delivered ${fmtDate(s.period!.from)}–${fmtDate(s.period!.to)}` : empty} />
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default function Dashboard() {
  const [f, setF] = useSharedFilters();
  const opts = useAsync(() => services.options(), []);
  const m = useAsync(() => services.metrics(f), [f.date_from, f.date_to, f.client_id, f.branch, f.billing_cycle]);
  const rec = useAsync(() => services.recent(), []);
  const d = m.data;

  return (
    <>
      <PageHeader title="Operations dashboard" subtitle="Where delivery documents stand between the consignee and the invoice."
        actions={d && <Badge tone={d.data_source === "demo" ? "amber" : "green"}>{d.data_source === "demo" ? "Seeded demo data" : "Live operational data"}</Badge>} />

      <Card className="mb-6 p-4"><FilterBar f={f} onChange={setF} opts={opts.data} /></Card>

      {m.error ? <Card><ErrorState message={m.error} onRetry={m.reload} /></Card> : !d ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{Array.from({ length: 12 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
      ) : (
        <>
          <section aria-label="Key metrics" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi label="Total trips" value={d.total_trips} hint={`${d.in_transit} in transit · ${d.delivered} delivered`} href="/trips" />
            <Kpi label="PODs pending" value={d.pods_pending} hint="Delivered, nothing uploaded" tone={d.pods_pending ? "amber" : "default"} href="/operations" />
            <Kpi label="PODs uploaded" value={d.pods_uploaded} hint="At least one attempt received" />
            <Kpi label="AI-verified PODs" value={d.ai_verified} hint={`${d.human_verified} verified after human review`} tone="green" />
            <Kpi label="Needs review" value={d.needs_review} hint={`${d.retake_requests} retake requests open`} tone={d.needs_review ? "amber" : "default"} href="/reviews" />
            <Kpi label="Billing-ready trips" value={d.billing_ready} hint={`${d.exported} exported · ${d.invoiced} invoiced (manual)`} tone="green" href="/billing" />
            <Kpi label="Trips without POD" value={d.trips_without_pod} hint="Includes retake / rejected, nothing usable" tone={d.trips_without_pod ? "red" : "default"} href="/operations" />
            <Kpi label="Avg delivery → upload" value={hours(d.avg_delivery_to_upload_hours)} hint={d.pods_within_24h_pct === null ? "No uploads yet" : `${d.pods_within_24h_pct}% within 24h of delivery day`} />
          </section>
          <p className="mt-2 text-xs text-muted">Avg upload → billing-ready: {hours(d.avg_upload_to_billing_ready_hours)}. Computed from timestamps in the database; no baseline comparison is implied.</p>
          <Turnaround m={d} />

          <section className="mt-6 grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader title="Missing POD aging" subtitle="Delivered trips with no usable POD, by days since delivery" />
              <div className="h-72 p-4">
                {d.aging.every((a) => a.count === 0) ? <EmptyState title="No missing PODs" text="Every delivered trip in this filter has a POD on file." /> : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={d.aging}><CartesianGrid strokeDasharray="3 3" stroke="#dde3df" vertical={false} /><XAxis dataKey="bucket" tick={{ fontSize: 12 }} /><YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                      <Tooltip formatter={(v, n) => (n === "freight" ? inrCompact(Number(v)) : v)} /><Bar dataKey="count" name="Trips" fill="#2D7768" radius={[4, 4, 0, 0]} /></BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </Card>
            <Card>
              <CardHeader title="Client-wise pending POD" subtitle="Trips awaiting a usable POD, plus those in review" />
              <div className="h-72 p-4">
                {d.clients.length === 0 ? <EmptyState title="No data" /> : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={d.clients} layout="vertical" margin={{ left: 20 }}><CartesianGrid strokeDasharray="3 3" stroke="#dde3df" horizontal={false} />
                      <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} /><YAxis type="category" dataKey="client" width={150} tick={{ fontSize: 12 }} /><Tooltip /><Legend />
                      <Bar dataKey="pending_pod" name="Awaiting POD" stackId="a" fill="#D69B37" /><Bar dataKey="needs_review" name="In review" stackId="a" fill="#183B36" /></BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </Card>
          </section>

          <section className="mt-6 grid gap-6 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader title="Branch-wise performance" subtitle="Branch comes from each trip record" />
              {d.branches.length === 0 ? <EmptyState title="No branch data" /> : (
                <Table><THead><tr><TH>Branch</TH><TH num>Trips</TH><TH num>Awaiting POD</TH><TH num>In review</TH><TH num>Billing-ready</TH><TH num>Freight awaiting POD</TH></tr></THead>
                  <TBody>{d.branches.map((b) => (
                    <TR key={b.branch}><TD className="font-medium">{b.branch}</TD><TD num>{b.trips}</TD><TD num>{b.pending_pod}</TD><TD num>{b.needs_review}</TD><TD num>{b.billing_ready}</TD><TD num>{inrCompact(b.freight_awaiting_pod)}</TD></TR>
                  ))}</TBody></Table>
              )}
            </Card>
            <Card>
              <CardHeader title="Recent activity" action={<Link href="/audit" className="text-xs text-teal hover:underline">All</Link>} />
              {rec.loading ? <div className="space-y-2 p-4">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-5" />)}</div> :
                rec.error ? <ErrorState message={rec.error} onRetry={rec.reload} /> :
                !rec.data?.items.length ? <EmptyState title="No activity yet" /> : (
                  <ul className="divide-y divide-line">{rec.data.items.map((a) => (
                    <li key={a.id} className="px-5 py-2.5 text-sm"><div className="font-medium">{humanize(a.action.replace(".", " · "))}</div><div className="text-xs text-muted">{a.user} · {dt(a.timestamp)}</div></li>
                  ))}</ul>
                )}
            </Card>
          </section>
        </>
      )}
    </>
  );
}
