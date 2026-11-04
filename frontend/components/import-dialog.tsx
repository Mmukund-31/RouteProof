"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { services } from "@/services";

type Result = Awaited<ReturnType<typeof services.importTrips>>;
const TEMPLATE = "trip_reference,lr_number,eway_bill_number,client_code,vehicle_registration,destination,freight_amount,consignee_name,expected_quantity,quantity_unit,driver_email,delivery_date,branch,billing_cycle\n";

export function ImportDialog({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  async function run(dry: boolean) {
    if (!file) return;
    setBusy(true);
    try {
      const r = await services.importTrips(file, dry);
      setRes(r);
      if (!dry && !r.fatal) { toast.success(`${r.created} trip(s) imported`); onDone(); }
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  }
  function close() { setFile(null); setRes(null); onClose(); }
  const template = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([TEMPLATE], { type: "text/csv" }));
    a.download = "routeproof_trip_import_template.csv"; a.click();
  };
  const ok = res && !res.fatal;
  return (
    <Dialog open={open} onClose={close} title="Import trips from CSV" wide
      footer={<>
        <Button variant="outline" onClick={close}>Close</Button>
        <Button variant="outline" disabled={!file} loading={busy} onClick={() => run(true)}>Validate only</Button>
        <Button disabled={!file || !!(res?.dry_run && (res.fatal || res.created === 0))} loading={busy} onClick={() => run(false)}>Import</Button>
      </>}>
      <p className="text-sm text-muted">Required columns: trip_reference, lr_number, eway_bill_number, client_code, vehicle_registration, destination, freight_amount. Duplicate trip references or LR numbers are skipped. <button className="text-teal underline" onClick={template}>Download template</button></p>
      <input type="file" accept=".csv,text/csv" aria-label="CSV file" className="mt-4 block w-full text-sm" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setRes(null); }} />
      {res?.fatal && <p role="alert" className="mt-4 rounded-lg bg-danger-50 p-3 text-sm text-danger">{res.fatal}</p>}
      {ok && (
        <div className="mt-4 space-y-3 text-sm" aria-live="polite">
          <p className="rounded-lg bg-teal-50 p-3 text-[#1d5c50]">{res.dry_run ? "Validation result (nothing saved yet): " : "Imported: "}<strong>{res.created}</strong> new trip(s), {res.duplicates.length} duplicate(s) skipped, {res.errors.length} row error(s).</p>
          {res.unknown_columns && res.unknown_columns.length > 0 && <p className="text-muted">Ignored columns: {res.unknown_columns.join(", ")}</p>}
          {res.duplicates.length > 0 && <div><div className="font-medium">Duplicates</div><ul className="mt-1 list-disc pl-5 text-muted">{res.duplicates.slice(0, 20).map((x) => <li key={x.row}>Row {x.row}: {x.trip_reference}</li>)}</ul></div>}
          {res.errors.length > 0 && <div><div className="font-medium">Row errors</div><ul className="mt-1 list-disc pl-5 text-danger">{res.errors.slice(0, 20).map((x, i) => <li key={i}>Row {x.row}: {x.message}</li>)}</ul></div>}
        </div>
      )}
    </Dialog>
  );
}
