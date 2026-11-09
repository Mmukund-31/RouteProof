"use client";
import { useState } from "react";
import Link from "next/link";
import { AlertOctagon, ArrowRight, ClipboardCheck, FileSpreadsheet, PackageSearch, RefreshCw } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardHeader, PageHeader, Segmented } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { PodBadge, PriorityBadge, ReasonBadge } from "@/components/ui/badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { Kpi } from "@/components/kpi";
import { ActivityTimeline } from "@/components/activity";
import { useAsync } from "@/hooks/use-async";
import { services } from "@/services";
import { ago, d as fmtDate, inr, inrCompact } from "@/lib/format";
import { cn } from "@/lib/utils";
import { FilterBar, useSharedFilters } from "@/hooks/use-shared-filters";
import type { Metrics, TurnaroundKey } from "@/types";

const C = { forest: "#173F38", teal: "#2D806B", amber: "#D69A36", grid: "#E9EEEA", tick: "#64736D" };
const axis = { fontSize: 12, fill: C.tick };

function ViewAll({ href, children = "View all" }: { href: string; children?: React.ReactNode }) {
  return <Link href={href} className="inline-flex items-center gap-1 text-[13px] font-medium text-teal-700 hover:underline">{children}<ArrowRight className="h-3.5 w-3.5" aria-hidden /></Link>;
}

