"use client";
import { useState } from "react";
import { Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, PageHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Label, Select } from "@/components/ui/input";
import { Pagination, Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { ClientLinkDialog, type ShareScope } from "@/components/client-link-dialog";
import { useAsync } from "@/hooks/use-async";
import { services } from "@/services";
import { dt } from "@/lib/format";

export default function ClientLinks() {
  const toast = useToast();
  const opts = useAsync(() => services.options(), []);
  const [client, setClient] = useState("");
  const [cycle, setCycle] = useState("");
  const [page, setPage] = useState(1);
  const [share, setShare] = useState<ShareScope | null>(null);
  const res = useAsync(() => services.clientLinks({ client_id: client, page, page_size: 15 }), [client, page]);

  async function revoke(id: string) {
    try { await services.revokeClientLink(id); toast.success("Link revoked — it stops working immediately"); res.reload(); }
    catch (e) { toast.error((e as Error).message); }
  }
  function shareCycle() {
    const c = opts.data?.clients.find((x) => x.id === client);
    if (!c || !cycle) { toast.error("Choose a client and a billing cycle"); return; }
    setShare({ clientId: c.id, clientName: c.name, billingCycle: cycle, label: `${c.name} · ${cycle}` });
  }

  return (
    <>
      <PageHeader title="Client POD links" subtitle="Read-only, expiring links that let a client see verified proof of delivery for its own trips. Share selected trips from the billing queue, or a whole billing cycle here." />
      <Card className="mb-6">
        <CardHeader title="Share a billing cycle" />
        <div className="grid gap-3 p-4 sm:grid-cols-3">
          <div><Label htmlFor="c">Client</Label><Select id="c" value={client} onChange={(e) => { setClient(e.target.value); setPage(1); }}>
            <option value="">All clients</option>{opts.data?.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></div>
          <div><Label htmlFor="cy">Billing cycle</Label><Select id="cy" value={cycle} onChange={(e) => setCycle(e.target.value)}>
            <option value="">Choose…</option>{opts.data?.billing_cycles.map((c) => <option key={c}>{c}</option>)}</Select></div>
          <div className="flex items-end"><Button onClick={shareCycle} disabled={!client || !cycle}><Eye className="h-4 w-4" />Create view link</Button></div>
        </div>
      </Card>
      <Card>
        {res.loading && !res.data ? <TableSkeleton cols={7} /> : res.error ? <ErrorState message={res.error} onRetry={res.reload} /> :
          !res.data?.items.length ? <EmptyState title="No client links yet" text="Links you create appear here with their access history." /> : (
            <>
              <Table>
                <THead><tr><TH>Client</TH><TH>Scope</TH><TH>Status</TH><TH>Expires</TH><TH num>Views</TH><TH>Last opened</TH><TH><span className="sr-only">Revoke</span></TH></tr></THead>
                <TBody>{res.data.items.map((l) => (
                  <TR key={l.id}>
                    <TD className="font-medium">{l.client.name}{l.label && <div className="text-xs text-muted">{l.label}</div>}</TD>
                    <TD>{l.scope === "billing_cycle" ? `Cycle ${l.billing_cycle}` : `${l.trip_count} trip(s)`}</TD>
                    <TD><Badge tone={l.state === "active" ? "green" : "neutral"}>{l.state}</Badge></TD>
                    <TD className="whitespace-nowrap">{dt(l.expires_at)}</TD>
                    <TD num>{l.access_count}</TD>
                    <TD className="whitespace-nowrap">{l.last_accessed_at ? dt(l.last_accessed_at) : "Never"}</TD>
                    <TD>{l.state === "active" && <Button size="sm" variant="outline" onClick={() => void revoke(l.id)}>Revoke</Button>}</TD>
                  </TR>
                ))}</TBody>
              </Table>
              <Pagination page={page} pageSize={15} total={res.data.total} onPage={setPage} />
            </>
          )}
      </Card>
      <ClientLinkDialog scope={share} onClose={() => setShare(null)} onCreated={res.reload} />
    </>
  );
}
