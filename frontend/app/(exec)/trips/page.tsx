"use client";
import { useState } from "react";
import Link from "next/link";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, PageHeader } from "@/components/ui/card";
import { Badge, BillingBadge, PodBadge } from "@/components/ui/badge";
import { Input, Select } from "@/components/ui/input";
import { Pagination, Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { ImportDialog } from "@/components/import-dialog";
import { useAsync, useDebounced } from "@/hooks/use-async";
import { services } from "@/services";
import { d, inr } from "@/lib/format";

const POD_STATES = ["PENDING", "UPLOADED", "AI_PROCESSING", "NEEDS_REVIEW", "RETAKE_REQUESTED", "VERIFIED", "REJECTED"];
const BILLING_STATES = ["NOT_READY", "BILLING_READY", "EXPORTED", "INVOICED"];

export default function TripsPage() {
  const [q, setQ] = useState("");
  const [f, setF] = useState({ client_id: "", pod_status: "", billing_status: "", trip_status: "", branch: "" });
  const [page, setPage] = useState(1);
  const [importing, setImporting] = useState(false);
  const dq = useDebounced(q);
  const opts = useAsync(() => services.options(), []);
  const res = useAsync(() => services.trips({ q: dq, ...f, page, page_size: 15 }), [dq, f.client_id, f.pod_status, f.billing_status, f.trip_status, f.branch, page]);
  const setFilter = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLSelectElement>) => { setF({ ...f, [k]: e.target.value }); setPage(1); };

  return (
    <>
      <PageHeader title="Trips" subtitle="Every trip with its LR, e-way bill, POD and billing state."
        actions={<Button variant="outline" onClick={() => setImporting(true)}><Upload className="h-4 w-4" />Import trips (CSV)</Button>} />
      <Card>
        <div className="grid gap-3 border-b border-line p-4 sm:grid-cols-2 lg:grid-cols-6">
          <Input className="lg:col-span-2" placeholder="Search trip, LR, e-way bill, client, vehicle, destination…" aria-label="Search trips" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          <Select aria-label="Client" value={f.client_id} onChange={setFilter("client_id")}><option value="">All clients</option>{opts.data?.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
          <Select aria-label="Trip status" value={f.trip_status} onChange={setFilter("trip_status")}><option value="">Any trip status</option>{["IN_TRANSIT", "DELIVERED", "POD_PENDING", "POD_VERIFIED", "CANCELLED"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}</Select>
          <Select aria-label="POD status" value={f.pod_status} onChange={setFilter("pod_status")}><option value="">Any POD status</option>{POD_STATES.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}</Select>
          <Select aria-label="Billing status" value={f.billing_status} onChange={setFilter("billing_status")}><option value="">Any billing status</option>{BILLING_STATES.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}</Select>
        </div>
        {res.loading && !res.data ? <TableSkeleton cols={8} /> : res.error ? <ErrorState message={res.error} onRetry={res.reload} /> :
          !res.data?.items.length ? <EmptyState title="No trips match" text="Try clearing filters, or import a CSV of trips." /> : (
            <>
              <Table>
                <THead><tr><TH>Trip</TH><TH>LR / e-way bill</TH><TH>Client</TH><TH>Vehicle</TH><TH>Driver</TH><TH>Destination</TH><TH num>Freight</TH><TH>Delivery</TH><TH>POD</TH><TH>Billing</TH></tr></THead>
                <TBody>
                  {res.data.items.map((t) => (
                    <TR key={t.id}>
                      <TD><Link href={`/trips/${t.id}`} className="font-medium text-teal hover:underline">{t.trip_reference}</Link></TD>
                      <TD><div>{t.lr_number}</div><div className="text-xs text-muted">{t.eway_bill_number}</div></TD>
                      <TD>{t.client.name}</TD>
                      <TD><div className="whitespace-nowrap">{t.vehicle.registration}</div><div className="text-xs text-muted">{t.vehicle.type} · <Badge tone={t.vehicle.ownership === "hired" ? "amber" : "neutral"}>{t.vehicle.ownership}</Badge></div></TD>
                      <TD>{t.driver?.name ?? "—"}</TD>
                      <TD>{t.destination}</TD>
                      <TD num>{inr(t.freight_amount)}</TD>
                      <TD className="whitespace-nowrap">{d(t.delivery_date)}</TD>
                      <TD><PodBadge status={t.pod_status} /></TD>
                      <TD><BillingBadge status={t.billing_status} /></TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <Pagination page={page} pageSize={15} total={res.data.total} onPage={setPage} />
            </>
          )}
      </Card>
      <ImportDialog open={importing} onClose={() => setImporting(false)} onDone={res.reload} />
    </>
  );
}
