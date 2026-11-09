import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";

/** Tables scroll inside their card, never the page. */
export function Table({ className, ...p }: React.HTMLAttributes<HTMLTableElement>) {
  return <div className="overflow-x-auto"><table className={cn("w-full text-sm", className)} {...p} /></div>;
}
export const THead = (p: React.HTMLAttributes<HTMLTableSectionElement>) => <thead className="border-b border-line-soft bg-surface-2 text-left" {...p} />;
export const TBody = (p: React.HTMLAttributes<HTMLTableSectionElement>) => <tbody className="divide-y divide-line-soft" {...p} />;
export function TH({ className, num, ...p }: React.ThHTMLAttributes<HTMLTableCellElement> & { num?: boolean }) {
  return <th scope="col" className={cn("h-9 whitespace-nowrap px-4 text-xs font-medium text-muted", num && "text-right", className)} {...p} />;
}
export function TD({ className, num, ...p }: React.TdHTMLAttributes<HTMLTableCellElement> & { num?: boolean }) {
  return <td className={cn("px-4 py-3 align-middle text-ink", num && "num", className)} {...p} />;
}
export function TR({ className, ...p }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("transition-colors hover:bg-surface-2", className)} {...p} />;
}

export type Sort = { key: string; dir: "asc" | "desc" } | null;
export const sortParam = (s: Sort) => (s ? `${s.dir === "desc" ? "-" : ""}${s.key}` : undefined);

/** Header cell that cycles ascending → descending → default order. */
export function SortTH({ label, k, sort, onSort, num, className }: {
  label: string; k: string; sort: Sort; onSort: (s: Sort) => void; num?: boolean; className?: string;
}) {
  const active = sort?.key === k;
  const next: Sort = !active ? { key: k, dir: "asc" } : sort!.dir === "asc" ? { key: k, dir: "desc" } : null;
  const Icon = !active ? ChevronsUpDown : sort!.dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <th scope="col" aria-sort={active ? (sort!.dir === "asc" ? "ascending" : "descending") : "none"}
      className={cn("h-9 whitespace-nowrap px-4 text-xs font-medium text-muted", num && "text-right", className)}>
      <button type="button" onClick={() => onSort(next)} className={cn("-mx-1 inline-flex items-center gap-1 rounded px-1 py-0.5 hover:bg-forest-50 hover:text-ink", active && "text-ink")}>
        {label}<Icon className={cn("h-3.5 w-3.5", !active && "text-neutral/70")} aria-hidden />
      </button>
    </th>
  );
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const btn = "inline-flex h-8 items-center gap-1 rounded-md border border-line bg-surface px-2.5 font-medium text-ink hover:bg-surface-2 disabled:pointer-events-none disabled:opacity-40";
  return (
    <nav aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-2 border-t border-line-soft px-4 py-2.5 text-[13px] text-muted">
      <span>Showing <span className="font-medium text-ink">{from}–{Math.min(page * pageSize, total)}</span> of <span className="font-medium text-ink">{total}</span></span>
      <div className="flex items-center gap-2">
        <button type="button" className={btn} disabled={page <= 1} onClick={() => onPage(page - 1)}><ChevronLeft className="h-4 w-4" aria-hidden />Previous</button>
        <span className="num min-w-14 text-center">{page} / {pages}</span>
        <button type="button" className={btn} disabled={page >= pages} onClick={() => onPage(page + 1)}>Next<ChevronRight className="h-4 w-4" aria-hidden /></button>
      </div>
    </nav>
  );
}
