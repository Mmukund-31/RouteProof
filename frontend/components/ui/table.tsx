import { cn } from "@/lib/utils";

export function Table({ className, ...p }: React.HTMLAttributes<HTMLTableElement>) {
  return <div className="overflow-x-auto"><table className={cn("w-full text-sm", className)} {...p} /></div>;
}
export const THead = (p: React.HTMLAttributes<HTMLTableSectionElement>) => <thead className="bg-canvas/70 text-left" {...p} />;
export const TBody = (p: React.HTMLAttributes<HTMLTableSectionElement>) => <tbody className="divide-y divide-line" {...p} />;
export function TH({ className, num, ...p }: React.ThHTMLAttributes<HTMLTableCellElement> & { num?: boolean }) {
  return <th scope="col" className={cn("whitespace-nowrap px-4 py-2.5 text-xs font-medium uppercase tracking-wide text-muted", num && "text-right", className)} {...p} />;
}
export function TD({ className, num, ...p }: React.TdHTMLAttributes<HTMLTableCellElement> & { num?: boolean }) {
  return <td className={cn("px-4 py-3 align-middle", num && "num", className)} {...p} />;
}
export function TR({ className, ...p }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("hover:bg-canvas/50", className)} {...p} />;
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  return (
    <div className="flex items-center justify-between border-t border-line px-4 py-3 text-sm text-muted">
      <span>{from}–{Math.min(page * pageSize, total)} of {total}</span>
      <div className="flex items-center gap-2">
        <button className="rounded-md border border-line px-3 py-1 hover:bg-canvas disabled:opacity-40" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
        <span className="num">{page} / {pages}</span>
        <button className="rounded-md border border-line px-3 py-1 hover:bg-canvas disabled:opacity-40" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
      </div>
    </div>
  );
}
