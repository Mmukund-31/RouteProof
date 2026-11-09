"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Check, Copy, ExternalLink, Link2, MessageSquare } from "lucide-react";
import { Button, buttonClass } from "@/components/ui/button";
import { Callout, Card, CardHeader, Field, PageHeader } from "@/components/ui/card";
import { Badge, BillingBadge, CategoryBadge, PodBadge, ReasonBadge, REASON_LABELS } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { ImageViewer } from "@/components/auth-image";
import { ActivityTimeline } from "@/components/activity";
import { useAsync } from "@/hooks/use-async";
import { services } from "@/services";
import { d, dt, humanize, inr } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Pod, Trip } from "@/types";

const DATE_SOURCE: Record<string, string> = { import: "trip record", pod_ai: "verified POD", pod_human: "confirmed by reviewer" };

/** Where the trip is on its way to an invoice. Each step is derived from recorded state, never assumed. */
function progress(t: Trip) {
  const billed = ["BILLING_READY", "EXPORTED", "INVOICED"].includes(t.billing_status ?? "");
  return [
    { label: "Delivered", done: !!t.delivery_date || !["IN_TRANSIT"].includes(t.trip_status), note: t.delivery_date ? d(t.delivery_date) : undefined },
    { label: "POD received", done: (t.pods?.length ?? 0) > 0, note: t.pods?.length ? `${t.pods.length} attempt${t.pods.length > 1 ? "s" : ""}` : undefined },
    { label: "POD verified", done: t.pod_status === "VERIFIED" },
    { label: "Billing-ready", done: billed },
    { label: "Exported", done: t.billing_status === "EXPORTED" || t.billing_status === "INVOICED", note: t.exported_at ? d(t.exported_at) : undefined },
    { label: "Invoiced", done: t.billing_status === "INVOICED", note: t.invoice_reference ?? undefined },
  ];
}

/** The one thing to do next on this trip, in plain words, with the action that does it. */
function nextStep(t: Trip, latest: Pod | undefined, openLink: () => void): { tone: "info" | "warning" | "success" | "error"; title: string; text: string; action?: React.ReactNode } {
  const podHref = latest ? `/pods/${latest.id}` : undefined;
  const go = (href: string, label: string) => <Link href={href} className={buttonClass({ size: "sm" })}>{label}<ArrowRight className="h-3.5 w-3.5" /></Link>;
  switch (t.pod_status) {
    case "PENDING": return { tone: "warning", title: "Waiting for the POD", text: t.trip_status === "IN_TRANSIT" ? "The trip is still in transit." : "No proof of delivery has been uploaded. Send the driver an upload link or call them.",
      action: <Button size="sm" onClick={openLink}><Link2 className="h-3.5 w-3.5" />Send upload link</Button> };
    case "UPLOADED": case "AI_PROCESSING": return { tone: "info", title: "AI is reading the POD", text: "The extraction usually finishes within a minute. Nothing to do yet.", action: podHref && go(podHref, "View POD") };
    case "NEEDS_REVIEW": return { tone: "warning", title: "Your decision is needed", text: `The POD was routed to review: ${(latest?.review_reasons ?? []).map((r) => REASON_LABELS[r] ?? humanize(r)).join(", ") || "see the review screen"}.`, action: podHref && go(podHref, "Review POD") };
    case "RETAKE_REQUESTED": return { tone: "warning", title: "Waiting for the driver's retake", text: `A new photo was requested. ${t.retakes_remaining} retake(s) left.`, action: <Button size="sm" variant="outline" onClick={openLink}><Link2 className="h-3.5 w-3.5" />Send upload link</Button> };
    case "REJECTED": return { tone: "error", title: "POD rejected", text: `${t.rejection_reason ?? "The last attempt was rejected."} A new attempt is needed before billing.`, action: <Button size="sm" variant="outline" onClick={openLink}><Link2 className="h-3.5 w-3.5" />Send upload link</Button> };
  }
  if (t.billing_status === "BILLING_READY") return { tone: "success", title: "Ready to export", text: "The POD is verified. Include this trip in the next billing CSV.", action: go("/billing", "Go to billing") };
  if (t.billing_status === "EXPORTED") return { tone: "success", title: "Exported", text: "Record the invoice reference from your accounting system once it is issued.", action: go("/billing", "Record invoice") };
  if (t.billing_status === "INVOICED") return { tone: "success", title: "Complete", text: `Invoice ${t.invoice_reference ?? ""} recorded. Nothing left to do.` };
  return { tone: "info", title: "POD verified", text: "Billing becomes available once nothing else blocks it (for example a confirmed delivery date)." };
}

