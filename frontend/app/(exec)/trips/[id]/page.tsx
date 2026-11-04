"use client";
import { use, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Copy, Link2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, PageHeader } from "@/components/ui/card";
import { Badge, BillingBadge, PodBadge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { useAsync } from "@/hooks/use-async";
import { services } from "@/services";
import { d, dt, humanize, inr } from "@/lib/format";

function Field({ k, v }: { k: string; v: React.ReactNode }) {
  return <div><dt className="text-xs uppercase tracking-wide text-muted">{k}</dt><dd className="mt-0.5 text-sm font-medium">{v ?? "—"}</dd></div>;
}

export default function TripDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const trip = useAsync(() => services.trip(id), [id]);
  const hist = useAsync(() => services.tripHistory(id), [id]);
  const [linkOpen, setLinkOpen] = useState(false);
  const [phone, setPhone] = useState("");
  const [link, setLink] = useState<Awaited<ReturnType<typeof services.driverLink>> | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  if (trip.error) return <Card><ErrorState message={trip.error} onRetry={trip.reload} /></Card>;
  const t = trip.data;
  if (!t) return <Skeleton className="h-96 w-full" />;

  async function gen() {
    setBusy(true);
    try { setLink(await services.driverLink(id, phone)); toast.success("Upload link created"); hist.reload(); }
    catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <>
      <Link href="/trips" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="h-4 w-4" />All trips</Link>
      <PageHeader title={t.trip_reference} subtitle={<span className="flex flex-wrap items-center gap-2">{t.client.name} · {t.origin} → {t.destination}<PodBadge status={t.pod_status} /><BillingBadge status={t.billing_status} /></span>}
        actions={<Button variant="outline" onClick={() => { setLink(null); setLinkOpen(true); }}><Link2 className="h-4 w-4" />Hired-driver upload link</Button>} />

      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Trip details" />
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4 p-5 md:grid-cols-3">
            <Field k="LR number" v={t.lr_number} /><Field k="E-way bill" v={t.eway_bill_number} /><Field k="Freight" v={inr(t.freight_amount)} />
            <Field k="Vehicle" v={`${t.vehicle.registration} (${t.vehicle.type})`} /><Field k="Ownership" v={<Badge tone={t.vehicle.ownership === "hired" ? "amber" : "neutral"}>{t.vehicle.ownership}</Badge>} />
            <Field k="Driver" v={t.driver?.name} /><Field k="Consignee" v={t.consignee_name} /><Field k="Commodity" v={t.commodity} />
            <Field k="Expected quantity" v={t.expected_quantity !== null ? `${t.expected_quantity} ${t.quantity_unit ?? ""}` : "Not on record"} />
            <Field k="Delivery date" v={d(t.delivery_date)} /><Field k="Trip status" v={humanize(t.trip_status)} /><Field k="Branch" v={t.branch} />
            <Field k="Billing cycle" v={t.billing_cycle} /><Field k="Invoice reference" v={t.invoice_reference ?? "Not recorded"} />
          </dl>
        </Card>

        <Card>
          <CardHeader title="Billing history" />
          {t.billing_history?.length ? (
            <ul className="divide-y divide-line">{t.billing_history.map((b) => (
              <li key={b.export_id} className="px-5 py-3 text-sm"><div className="font-medium">{b.export_reference} {b.is_reexport && <Badge tone="amber">re-export</Badge>}</div><div className="text-xs text-muted">{dt(b.created_at)}</div></li>
            ))}</ul>
          ) : <EmptyState title="Not exported yet" text="Exports appear here after the trip is included in a CSV." />}
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader title="POD attempts" subtitle="Every attempt is kept, including rejected and retaken documents" />
        {!t.pods?.length ? <EmptyState title="No POD uploaded" text="Waiting for the driver. You can send a hired driver an upload link." /> : (
          <Table>
            <THead><tr><TH>Attempt</TH><TH>Status</TH><TH>Received</TH><TH>Source</TH><TH>Verified by</TH><TH>Retakes used</TH><TH><span className="sr-only">Open</span></TH></tr></THead>
            <TBody>{t.pods.map((p) => (
              <TR key={p.id}><TD>#{p.attempt_number}</TD><TD><PodBadge status={p.verification_status} /></TD><TD>{dt(p.server_received_at)}</TD>
                <TD>{humanize(p.source)}</TD><TD>{p.verification_method ? humanize(p.verification_method) : "—"}</TD><TD>{p.retake_count}/2</TD>
                <TD><Link className="text-teal hover:underline" href={`/pods/${p.id}`}>Open document</Link></TD></TR>
            ))}</TBody>
          </Table>
        )}
      </Card>

      <Card className="mt-6">
        <CardHeader title="Verification & audit history" />
        {hist.loading ? <Skeleton className="m-5 h-24" /> : hist.error ? <ErrorState message={hist.error} onRetry={hist.reload} /> :
          !hist.data?.items.length ? <EmptyState title="No history" /> : (
            <ol className="divide-y divide-line">{hist.data.items.map((h) => (
              <li key={h.id} className="flex flex-wrap items-baseline justify-between gap-2 px-5 py-2.5 text-sm">
                <span className="font-medium">{humanize(h.action.replace(".", " · "))}</span><span className="text-xs text-muted">{h.user ?? "System / link"} · {dt(h.timestamp)}</span>
              </li>
            ))}</ol>
          )}
      </Card>

      <Dialog open={linkOpen} onClose={() => setLinkOpen(false)} title="Hired-driver upload link"
        footer={link ? <Button onClick={() => setLinkOpen(false)}>Done</Button> : <><Button variant="outline" onClick={() => setLinkOpen(false)}>Cancel</Button><Button loading={busy} onClick={gen}>Create link</Button></>}>
        {!link ? (
          <>
            <p className="text-sm text-muted">Creates a single-trip, expiring link. The driver opens it on a phone and uploads the POD without an account.</p>
            <div className="mt-4"><Label htmlFor="ph" hint="(optional, shown masked in the log)">Driver mobile number</Label><Input id="ph" inputMode="tel" placeholder="9XXXXXXXXX" value={phone} onChange={(e) => setPhone(e.target.value)} /></div>
          </>
        ) : (
          <div className="space-y-3 text-sm">
            <p className="rounded-lg bg-amber-50 p-3 text-[#8a5f12]">{link.sms.note} Sent to {link.sms.to} via the {link.sms.provider} provider: <strong>{link.sms.status}</strong>.</p>
            <Label htmlFor="lk">One-time link (shown once)</Label>
            <div className="flex gap-2"><Input id="lk" readOnly value={link.url} /><Button variant="outline" aria-label="Copy link" onClick={() => { navigator.clipboard?.writeText(link.url); toast.success("Copied"); }}><Copy className="h-4 w-4" /></Button></div>
            <p className="text-xs text-muted">Expires {dt(link.expires_at)}. Only a hash of the token is stored.</p>
          </div>
        )}
      </Dialog>
    </>
  );
}
