"use client";
import { Fragment, useState } from "react";
import Link from "next/link";
import { Download, FileDown, Receipt } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, PageHeader } from "@/components/ui/card";
import { Badge, BillingBadge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { Pagination, Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { useAsync, useDebounced } from "@/hooks/use-async";
import { services } from "@/services";
import { downloadFile } from "@/lib/api";
import { d, dt, inr } from "@/lib/format";
import type { BillingRow } from "@/types";

export default function Billing() {
  const [tab, setTab] = useState<"queue" | "history">("queue");
  const toast = useToast();
  return (
    <>
      <PageHeader title="Billing queue" subtitle="Verified trips only. Exporting a CSV does not issue an invoice — invoicing happens in your accounting system." />
      <div className="mb-4 flex w-fit gap-1 rounded-lg bg-black/5 p-1" role="tablist">
        {([["queue", "Ready to export"], ["history", "Export history"]] as const).map(([v, l]) => (
          <button key={v} role="tab" aria-selected={tab === v} onClick={() => setTab(v)} className={`rounded-md px-3 py-1.5 text-sm font-medium ${tab === v ? "bg-surface shadow-sm" : "text-muted"}`}>{l}</button>
        ))}
      </div>
      {tab === "queue" ? <Queue toast={toast} onExported={() => setTab("history")} /> : <History toast={toast} />}
    </>
  );
}

type Toast = ReturnType<typeof useToast>;

function Queue({ toast, onExported }: { toast: Toast; onExported: () => void }) {
  const [q, setQ] = useState("");
  const [f, setF] = useState({ client_id: "", billing_cycle: "", export_status: "", date_from: "", date_to: "" });
  const [page, setPage] = useState(1);
  const [sel, setSel] = useState<Record<string, BillingRow>>({});
  const [dlg, setDlg] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [invFor, setInvFor] = useState<BillingRow | null>(null);
  const [invRef, setInvRef] = useState("");
  const dq = useDebounced(q);
  const opts = useAsync(() => services.options(), []);
  const res = useAsync(() => services.billingQueue({ q: dq, ...f, page, page_size: 15 }), [dq, f.client_id, f.billing_cycle, f.export_status, f.date_from, f.date_to, page]);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => { setF({ ...f, [k]: e.target.value }); setPage(1); };

  const rows = res.data?.items ?? [];
  const chosen = Object.values(sel);
  const reexport = chosen.some((r) => r.export_status === "EXPORTED");
  const total = chosen.reduce((s, r) => s + Number(r.freight_amount), 0);
  const toggle = (r: BillingRow) => setSel((s) => { const n = { ...s }; if (n[r.id]) delete n[r.id]; else n[r.id] = r; return n; });
  const allOnPage = rows.length > 0 && rows.every((r) => sel[r.id]);

  async function doExport() {
    if (reexport && !reason.trim()) { toast.error("Enter a reason to re-export"); return; }
    setBusy(true);
    try {
      const exp = await services.createExport({ trip_ids: chosen.map((r) => r.id), billing_period: f.billing_cycle || undefined, filters: { ...f, q: dq }, reexport, reexport_reason: reexport ? reason : undefined });
      await downloadFile(`/billing/exports/${exp.id}/download`, `${exp.export_reference}.csv`);
      toast.success(`${exp.export_reference} exported (${exp.trip_count} trips)`);
      setSel({}); setDlg(false); setReason(""); res.reload(); onExported();
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  }
  async function markInvoiced() {
    if (!invFor || !invRef.trim()) return;
    setBusy(true);
    try { await services.markInvoiced(invFor.id, invRef.trim()); toast.success("Recorded. RouteProof did not issue this invoice."); setInvFor(null); setInvRef(""); res.reload(); }
    catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <Card>
      <div className="grid gap-3 border-b border-line p-4 sm:grid-cols-2 lg:grid-cols-6">
        <Input className="lg:col-span-2" placeholder="Search trip, LR, client, destination…" aria-label="Search" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <Select aria-label="Client" value={f.client_id} onChange={set("client_id")}><option value="">All clients</option>{opts.data?.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
        <Select aria-label="Billing cycle" value={f.billing_cycle} onChange={set("billing_cycle")}><option value="">All billing cycles</option>{opts.data?.billing_cycles.map((c) => <option key={c}>{c}</option>)}</Select>
        <Select aria-label="Export status" value={f.export_status} onChange={set("export_status")}><option value="">Exported or not</option><option value="NOT_EXPORTED">Not exported</option><option value="EXPORTED">Already exported</option></Select>
        <div className="flex gap-2"><Input type="date" aria-label="Delivery from" value={f.date_from} onChange={set("date_from")} /><Input type="date" aria-label="Delivery to" value={f.date_to} onChange={set("date_to")} /></div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-canvas/60 px-4 py-2.5 text-sm">
        <span>{chosen.length ? <><strong>{chosen.length}</strong> selected · <span className="num">{inr(total)}</span> freight</> : <span className="text-muted">Select trips to export. {res.data ? `Queue total ${inr(res.data.total_freight)}` : ""}</span>}</span>
        <div className="flex gap-2">
          {chosen.length > 0 && <Button variant="ghost" size="sm" onClick={() => setSel({})}>Clear</Button>}
          <Button size="sm" disabled={!chosen.length} onClick={() => setDlg(true)}><FileDown className="h-4 w-4" />{reexport ? "Re-export CSV" : "Export CSV"}</Button>
        </div>
      </div>
      {res.loading && !res.data ? <TableSkeleton cols={8} /> : res.error ? <ErrorState message={res.error} onRetry={res.reload} /> :
        !rows.length ? <EmptyState title="Nothing is billing-ready" text="Trips appear here once their POD is verified and nothing blocks billing." /> : (
          <>
            <Table>
              <THead><tr><TH><input type="checkbox" aria-label="Select all on page" checked={allOnPage} onChange={() => setSel((s) => { const n = { ...s }; rows.forEach((r) => { if (allOnPage) delete n[r.id]; else n[r.id] = r; }); return n; })} /></TH>
                <TH>Trip / LR</TH><TH>Client</TH><TH>Destination</TH><TH num>Freight</TH><TH>Delivered</TH><TH>POD verified</TH><TH>Cycle</TH><TH>Export</TH><TH><span className="sr-only">Actions</span></TH></tr></THead>
              <TBody>{rows.map((r) => (
                <TR key={r.id} className={sel[r.id] ? "bg-teal-50/50" : ""}>
                  <TD><input type="checkbox" aria-label={`Select ${r.trip_reference}`} checked={!!sel[r.id]} onChange={() => toggle(r)} /></TD>
                  <TD><Link href={`/trips/${r.id}`} className="font-medium text-teal hover:underline">{r.trip_reference}</Link><div className="text-xs text-muted">{r.lr_number} · {r.eway_bill_number}</div></TD>
                  <TD>{r.client.name}</TD><TD>{r.destination}</TD><TD num>{inr(r.freight_amount)}</TD>
                  <TD className="whitespace-nowrap">{d(r.delivery_date)}</TD>
                  <TD className="whitespace-nowrap">{d(r.pod_verified_at)}<div className="text-xs text-muted">{r.verification_method === "ai" ? "Automated checks" : "Human review"}</div>{(r.approved_exceptions?.length ?? 0) > 0 && <div className="text-xs font-medium text-[#8a5f12]">Accepted exception: {r.approved_exceptions!.join(", ").toLowerCase().replace(/_/g, " ")}</div>}</TD>
                  <TD>{r.billing_cycle}</TD>
                  <TD><BillingBadge status={r.billing_status} /></TD>
                  <TD>{r.export_status === "EXPORTED" && <button className="text-xs text-teal hover:underline" onClick={() => setInvFor(r)}>Record invoice</button>}</TD>
                </TR>
              ))}</TBody>
            </Table>
            <Pagination page={page} pageSize={15} total={res.data!.total} onPage={setPage} />
          </>
        )}

      <Dialog open={dlg} onClose={() => setDlg(false)} title={reexport ? "Re-export trips" : "Export Tally-compatible CSV"}
        footer={<><Button variant="outline" onClick={() => setDlg(false)}>Cancel</Button><Button loading={busy} onClick={doExport}><Download className="h-4 w-4" />Export & download</Button></>}>
        <p className="text-sm text-muted">{chosen.length} trip(s), {inr(total)} freight. The CSV is a flat file for manual/bulk import into your accounting tool. It is <strong>not</strong> a live Tally integration and does not issue invoices.</p>
        {reexport && (
          <div className="mt-4">
            <p className="mb-2 rounded-lg bg-amber-50 p-3 text-sm text-[#8a5f12]">Some selected trips were already exported. Re-exporting is recorded in the audit history.</p>
            <Label htmlFor="rx">Reason for re-export</Label><Textarea id="rx" value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
        )}
      </Dialog>
      <Dialog open={!!invFor} onClose={() => setInvFor(null)} title="Record external invoice"
        footer={<><Button variant="outline" onClick={() => setInvFor(null)}>Cancel</Button><Button loading={busy} disabled={!invRef.trim()} onClick={markInvoiced}><Receipt className="h-4 w-4" />Record</Button></>}>
        <p className="text-sm text-muted">Invoices are issued outside RouteProof. Enter the reference from your accounting system to mark {invFor?.trip_reference} as invoiced.</p>
        <div className="mt-4"><Label htmlFor="iv">Invoice reference</Label><Input id="iv" value={invRef} onChange={(e) => setInvRef(e.target.value)} /></div>
      </Dialog>
    </Card>
  );
}

function History({ toast }: { toast: Toast }) {
  const [page, setPage] = useState(1);
  const res = useAsync(() => services.exports({ page, page_size: 10 }), [page]);
  const [open, setOpen] = useState<string | null>(null);
  return (
    <Card>
      {res.loading && !res.data ? <TableSkeleton cols={6} /> : res.error ? <ErrorState message={res.error} onRetry={res.reload} /> :
        !res.data?.items.length ? <EmptyState title="No exports yet" text="Generate your first CSV from the queue." /> : (
          <>
            <Table>
              <THead><tr><TH>Reference</TH><TH>Client</TH><TH>Period</TH><TH num>Trips</TH><TH num>Freight</TH><TH>Created</TH><TH><span className="sr-only">Download</span></TH></tr></THead>
              <TBody>{res.data.items.map((e) => (
                <Fragment key={e.id}>
                  <TR>
                    <TD><button className="font-medium text-teal hover:underline" onClick={() => setOpen(open === e.id ? null : e.id)}>{e.export_reference}</button>{e.is_reexport && <> <Badge tone="amber">re-export</Badge></>}</TD>
                    <TD>{e.client}</TD><TD>{e.billing_period ?? "—"}</TD><TD num>{e.trip_count}</TD><TD num>{inr(e.total_freight)}</TD><TD className="whitespace-nowrap">{dt(e.created_at)}</TD>
                    <TD><Button size="sm" variant="outline" onClick={() => downloadFile(`/billing/exports/${e.id}/download`, `${e.export_reference}.csv`).catch((x) => toast.error(x.message))}><Download className="h-4 w-4" />CSV</Button></TD>
                  </TR>
                  {open === e.id && <tr><td colSpan={7} className="bg-canvas/60 px-4 py-3 text-xs text-muted">Trips: {e.trip_references.join(", ")}{e.reexport_reason && <div className="mt-1">Re-export reason: {e.reexport_reason}</div>}</td></tr>}
                </Fragment>
              ))}</TBody>
            </Table>
            <Pagination page={page} pageSize={10} total={res.data.total} onPage={setPage} />
          </>
        )}
    </Card>
  );
}