export default function TripDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const trip = useAsync(() => services.trip(id), [id]);
  const hist = useAsync(() => services.tripHistory(id), [id]);
  const links = useAsync(() => services.driverLinks(id), [id]);
  const [linkOpen, setLinkOpen] = useState(false);
  const [phone, setPhone] = useState("");
  const [link, setLink] = useState<Awaited<ReturnType<typeof services.driverLink>> | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  // Deep link from the missing-POD page: open the "send upload link" dialog straight away.
  useEffect(() => { if (new URLSearchParams(window.location.search).get("link") === "1") setLinkOpen(true); }, []);

  if (trip.error) return <Card><ErrorState message={trip.error} onRetry={trip.reload} /></Card>;
  const t = trip.data;
  if (!t) return <div role="status" aria-label="Loading trip" className="space-y-4"><Skeleton className="h-16 w-1/2" /><Skeleton className="h-96 w-full" /></div>;

  const pods = [...(t.pods ?? [])].sort((a, b) => b.attempt_number - a.attempt_number);
  const latest = pods.find((p) => p.id === t.latest_pod_id) ?? pods[0];
  const openLink = () => { setLink(null); setPhone(""); setCopied(false); setLinkOpen(true); };
  const step = nextStep(t, latest, openLink);
  const steps = progress(t);

  async function revoke(linkId: string) {
    try { await services.revokeDriverLink(linkId); toast.success("Link revoked"); links.reload(); hist.reload(); }
    catch (e) { toast.error((e as Error).message); }
  }
  async function gen() {
    if (phone.trim() && phone.replace(/\D/g, "").length < 10) { toast.error("Enter a 10-digit mobile number, or leave it empty"); return; }
    setBusy(true);
    try { setLink(await services.driverLink(id, phone)); toast.success("Upload link created"); hist.reload(); links.reload(); }
    catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader crumbs={[{ label: "Trips", href: "/trips" }, { label: t.trip_reference }]} title={t.trip_reference}
        meta={<><span>{t.lr_number}</span><span aria-hidden>·</span><span>{t.client.name}</span><span aria-hidden>·</span><span>{t.origin} → {t.destination}</span><PodBadge status={t.pod_status} /><BillingBadge status={t.billing_status} /></>}
        actions={<Button variant="outline" onClick={openLink}><Link2 className="h-4 w-4" />Hired-driver upload link</Button>} />

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-5">
          <Card>
            <CardHeader title="Proof of delivery"
              subtitle={latest ? <>Attempt #{latest.attempt_number} · received {dt(latest.server_received_at)} · {humanize(latest.source)}</> : "No document uploaded yet"}
              action={latest && <Link href={`/pods/${latest.id}`} className={buttonClass({ variant: latest.verification_status === "NEEDS_REVIEW" ? "primary" : "outline", size: "sm" })}>
                {latest.verification_status === "NEEDS_REVIEW" ? "Review POD" : "Open full review"}<ExternalLink className="h-3.5 w-3.5" /></Link>} />
            {latest ? (
              <div className="p-3"><ImageViewer key={latest.id} height="h-[420px]" path={`/pods/${latest.id}/image?variant=upload`} alt={`POD for ${t.trip_reference}, attempt ${latest.attempt_number}`} /></div>
            ) : (
              <EmptyState title="No POD uploaded" text="Waiting for the driver. Hired drivers can upload through a one-time link."
                action={<Button variant="outline" size="sm" onClick={openLink}><Link2 className="h-3.5 w-3.5" />Send upload link</Button>} />
            )}
            {pods.length > 0 && (
              <>
                <div className="border-t border-line-soft px-5 pb-1 pt-3 text-xs font-medium text-muted">All attempts — every attempt is kept, including rejected and retaken documents</div>
                <Table>
                  <THead><tr><TH>Attempt</TH><TH>Status</TH><TH>Received</TH><TH className="hidden sm:table-cell">Source</TH><TH>Decided by</TH><TH><span className="sr-only">Open</span></TH></tr></THead>
                  <TBody>{pods.map((p) => (
                    <TR key={p.id} className={cn(p.id === latest?.id && "bg-surface-2/60")}>
                      <TD className="whitespace-nowrap">#{p.attempt_number}{p.id === latest?.id && <span className="ml-1.5 text-xs text-muted">latest</span>}</TD>
                      <TD><PodBadge status={p.verification_status} /></TD>
                      <TD className="whitespace-nowrap">{dt(p.server_received_at)}</TD>
                      <TD className="hidden sm:table-cell">{humanize(p.source)}</TD>
                      <TD>{p.verification_method === "ai" ? "Automated checks" : p.verification_method === "human" ? "Reviewer" : "—"}</TD>
                      <TD className="text-right"><Link className="text-[13px] font-medium text-teal-700 hover:underline" href={`/pods/${p.id}`}>Open</Link></TD>
                    </TR>
                  ))}</TBody>
                </Table>
              </>
            )}
          </Card>

          <Card>
            <CardHeader title="Trip details" />
            <div className="grid gap-x-8 gap-y-5 p-5 md:grid-cols-3">
              <section aria-label="Shipment"><h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-neutral">Shipment</h3>
                <dl className="space-y-3"><Field k="LR number" v={t.lr_number} /><Field k="E-way bill" v={t.eway_bill_number} /><Field k="Consignee" v={t.consignee_name} />
                  <Field k="Commodity" v={t.commodity} /><Field k="Expected quantity" v={t.expected_quantity !== null ? `${t.expected_quantity} ${t.quantity_unit ?? ""}` : "Not on record"} /></dl></section>
              <section aria-label="Delivery"><h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-neutral">Delivery</h3>
                <dl className="space-y-3"><Field k="Origin" v={t.origin} /><Field k="Destination" v={t.destination} /><Field k="Branch" v={t.branch} />
                  <Field k="Delivery date" v={<>{d(t.delivery_date)}{t.delivery_date_source && <span className="ml-1 text-xs font-normal text-muted">({DATE_SOURCE[t.delivery_date_source]})</span>}</>} />
                  <Field k="Trip status" v={humanize(t.trip_status)} /></dl></section>
              <section aria-label="Vehicle and driver"><h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-neutral">Vehicle & driver</h3>
                <dl className="space-y-3"><Field k="Vehicle" v={`${t.vehicle.registration} (${t.vehicle.type})`} />
                  <Field k="Ownership" v={<Badge tone={t.vehicle.ownership === "hired" ? "amber" : "neutral"}>{t.vehicle.ownership}</Badge>} />
                  <Field k="Driver" v={t.driver?.name ?? "Link upload (no account)"} /><Field k="Client" v={`${t.client.name} (${t.client.code})`} /></dl></section>
            </div>
          </Card>

          <Card>
            <CardHeader title="Verification & audit history" subtitle="Every upload, AI result, decision and export on this trip" />
            {hist.loading ? <Skeleton className="m-5 h-24" /> : hist.error ? <ErrorState message={hist.error} onRetry={hist.reload} /> :
              !hist.data?.items.length ? <EmptyState compact title="No history yet" /> :
              <ActivityTimeline className="px-5 py-4" items={hist.data.items.map((h) => ({ id: h.id, action: h.action, user: h.user, timestamp: h.timestamp }))} />}
          </Card>
        </div>

        <aside className="space-y-5 lg:sticky lg:top-20" aria-label="Status and actions">
          <Card data-testid="next-step">
            <CardHeader title="Status" />
            <div className="space-y-4 p-4">
              <Callout tone={step.tone} title={step.title}>{step.text}</Callout>
              {step.action && <div className="flex">{step.action}</div>}
              <ol className="space-y-2.5" aria-label="Progress">
                {steps.map((s) => (
                  <li key={s.label} className="flex items-center gap-2.5 text-[13px]">
                    <span className={cn("flex h-5 w-5 shrink-0 items-center justify-center rounded-full", s.done ? "bg-teal text-white" : "border border-line bg-surface")} aria-hidden>
                      {s.done && <Check className="h-3 w-3" strokeWidth={3} />}
                    </span>
                    <span className={cn("flex-1", s.done ? "font-medium text-ink" : "text-muted")}>{s.label}<span className="sr-only">{s.done ? " — done" : " — not yet"}</span></span>
                    {s.note && <span className="truncate text-xs text-muted">{s.note}</span>}
                  </li>
                ))}
              </ol>
            </div>
          </Card>

          {latest && (
            <Card>
              <CardHeader title="Latest verification" subtitle={`Attempt #${latest.attempt_number}`} />
              <div className="space-y-3 p-4 text-[13px]">
                {latest.verification_status === "VERIFIED" && <p>Verified by <strong>{latest.verification_method === "ai" ? "automated checks" : "a billing executive"}</strong> on {dt(latest.verified_at)}.</p>}
                {latest.approved_exceptions?.length > 0 && <Callout tone="warning">Approved with exception: {latest.approved_exceptions.map((e) => REASON_LABELS[e] ?? e).join(", ")}</Callout>}
                {latest.rejection_reason && <p className="text-danger-700">Rejected: {latest.rejection_reason}</p>}
                {latest.review_categories?.length > 0 && <div className="flex flex-wrap gap-1">{latest.review_categories.map((c) => <CategoryBadge key={c} c={c} />)}</div>}
                {latest.review_reasons.length > 0 ? <div className="flex flex-wrap gap-1">{latest.review_reasons.map((r) => <ReasonBadge key={r} code={r} />)}</div>
                  : latest.verification_status !== "VERIFIED" && <p className="text-muted">No findings recorded yet.</p>}
              </div>
            </Card>
          )}

          <Card>
            <CardHeader title="Billing" />
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 p-4">
              <Field k="Freight" v={inr(t.freight_amount)} /><Field k="Status" v={<BillingBadge status={t.billing_status} />} />
              <Field k="Billing cycle" v={t.billing_cycle} />
              <Field k="Invoice" v={t.invoice_reference ? `${t.invoice_reference}${t.invoice_date ? ` · ${d(t.invoice_date)}` : ""}` : "Not recorded"} />
            </dl>
            <div className="border-t border-line-soft px-4 py-3">
              <p className="mb-2 text-xs font-medium text-muted">Exports</p>
              {t.billing_history?.length ? (
                <ul className="space-y-1.5">{t.billing_history.map((b) => (
                  <li key={b.export_id} className="flex items-center justify-between gap-2 text-[13px]"><span className="font-medium">{b.export_reference}{b.is_reexport && <Badge tone="amber" className="ml-1.5">re-export</Badge>}</span><span className="text-xs text-muted">{d(b.created_at)}</span></li>
                ))}</ul>
              ) : <p className="text-[13px] text-muted">Not exported yet.</p>}
            </div>
          </Card>

          <Card data-testid="driver-links">
            <CardHeader title="Driver upload links" subtitle="Single-trip, expiring. SMS is mocked: messages are logged, not sent."
              action={<Button size="xs" variant="outline" onClick={openLink}>New link</Button>} />
            {links.loading && !links.data ? <Skeleton className="m-4 h-12" /> : !links.data?.items.length ? <p className="px-4 py-3 text-[13px] text-muted">No links sent for this trip.</p> : (
              <ul className="divide-y divide-line-soft">{links.data.items.map((l) => (
                <li key={l.id} className="px-4 py-3 text-[13px]">
                  <div className="flex items-center justify-between gap-2">
                    <Badge tone={l.state === "active" ? "green" : "neutral"}>{l.state}</Badge>
                    {l.state === "active" && <Button size="xs" variant="danger-outline" onClick={() => void revoke(l.id)}>Revoke</Button>}
                  </div>
                  <div className="mt-1.5 text-xs text-muted">Created {dt(l.created_at)} · expires {dt(l.expires_at)} · {l.use_count} upload(s)</div>
                  {l.sms_log.map((m, i) => (
                    <div key={i} className="mt-1 flex items-center gap-1 text-xs text-muted"><MessageSquare className="h-3.5 w-3.5" aria-hidden />{m.to} · {m.provider} · <strong className="font-medium text-ink">{m.status}</strong></div>
                  ))}
                </li>
              ))}</ul>
            )}
          </Card>
        </aside>
      </div>

      <Dialog open={linkOpen} onClose={() => setLinkOpen(false)} title="Hired-driver upload link"
        description={!link ? "A single-trip, expiring link. The driver opens it on a phone and uploads the POD without an account." : undefined}
        footer={link ? <Button onClick={() => setLinkOpen(false)}>Done</Button> : <><Button variant="outline" onClick={() => setLinkOpen(false)}>Cancel</Button><Button loading={busy} onClick={gen}>Create link</Button></>}>
        {!link ? (
          <div><Label htmlFor="ph" hint="(optional, shown masked in the log)">Driver mobile number</Label><Input id="ph" inputMode="tel" autoComplete="off" placeholder="9XXXXXXXXX" value={phone} onChange={(e) => setPhone(e.target.value)} /></div>
        ) : (
          <div className="space-y-3 text-sm">
            <Callout tone="warning">{link.sms.note} Sent to {link.sms.to} via the {link.sms.provider} provider: <strong>{link.sms.status}</strong>.</Callout>
            <div>
              <Label htmlFor="lk">One-time link (shown once)</Label>
              <div className="flex gap-2"><Input id="lk" readOnly value={link.url} onFocus={(e) => e.currentTarget.select()} />
                <Button variant="outline" aria-label="Copy link" onClick={() => { navigator.clipboard?.writeText(link.url).then(() => { setCopied(true); toast.success("Link copied"); }, () => toast.error("Copy failed — select the link and copy it manually")); }}>
                  {copied ? <Check className="h-4 w-4 text-teal" /> : <Copy className="h-4 w-4" />}
                </Button></div>
            </div>
            <p className="text-xs text-muted">Expires {dt(link.expires_at)}. Only a hash of the token is stored, so this link cannot be shown again.</p>
          </div>
        )}
      </Dialog>
    </>
  );
}
