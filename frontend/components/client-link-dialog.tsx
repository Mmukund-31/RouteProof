"use client";
import { useEffect, useState } from "react";
import { Copy, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input, Label, Select } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { services } from "@/services";
import { dt } from "@/lib/format";

export interface ShareScope { clientId: string; clientName: string; tripIds?: string[]; billingCycle?: string; label?: string }

/** Creates a read-only, expiring client POD-view link. The URL is shown once; only a hash is stored. */
export function ClientLinkDialog({ scope, onClose, onCreated }: { scope: ShareScope | null; onClose: () => void; onCreated?: () => void }) {
  const toast = useToast();
  const [days, setDays] = useState("7");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [made, setMade] = useState<{ url: string; expires_at: string } | null>(null);
  useEffect(() => { setMade(null); setLabel(scope?.label ?? ""); setDays("7"); }, [scope]);

  async function create() {
    if (!scope) return;
    setBusy(true);
    try {
      const r = await services.createClientLink({ client_id: scope.clientId, trip_ids: scope.tripIds, billing_cycle: scope.billingCycle,
        expires_in_days: Number(days), label: label || undefined });
      setMade({ url: r.url, expires_at: r.expires_at });
      onCreated?.();
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  }

  const what = scope?.tripIds ? `${scope.tripIds.length} trip(s)` : `billing cycle ${scope?.billingCycle}`;
  return (
    <Dialog open={!!scope} onClose={onClose} title="Share PODs with client"
      footer={made ? <Button onClick={onClose}>Done</Button> : <><Button variant="outline" onClick={onClose}>Cancel</Button><Button loading={busy} onClick={create}><Eye className="h-4 w-4" />Create view link</Button></>}>
      {!made ? (
        <div className="space-y-4 text-sm">
          <p className="text-muted">Read-only link for <strong>{scope?.clientName}</strong> covering {what}. The client sees trip, LR, delivery date, POD status and the verified POD image only — no driver, phone, freight or other clients&apos; trips. Every view is recorded in the audit log.</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div><Label htmlFor="cl-label" hint="(optional)">Label</Label><Input id="cl-label" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Invoice INV-2041" /></div>
            <div><Label htmlFor="cl-days">Expires after</Label>
              <Select id="cl-days" value={days} onChange={(e) => setDays(e.target.value)}>{["1", "7", "14", "30"].map((v) => <option key={v} value={v}>{v} day{v === "1" ? "" : "s"}</option>)}</Select></div>
          </div>
        </div>
      ) : (
        <div className="space-y-3 text-sm">
          <Label htmlFor="cl-url">Client view link (shown once)</Label>
          <div className="flex gap-2"><Input id="cl-url" readOnly value={made.url} data-testid="client-link-url" />
            <Button variant="outline" aria-label="Copy link" onClick={() => { navigator.clipboard?.writeText(made.url); toast.success("Copied"); }}><Copy className="h-4 w-4" /></Button></div>
          <p className="text-xs text-muted">Expires {dt(made.expires_at)}. You can revoke it any time under Client POD links.</p>
        </div>
      )}
    </Dialog>
  );
}
