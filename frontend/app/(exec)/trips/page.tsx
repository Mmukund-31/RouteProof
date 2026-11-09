"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, PageHeader, Segmented, Toolbar } from "@/components/ui/card";
import { Badge, BillingBadge, BILLING_STATUS, PodBadge } from "@/components/ui/badge";
import { Input, SearchInput, Select } from "@/components/ui/input";
import { Pagination, SortTH, sortParam, Table, TBody, TD, TH, THead, TR, type Sort } from "@/components/ui/table";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { ImportDialog } from "@/components/import-dialog";
import { useAsync, useDebounced } from "@/hooks/use-async";
import { useSessionState } from "@/hooks/use-session-state";
import { services } from "@/services";
import { d, humanize, inr } from "@/lib/format";

const PAGE = 20;
/** POD-status views, in workflow order. "Exception" cases live under Needs review and on the Exceptions page. */
const VIEWS = [["", "All"], ["PENDING", "Awaiting POD"], ["AI_PROCESSING", "Processing"], ["NEEDS_REVIEW", "Needs review"],
  ["RETAKE_REQUESTED", "Retake requested"], ["VERIFIED", "Verified"], ["REJECTED", "Rejected"]] as const;
const TRIP_STATES = ["IN_TRANSIT", "DELIVERED", "POD_PENDING", "POD_VERIFIED", "CANCELLED"];
const EMPTY = { client_id: "", branch: "", billing_status: "", trip_status: "", date_from: "", date_to: "" };
type Filters = typeof EMPTY;

