"use client";
import { use, useEffect, useState } from "react";
import { CheckCircle2, Clock, ImageOff, Link2Off, X } from "lucide-react";
import { Logo } from "@/components/logo";
import { Skeleton } from "@/components/ui/states";
import { API_BASE } from "@/lib/api";
import { d, dt } from "@/lib/format";
import type { ClientView } from "@/types";

/** Public, read-only client view. The link token is the only credential: no cookies are sent with these requests. */
const base = (token: string) => `${API_BASE}/api/v1/client-view/${encodeURIComponent(token)}`;

function PodImage({ token, tripId, alt }: { token: string; tripId: string; alt: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let url: string | null = null; let live = true;
    fetch(`${base(token)}/trips/${tripId}/pod-image`, { credentials: "omit" })
      .then((r) => (r.ok ? r.blob() : Promise.reject()))
      .then((b) => { if (live) { url = URL.createObjectURL(b); setSrc(url); } })
      .catch(() => live && setErr(true));
    return () => { live = false; if (url) URL.revokeObjectURL(url); };
  }, [token, tripId]);
  if (err) return <div className="flex h-64 flex-col items-center justify-center gap-2 text-muted"><ImageOff className="h-8 w-8" />Image unavailable</div>;
  // eslint-disable-next-line @next/next/no-img-element
  return src ? <img src={src} alt={alt} className="mx-auto max-h-[75vh] w-auto rounded-lg" /> : <Skeleton className="h-96 w-full" />;
}

export default function ClientViewPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [data, setData] = useState<ClientView | null>(null);
  const [status, setStatus] = useState<number | null>(null);
  const [open, setOpen] = useState<ClientView["trips"][number] | null>(null);
  useEffect(() => {
    fetch(base(token), { credentials: "omit" })
      .then(async (r) => { if (!r.ok) { setStatus(r.status); return; } setData(await r.json()); })
      .catch(() => setStatus(0));
  }, [token]);

  return (
    <div className="min-h-screen bg-canvas">
      <header className="bg-forest text-white"><div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3"><Logo light /><span className="text-sm text-white/80">Proof of delivery</span></div></header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        {status !== null ? (
          <div className="mx-auto flex max-w-md flex-col items-center gap-3 rounded-3xl bg-surface p-8 text-center ring-1 ring-line" data-testid="client-view-error">
            <Link2Off className="h-12 w-12 text-muted" />
            <h1 className="text-xl font-bold text-forest">{status === 410 ? "This link has expired or was withdrawn" : status === 0 ? "Cannot reach the server" : "This link is not valid"}</h1>
            <p className="text-muted">Please ask your transport partner for a new link.</p>
          </div>
        ) : !data ? <Skeleton className="h-64 w-full" /> : (
          <>
            <h1 className="text-2xl font-bold text-forest">{data.client}</h1>
            <p className="mt-1 text-sm text-muted">{data.label ?? (data.billing_cycle ? `Billing cycle ${data.billing_cycle}` : "Selected trips")} · link valid until {dt(data.expires_at)}</p>
            <p className="mt-1 text-xs text-muted">{data.note}</p>
            <div className="mt-5 overflow-x-auto rounded-2xl bg-surface ring-1 ring-line">
              <table className="w-full text-sm" data-testid="client-view-table">
                <thead className="border-b border-line text-left text-xs uppercase text-muted"><tr><th className="px-4 py-3">Trip</th><th className="px-4 py-3">LR number</th><th className="px-4 py-3">Delivered</th><th className="px-4 py-3">Destination</th><th className="px-4 py-3">POD</th><th /></tr></thead>
                <tbody className="divide-y divide-line">{data.trips.map((t) => (
                  <tr key={t.trip_id}>
                    <td className="px-4 py-3 font-medium">{t.trip_reference}</td><td className="px-4 py-3">{t.lr_number}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{d(t.delivery_date)}</td><td className="px-4 py-3">{t.destination}</td>
                    <td className="px-4 py-3">{t.pod_status === "VERIFIED"
                      ? <span className="inline-flex items-center gap-1 text-teal"><CheckCircle2 className="h-4 w-4" />Verified {t.pod_reference && <span className="text-xs text-muted">{t.pod_reference}</span>}</span>
                      : <span className="inline-flex items-center gap-1 text-muted"><Clock className="h-4 w-4" />Not yet available</span>}</td>
                    <td className="px-4 py-3">{t.has_image && <button className="font-medium text-teal hover:underline" onClick={() => setOpen(t)}>View POD</button>}</td>
                  </tr>
                ))}</tbody>
              </table>
              {!data.trips.length && <p className="p-6 text-center text-muted">No trips in this link.</p>}
            </div>
          </>
        )}
        {open && (
          <div role="dialog" aria-modal="true" aria-label={`POD for ${open.trip_reference}`} className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setOpen(null)}>
            <div className="max-h-full w-full max-w-3xl overflow-auto rounded-2xl bg-surface p-4" onClick={(e) => e.stopPropagation()}>
              <div className="mb-3 flex items-center justify-between"><div><div className="font-semibold">{open.trip_reference} · {open.lr_number}</div><div className="text-xs text-muted">Delivered {d(open.delivery_date)} · verified {dt(open.pod_verified_at)}</div></div>
                <button aria-label="Close" onClick={() => setOpen(null)}><X className="h-5 w-5" /></button></div>
              <PodImage token={token} tripId={open.trip_id} alt={`Proof of delivery for ${open.trip_reference}`} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