/** Where every delivered trip stands on its way to cash. Each step counts trips that have reached at least that stage. */
function Pipeline({ m }: { m: Metrics }) {
  const verified = m.ai_verified + m.human_verified;
  const steps = [
    { label: "Delivered", n: m.delivered, note: `${m.in_transit} still in transit` },
    { label: "POD received", n: m.pods_uploaded, note: `${m.pods_pending} awaiting upload` },
    { label: "POD verified", n: verified, note: <><span>{m.ai_verified}</span> by AI checks · {m.human_verified} by review</> },
    { label: "Billing-ready", n: m.billing_ready + m.exported + m.invoiced, note: `${m.billing_ready} waiting for export` },
    { label: "Exported", n: m.exported + m.invoiced, note: "Tally-compatible CSV" },
    { label: "Invoiced", n: m.invoiced, note: "Recorded by billing" },
  ];
  const base = Math.max(m.delivered, 1);
  return (
    <Card className="mb-5" data-testid="pipeline">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line-soft px-5 py-3">
        <h2 className="text-sm font-semibold text-ink">Delivery-to-invoice pipeline</h2>
        <div className="flex items-baseline gap-2 text-[13px] text-muted"><span>Total trips</span><strong className="num text-base font-semibold text-ink">{m.total_trips}</strong></div>
      </div>
      <ol className="grid grid-cols-2 gap-px overflow-hidden rounded-b-xl bg-line-soft sm:grid-cols-3 xl:grid-cols-6">
        {steps.map((s, i) => {
          const pct = Math.round((100 * s.n) / base);
          return (
            <li key={s.label} className="bg-surface px-5 py-3.5">
              <div className="text-xs font-medium text-muted">{s.label}</div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="num !text-left text-[22px] font-semibold leading-none tracking-tight text-ink">{s.n}</span>
                {i > 0 && <span className="text-xs text-muted">{pct}%</span>}
              </div>
              <div className="mt-2 h-1 overflow-hidden rounded-full bg-[#edf1ee]" aria-hidden>
                <div className={cn("h-full rounded-full", i < 3 ? "bg-forest" : "bg-teal")} style={{ width: `${Math.min(i === 0 ? 100 : pct, 100)}%` }} />
              </div>
              <div className="mt-1.5 text-xs text-muted">{s.note}</div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

const TURNAROUND: { key: TurnaroundKey; label: string; empty: string }[] = [
  { key: "delivery_to_pod_received", label: "POD received", empty: "No PODs received yet" },
  { key: "delivery_to_pod_verified", label: "POD verified", empty: "No verified PODs yet" },
  { key: "delivery_to_billing_export", label: "Billing export", empty: "Nothing exported yet" },
  { key: "delivery_to_invoice_recorded", label: "Invoice recorded", empty: "No invoice dates recorded" },
];

/** Days from delivery to each milestone, with the sample behind each figure. */
function Turnaround({ m }: { m: Metrics }) {
  return (
    <Card aria-label="Turnaround">
      <CardHeader title="Days from delivery to…" subtitle="Average, counted from the delivery date" />
      <ul className="divide-y divide-line-soft">
        {m.turnaround && TURNAROUND.map(({ key, label, empty }) => {
          const s = m.turnaround![key];
          return (
            <li key={key} className="px-5 py-3" data-testid={`tat-${key}`} title={m.metric_definitions?.[key]}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-[13px] font-medium text-ink">{label}</span>
                <span className="num text-lg font-semibold tracking-tight text-ink">{s.avg_days === null ? "—" : `${s.avg_days} d`}</span>
              </div>
              <div className="mt-0.5 text-xs text-muted">
                {s.count ? `median ${s.median_days} d · n=${s.count} · delivered ${fmtDate(s.period!.from)}–${fmtDate(s.period!.to)}` : empty}
              </div>
            </li>
          );
        })}
        <li className="flex items-baseline justify-between gap-3 px-5 py-3" title="First POD in by the end of the day after delivery">
          <span className="text-[13px] font-medium text-ink">PODs received within a day</span>
          <span className="num text-lg font-semibold tracking-tight text-ink">{m.pods_within_24h_pct === null ? "—" : `${m.pods_within_24h_pct}%`}</span>
        </li>
      </ul>
      <p className="border-t border-line-soft px-5 py-2.5 text-xs text-muted">An export is not an invoice: “Invoice recorded” only counts invoice dates entered by billing.</p>
    </Card>
  );
}

/** Uploads that have not reached a decision yet, and whether any are stuck. */
function Processing() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const res = useAsync(() => Promise.all([
    services.reviews({ status: "UPLOADED", page_size: 50 }),
    services.reviews({ status: "AI_PROCESSING", page_size: 50 }),
    services.reviews({ status: "RETAKE_REQUESTED", page_size: 1 }),
  ]), []);
  const [up, proc, retake] = res.data ?? [];
  const stale = [...(up?.items ?? []), ...(proc?.items ?? [])].filter((p) => p.processing?.stale).length;

  async function recover() {
    setBusy(true);
    try {
      const r = await services.recoverStale();
      toast.success(r.recovered.length ? `Recovered ${r.recovered.length} stalled upload(s)` : "Nothing was stalled");
      res.reload();
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  }
  const row = (label: string, n: number | undefined, hint: string, tone?: "amber" | "red") => (
    <li className="flex items-center justify-between gap-3 px-5 py-2.5">
      <div><div className="text-[13px] font-medium text-ink">{label}</div><div className="text-xs text-muted">{hint}</div></div>
      <span className={cn("num text-lg font-semibold", tone === "red" ? "text-danger-700" : tone === "amber" ? "text-amber-700" : "text-ink")}>{n ?? "—"}</span>
    </li>
  );
  return (
    <Card data-testid="processing">
      <CardHeader title="Uploads in progress" subtitle="Received PODs that have not reached a decision yet"
        action={stale > 0 && <Button size="xs" variant="outline" loading={busy} onClick={recover}><RefreshCw className="h-3.5 w-3.5" />Recover stalled</Button>} />
      {res.error ? <ErrorState message={res.error} onRetry={res.reload} /> : !res.data ? <div className="space-y-2 p-5"><Skeleton className="h-8" /><Skeleton className="h-8" /></div> : (
        <ul className="divide-y divide-line-soft">
          {row("Waiting for AI", up?.total, "Uploaded, extraction not started")}
          {row("AI reading", proc?.total, "Extraction running")}
          {row("Stalled", stale, stale ? "Processing took too long — recover to re-run" : "No stuck uploads", stale ? "red" : undefined)}
          {row("Retakes with drivers", retake?.total, "Waiting for a new photo", retake?.total ? "amber" : undefined)}
        </ul>
      )}
    </Card>
  );
}

function Breakdown({ m }: { m: Metrics }) {
  const [by, setBy] = useState<"client" | "branch">("client");
  const rows = by === "client" ? m.clients.map((c) => ({ name: c.client, ...c })) : m.branches.map((b) => ({ name: b.branch, ...b }));
  return (
    <Card className="xl:col-span-2">
      <CardHeader title={by === "client" ? "By client" : "By branch"} subtitle="Where PODs and billing are held up"
        action={<Segmented label="Group by" value={by} onChange={setBy} items={[["client", "Client"], ["branch", "Branch"]] as const} />} />
      {rows.length === 0 ? <EmptyState compact title="No data in this filter" /> : (
        <Table><THead><tr><TH>{by === "client" ? "Client" : "Branch"}</TH><TH num>Trips</TH><TH num>Awaiting POD</TH><TH num>In review</TH><TH num>Billing-ready</TH><TH num>Freight awaiting POD</TH></tr></THead>
          <TBody>{rows.map((r) => (
            <TR key={r.name}><TD className="max-w-64 truncate font-medium" title={r.name}>{r.name}</TD><TD num>{r.trips}</TD>
              <TD num>{r.pending_pod ? <span className="font-medium text-amber-700">{r.pending_pod}</span> : 0}</TD>
              <TD num>{r.needs_review}</TD><TD num>{r.billing_ready}</TD><TD num className="font-medium">{inrCompact(r.freight_awaiting_pod)}</TD></TR>
          ))}</TBody></Table>
      )}
    </Card>
  );
}

export default function Dashboard() {
  const [f, setF] = useSharedFilters();
  const deps = [f.date_from, f.date_to, f.client_id, f.branch, f.billing_cycle];
  const opts = useAsync(() => services.options(), []);
  const m = useAsync(() => services.metrics(f), deps);
  const miss = useAsync(() => services.missing(f), deps);
  const rec = useAsync(() => services.recent(), []);
  // The review endpoints filter by client only; the cards below say so when other filters are active.
  const queue = useAsync(() => services.reviews({ status: "NEEDS_REVIEW", client_id: f.client_id || undefined, page_size: 5 }), [f.client_id]);
  const exc = useAsync(() => services.reviews({ status: "NEEDS_REVIEW", category: "business", client_id: f.client_id || undefined, page_size: 1 }), [f.client_id]);
  const d = m.data;
  const partialScope = !!(f.date_from || f.date_to || f.branch || f.billing_cycle);
  const missItems = miss.data?.items ?? [];

  return (
    <>
      <PageHeader title="Operations dashboard"
        subtitle={<>What needs attention between delivery and invoice.{d?.data_source === "demo" && <> Figures are computed live from <span className="font-medium text-amber-700">seeded demo data</span>.</>}</>} />

      <Card className="mb-5 px-4 py-3"><FilterBar f={f} onChange={setF} opts={opts.data} /></Card>

      {m.error ? <Card><ErrorState message={m.error} onRetry={m.reload} /></Card> : !d ? (
        <div className="space-y-5" role="status" aria-label="Loading dashboard"><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-32 rounded-xl" />)}</div><Skeleton className="h-32 w-full rounded-xl" /></div>
      ) : (
        <>
          <section aria-label="Needs attention" className="mb-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi testId="kpi-review" label="Awaiting review" icon={ClipboardCheck} tone={d.needs_review ? "amber" : "default"} href="/reviews" action="Open review queue"
              value={d.needs_review} hint={`${d.retake_requests} retake request(s) open with drivers`} />
            <Kpi testId="kpi-exceptions" label="Open exceptions" icon={AlertOctagon} tone={exc.data?.total ? "red" : "default"} href="/exceptions" action="Resolve exceptions"
              value={exc.data ? exc.data.total : "—"} hint={partialScope ? "Shortage, damage or mismatch · client filter only" : "Shortage, damage or mismatch awaiting a decision"} />
            <Kpi testId="kpi-missing" label="Freight held up" icon={PackageSearch} tone={missItems.length ? "red" : "default"} href="/operations" action="Chase missing PODs"
              value={miss.data ? inrCompact(miss.data.freight_blocked) : "—"}
              hint={miss.data ? `${missItems.length} trips without a usable POD · ${miss.data.overdue_count} overdue` : "Loading…"} />
            <Kpi testId="kpi-billing" label="Ready to export" icon={FileSpreadsheet} tone={d.billing_ready ? "green" : "default"} href="/billing" action="Go to billing"
              value={d.billing_ready} hint="Verified and not yet in a billing CSV" />
          </section>

          <Pipeline m={d} />

          <section className="mb-5 grid items-start gap-5 xl:grid-cols-3">
            <div className="space-y-5 xl:col-span-2">
              <Card data-testid="dashboard-review">
                <CardHeader title="Next in the review queue" subtitle={queue.data ? `${queue.data.total} POD(s) waiting · highest priority first${partialScope ? " · client filter only" : ""}` : "Highest priority first"}
                  action={<ViewAll href="/reviews">Open queue</ViewAll>} />
                {queue.loading && !queue.data ? <div className="space-y-2 p-5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-9" />)}</div> :
                  queue.error ? <ErrorState message={queue.error} onRetry={queue.reload} /> :
                  !queue.data?.items.length ? <EmptyState compact title="Review queue is clear" text="New uploads that need a person will appear here." /> : (
                    <Table><THead><tr><TH>Priority</TH><TH>Trip</TH><TH>Why it needs you</TH><TH>Waiting</TH><TH><span className="sr-only">Action</span></TH></tr></THead>
                      <TBody>{queue.data.items.map((p) => (
                        <TR key={p.id}>
                          <TD className="whitespace-nowrap"><PriorityBadge p={p.review_priority} /></TD>
                          <TD className="whitespace-nowrap"><div className="font-medium">{p.trip.trip_reference}</div><div className="text-xs text-muted">{p.trip.lr_number} · {p.trip.client.name}</div></TD>
                          <TD><div className="flex max-w-xs flex-wrap gap-1">{p.review_reasons.slice(0, 3).map((r) => <ReasonBadge key={r} code={r} />)}{p.review_reasons.length > 3 && <span className="text-xs text-muted">+{p.review_reasons.length - 3}</span>}</div></TD>
                          <TD className="whitespace-nowrap text-muted">{ago(p.server_received_at)}</TD>
                          <TD className="text-right"><Link href={`/pods/${p.id}`} className="text-[13px] font-medium text-teal-700 hover:underline">Review</Link></TD>
                        </TR>
                      ))}</TBody></Table>
                  )}
              </Card>

              <Card data-testid="dashboard-missing">
                <CardHeader title="Freight held up by missing PODs"
                  subtitle={miss.data ? `${missItems.length} trip(s) · ${inrCompact(miss.data.freight_blocked)} · ${miss.data.overdue_count} overdue (> ${miss.data.overdue_after_days} days)` : "Delivered trips with no usable proof of delivery"}
                  action={<ViewAll href="/operations" />} />
                {miss.loading && !miss.data ? <div className="space-y-2 p-5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-9" />)}</div> :
                  miss.error ? <ErrorState message={miss.error} onRetry={miss.reload} /> :
                  !missItems.length ? <EmptyState compact title="Nothing blocked" text="Every delivered trip in this filter has a usable POD." /> : (
                    <Table><THead><tr><TH>Trip</TH><TH>Client · branch</TH><TH num>Days waiting</TH><TH num>Freight</TH><TH>POD</TH></tr></THead>
                      <TBody>{missItems.slice(0, 6).map((i) => (
                        <TR key={i.trip_id}>
                          <TD className="whitespace-nowrap"><Link href={`/trips/${i.trip_id}`} className="font-medium text-teal-700 hover:underline">{i.trip_reference}</Link><div className="text-xs text-muted">{i.lr_number}</div></TD>
                          <TD className="max-w-60"><div className="truncate" title={i.client}>{i.client}</div><div className="truncate text-xs text-muted">{i.branch ?? "Unassigned"}</div></TD>
                          <TD num>{i.overdue
                            ? <span className="inline-flex min-w-8 justify-center rounded bg-danger-50 px-1.5 font-semibold text-danger-700">{i.days_since_delivery}</span>
                            : <span className="inline-flex min-w-8 justify-center px-1.5">{i.days_since_delivery}</span>}</TD>
                          <TD num className="whitespace-nowrap font-medium">{inr(i.freight_amount)}</TD><TD className="whitespace-nowrap"><PodBadge status={i.pod_state} /></TD>
                        </TR>
                      ))}</TBody></Table>
                  )}
              </Card>
            </div>

            <div className="space-y-5">
              <Processing />
              <Card>
                <CardHeader title="Recent activity" action={<ViewAll href="/audit" />} />
                {rec.loading ? <div className="space-y-3 p-5">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-8" />)}</div> :
                  rec.error ? <ErrorState message={rec.error} onRetry={rec.reload} /> :
                  !rec.data?.items.length ? <EmptyState compact title="No activity yet" /> :
                  <ActivityTimeline className="px-5 py-4" items={rec.data.items.slice(0, 7)} />}
              </Card>
            </div>
          </section>

          <section className="grid items-start gap-5 xl:grid-cols-3">
            <Breakdown m={d} />
            <Turnaround m={d} />
            <Card className="xl:col-span-3">
              <CardHeader title="Missing POD aging" subtitle="Delivered trips with no usable POD, by days since delivery" action={<ViewAll href="/operations" />} />
              <div className="h-56 px-3 pb-3 pt-4">
                {d.aging.every((a) => a.count === 0) ? <EmptyState compact title="No missing PODs" text="Every delivered trip in this filter has a POD on file." /> : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={d.aging} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
                      <CartesianGrid stroke={C.grid} vertical={false} />
                      <XAxis dataKey="bucket" tick={axis} axisLine={false} tickLine={false} />
                      <YAxis allowDecimals={false} tick={axis} axisLine={false} tickLine={false} />
                      <Tooltip cursor={{ fill: "#F4F6F3" }} contentStyle={{ borderRadius: 8, borderColor: C.grid, fontSize: 12 }}
                        formatter={(v, _n, p) => [`${v} trips · ${inrCompact((p.payload as { freight: number }).freight)}`, "Missing"]} />
                      <Bar dataKey="count" name="Trips" fill={C.forest} radius={[3, 3, 0, 0]} maxBarSize={48} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </Card>
          </section>
        </>
      )}
    </>
  );
}
