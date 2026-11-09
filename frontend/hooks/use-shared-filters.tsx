"use client";
import { useEffect, useState } from "react";
import { Input, Label, Select } from "@/components/ui/input";
import type { Options } from "@/types";

/** Filters shared by the dashboard and the missing-POD page, so both always describe the same trips. */
export type DashFilters = { date_from: string; date_to: string; client_id: string; branch: string; billing_cycle: string };
export const EMPTY_FILTERS: DashFilters = { date_from: "", date_to: "", client_id: "", branch: "", billing_cycle: "" };
const KEY = "rp_dash_filters";

export function useSharedFilters(): [DashFilters, (f: DashFilters) => void] {
  const [f, setF] = useState<DashFilters>(EMPTY_FILTERS);
  useEffect(() => { // after mount, so server and first client render agree
    try { const s = sessionStorage.getItem(KEY); if (s) setF({ ...EMPTY_FILTERS, ...JSON.parse(s) }); } catch { /* storage blocked */ }
  }, []);
  const set = (n: DashFilters) => { setF(n); try { sessionStorage.setItem(KEY, JSON.stringify(n)); } catch { /* ignore */ } };
  return [f, set];
}

export const activeFilterCount = (f: DashFilters) => Object.values(f).filter(Boolean).length;

export function FilterBar({ f, onChange, opts, extra }: { f: DashFilters; onChange: (f: DashFilters) => void; opts?: Options | null; extra?: React.ReactNode }) {
  const set = (k: keyof DashFilters) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => onChange({ ...f, [k]: e.target.value });
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
      <div><Label htmlFor="df">Delivery from</Label><Input id="df" type="date" value={f.date_from} onChange={set("date_from")} /></div>
      <div><Label htmlFor="dt">Delivery to</Label><Input id="dt" type="date" value={f.date_to} onChange={set("date_to")} /></div>
      <div><Label htmlFor="cl">Client</Label>
        <Select id="cl" value={f.client_id} onChange={set("client_id")}><option value="">All clients</option>{opts?.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></div>
      <div><Label htmlFor="br">Branch</Label>
        <Select id="br" value={f.branch} onChange={set("branch")}><option value="">All branches</option>{opts?.branches.map((b) => <option key={b}>{b}</option>)}</Select></div>
      <div><Label htmlFor="bc">Billing cycle</Label>
        <Select id="bc" value={f.billing_cycle} onChange={set("billing_cycle")}><option value="">All cycles</option>{opts?.billing_cycles.map((c) => <option key={c}>{c}</option>)}</Select></div>
      <div className="flex items-end gap-3">
        {extra}
        <button className="h-10 text-sm text-teal underline-offset-2 hover:underline" onClick={() => onChange(EMPTY_FILTERS)}>Clear filters</button>
      </div>
    </div>
  );
}
