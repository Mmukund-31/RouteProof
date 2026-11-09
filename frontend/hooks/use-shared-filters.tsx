"use client";
import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { Input, Select } from "@/components/ui/input";
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

/** One compact row of scope filters. Each control keeps a visible caption so the row reads without opening anything. */
export function FilterBar({ f, onChange, opts, extra }: { f: DashFilters; onChange: (f: DashFilters) => void; opts?: Options | null; extra?: React.ReactNode }) {
  const set = (k: keyof DashFilters) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => onChange({ ...f, [k]: e.target.value });
  const active = activeFilterCount(f);
  const cap = "mb-1 block text-xs font-medium text-muted";
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="min-w-[9.5rem] flex-1 sm:flex-none"><label htmlFor="df" className={cap}>Delivery from</label><Input id="df" type="date" value={f.date_from} max={f.date_to || undefined} onChange={set("date_from")} /></div>
      <div className="min-w-[9.5rem] flex-1 sm:flex-none"><label htmlFor="dt" className={cap}>Delivery to</label><Input id="dt" type="date" value={f.date_to} min={f.date_from || undefined} onChange={set("date_to")} /></div>
      <div className="min-w-[10rem] flex-1"><label htmlFor="cl" className={cap}>Client</label>
        <Select id="cl" value={f.client_id} onChange={set("client_id")}><option value="">All clients</option>{opts?.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></div>
      <div className="min-w-[8rem] flex-1"><label htmlFor="br" className={cap}>Branch</label>
        <Select id="br" value={f.branch} onChange={set("branch")}><option value="">All branches</option>{opts?.branches.map((b) => <option key={b}>{b}</option>)}</Select></div>
      <div className="min-w-[8rem] flex-1"><label htmlFor="bc" className={cap}>Billing cycle</label>
        <Select id="bc" value={f.billing_cycle} onChange={set("billing_cycle")}><option value="">All cycles</option>{opts?.billing_cycles.map((c) => <option key={c}>{c}</option>)}</Select></div>
      {extra}
      <button type="button" className="inline-flex h-9 items-center gap-1 rounded-lg px-2 text-[13px] font-medium text-teal-700 hover:bg-teal-50 disabled:pointer-events-none disabled:text-neutral"
        disabled={!active} onClick={() => onChange(EMPTY_FILTERS)}>
        <X className="h-3.5 w-3.5" aria-hidden />Clear filters{active > 0 && <span className="tabular-nums"> ({active})</span>}
      </button>
    </div>
  );
}