export default function TripsPage() {
  const router = useRouter();
  const [q, setQ] = useSessionState("rp_trips_q", "");
  const [view, setView] = useSessionState<string>("rp_trips_view", "");
  const [f, setF] = useSessionState<Filters>("rp_trips_filters", EMPTY);
  const [sort, setSort] = useSessionState<Sort>("rp_trips_sort", null);
  const [page, setPage] = useSessionState("rp_trips_page", 1);
  const [importing, setImporting] = useState(false);
  // Deep link from the global "Find trip" box: /trips?q=LR-123
  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("q");
    if (fromUrl) { setQ(fromUrl); setView(""); setF(EMPTY); setPage(1); }
  }, [setQ, setView, setF, setPage]);

  const dq = useDebounced(q);
  const opts = useAsync(() => services.options(), []);
  const res = useAsync(() => services.trips({ q: dq, ...f, pod_status: view, sort: sortParam(sort), page, page_size: PAGE }),
    [dq, view, f.client_id, f.branch, f.billing_status, f.trip_status, f.date_from, f.date_to, sort?.key, sort?.dir, page]);
  const set = (k: keyof Filters) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => { setF({ ...f, [k]: e.target.value }); setPage(1); };
  const active = Object.values(f).filter(Boolean).length + (view ? 1 : 0) + (q ? 1 : 0);
  const clear = () => { setF(EMPTY); setView(""); setQ(""); setPage(1); };
  const onSort = (s: Sort) => { setSort(s); setPage(1); };

  return (
    <>
      <PageHeader title="Trips" subtitle="Every trip with its LR, e-way bill, POD and billing state. Open a trip for its evidence and history."
        actions={<Button variant="outline" onClick={() => setImporting(true)}><Upload className="h-4 w-4" />Import trips (CSV)</Button>} />
      <Card>
        <Toolbar className="gap-3">
          <SearchInput className="w-full lg:w-96" label="Search trips" placeholder="Trip, LR, e-way bill, destination, client or vehicle"
            value={q} onChange={(v) => { setQ(v); setPage(1); }} />
          <Segmented label="POD status" value={view} onChange={(v) => { setView(v); setPage(1); }} items={VIEWS} />
        </Toolbar>
        <Toolbar className="gap-2 bg-surface-2/60 py-2.5">
          <Select aria-label="Client" className="w-auto min-w-36 flex-1 sm:flex-none" value={f.client_id} onChange={set("client_id")}><option value="">All clients</option>{opts.data?.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
          <Select aria-label="Branch" className="w-auto min-w-32 flex-1 sm:flex-none" value={f.branch} onChange={set("branch")}><option value="">All branches</option>{opts.data?.branches.map((b) => <option key={b}>{b}</option>)}</Select>
          <Select aria-label="Billing status" className="w-auto min-w-36 flex-1 sm:flex-none" value={f.billing_status} onChange={set("billing_status")}><option value="">Any billing status</option>{Object.entries(BILLING_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</Select>
          <Select aria-label="Trip status" className="w-auto min-w-36 flex-1 sm:flex-none" value={f.trip_status} onChange={set("trip_status")}><option value="">Any trip status</option>{TRIP_STATES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}</Select>
          <div className="flex min-w-0 flex-1 items-center gap-1.5 sm:flex-none">
            <Input type="date" aria-label="Delivered from" className="w-auto min-w-0" value={f.date_from} max={f.date_to || undefined} onChange={set("date_from")} />
            <span className="text-xs text-muted">to</span>
            <Input type="date" aria-label="Delivered to" className="w-auto min-w-0" value={f.date_to} min={f.date_from || undefined} onChange={set("date_to")} />
          </div>
          {active > 0 && <Button variant="ghost" size="sm" className="text-teal-700" onClick={clear}><X className="h-3.5 w-3.5" />Clear all</Button>}
          <span className="ml-auto text-[13px] text-muted" aria-live="polite">{res.data ? `${res.data.total} trip${res.data.total === 1 ? "" : "s"}` : ""}</span>
        </Toolbar>
        {res.loading && !res.data ? <TableSkeleton cols={8} /> : res.error ? <ErrorState message={res.error} onRetry={res.reload} /> :
          !res.data?.items.length ? (
            <EmptyState title="No trips match" text={active ? "Try a different search or clear the filters." : "Import a CSV of trips to get started."}
              action={active ? <Button variant="outline" size="sm" onClick={clear}>Clear filters</Button> : undefined} />
          ) : (
            <>
              <Table>
                <THead><tr>
                  <SortTH label="Trip / LR" k="trip_reference" sort={sort} onSort={onSort} />
                  <SortTH label="Client" k="client" sort={sort} onSort={onSort} className="hidden md:table-cell" />
                  <SortTH label="Route" k="destination" sort={sort} onSort={onSort} />
                  <SortTH label="Vehicle · driver" k="vehicle" sort={sort} onSort={onSort} className="hidden xl:table-cell" />
                  <SortTH label="Delivered" k="delivery_date" sort={sort} onSort={onSort} />
                  <SortTH label="Freight" k="freight_amount" sort={sort} onSort={onSort} num />
                  <TH>POD</TH><TH className="hidden sm:table-cell">Billing</TH><TH><span className="sr-only">Open</span></TH>
                </tr></THead>
                <TBody>
                  {res.data.items.map((t) => (
                    <TR key={t.id} className="cursor-pointer" onClick={(e) => { if (!(e.target as HTMLElement).closest("a,button")) router.push(`/trips/${t.id}`); }}>
                      <TD className="whitespace-nowrap">
                        <Link href={`/trips/${t.id}`} className="font-medium text-ink hover:text-teal-700 hover:underline">{t.trip_reference}</Link>
                        <div className="text-xs text-muted">{t.lr_number}<span className="hidden lg:inline"> · EWB {t.eway_bill_number}</span></div>
                      </TD>
                      <TD className="hidden max-w-52 md:table-cell"><div className="truncate" title={t.client.name}>{t.client.name}</div></TD>
                      <TD className="max-w-56"><div className="truncate" title={`${t.origin} → ${t.destination}`}>{t.destination}</div><div className="truncate text-xs text-muted">from {t.origin}{t.branch ? ` · ${t.branch}` : ""}</div></TD>
                      <TD className="hidden whitespace-nowrap xl:table-cell">
                        <div className="flex items-center gap-1.5">{t.vehicle.registration}{t.vehicle.ownership === "hired" && <Badge tone="amber">hired</Badge>}</div>
                        <div className="max-w-44 truncate text-xs text-muted">{t.driver?.name ?? "Link upload (no account)"}</div>
                      </TD>
                      <TD className="whitespace-nowrap">{t.delivery_date ? d(t.delivery_date) : <span className="text-muted">In transit</span>}</TD>
                      <TD num className="whitespace-nowrap font-medium">{inr(t.freight_amount)}</TD>
                      <TD className="whitespace-nowrap"><PodBadge status={t.pod_status} /></TD>
                      <TD className="hidden whitespace-nowrap sm:table-cell"><BillingBadge status={t.billing_status} /></TD>
                      <TD className="w-8 pl-0 text-neutral"><ChevronRight className="h-4 w-4" aria-hidden /></TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <Pagination page={page} pageSize={PAGE} total={res.data.total} onPage={setPage} />
            </>
          )}
      </Card>
      <ImportDialog open={importing} onClose={() => setImporting(false)} onDone={res.reload} />
    </>
  );
}
