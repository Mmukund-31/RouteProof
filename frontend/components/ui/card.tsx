import Link from "next/link";
import { AlertTriangle, CheckCircle2, ChevronRight, Info, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export function Card({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border border-line bg-surface shadow-card", className)} {...p} />;
}

export function CardHeader({ title, subtitle, action, className }: { title: React.ReactNode; subtitle?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-start justify-between gap-4 border-b border-line-soft px-5 py-3.5", className)}>
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        {subtitle && <p className="mt-0.5 text-[13px] text-muted">{subtitle}</p>}
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </div>
  );
}

export type Crumb = { label: string; href?: string };

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-2">
      <ol className="flex flex-wrap items-center gap-1 text-[13px] text-muted">
        {items.map((c, i) => (
          <li key={i} className="flex items-center gap-1">
            {i > 0 && <ChevronRight className="h-3.5 w-3.5 text-neutral" aria-hidden />}
            {c.href ? <Link href={c.href} className="hover:text-ink hover:underline">{c.label}</Link>
              : <span aria-current="page" className="font-medium text-ink">{c.label}</span>}
          </li>
        ))}
      </ol>
    </nav>
  );
}

/** Page title block. `meta` sits under the title (status badges, identifiers); `actions` align right. */
export function PageHeader({ title, subtitle, actions, meta, crumbs }: {
  title: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode; meta?: React.ReactNode; crumbs?: Crumb[];
  /** @deprecated section labels now live in the sidebar */ eyebrow?: string;
}) {
  return (
    <div className="mb-5">
      {crumbs && <Breadcrumbs items={crumbs} />}
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <h1 className="text-[22px] font-semibold leading-tight tracking-tight text-ink">{title}</h1>
          {subtitle && <div className="mt-1 max-w-3xl text-sm text-muted">{subtitle}</div>}
          {meta && <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted">{meta}</div>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}

/** Underline tabs for switching between views of one page. */
export function Tabs<T extends string>({ value, onChange, items, className }: {
  value: T; onChange: (v: T) => void; items: readonly (readonly [T, string] | readonly [T, string, number | undefined])[]; className?: string;
}) {
  return (
    <div className={cn("mb-4 flex max-w-full gap-1 overflow-x-auto border-b border-line", className)} role="tablist">
      {items.map(([v, label, count]) => {
        const on = value === v;
        return (
          <button key={v} type="button" role="tab" aria-selected={on} onClick={() => onChange(v)}
            className={cn("relative -mb-px flex items-center gap-2 whitespace-nowrap border-b-2 px-3 pb-2.5 pt-1.5 text-sm font-medium transition-colors",
              on ? "border-forest text-ink" : "border-transparent text-muted hover:text-ink")}>
            {label}
            {count !== undefined && <span className={cn("rounded-full px-1.5 text-[11px] font-semibold tabular-nums leading-[18px]", on ? "bg-forest text-white" : "bg-[#edf1ee] text-muted")}>{count}</span>}
          </button>
        );
      })}
    </div>
  );
}

/** Compact segmented filter (single choice) used in table toolbars. */
export function Segmented<T extends string>({ value, onChange, items, label }: {
  value: T; onChange: (v: T) => void; items: readonly (readonly [T, string] | readonly [T, string, number | undefined])[]; label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex max-w-full overflow-x-auto rounded-lg border border-line bg-surface-2 p-0.5">
      {items.map(([v, l, count]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} onClick={() => onChange(v)}
          className={cn("flex items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1 text-[13px] font-medium transition-colors",
            value === v ? "bg-surface text-ink shadow-[0_1px_2px_rgba(23,51,46,0.1)] ring-1 ring-line" : "text-muted hover:text-ink")}>
          {l}{count !== undefined && <span className="tabular-nums text-muted">{count}</span>}
        </button>
      ))}
    </div>
  );
}

/** Toolbar strip at the top of a table card. */
export function Toolbar({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("flex flex-wrap items-center gap-2 border-b border-line-soft px-4 py-3", className)}>{children}</div>;
}

const CALLOUT = {
  info: { box: "bg-forest-50 text-forest ring-[#d3e0db]", icon: Info },
  success: { box: "bg-teal-50 text-teal-700 ring-[#cde5dc]", icon: CheckCircle2 },
  warning: { box: "bg-amber-50 text-amber-700 ring-[#efdcb4]", icon: AlertTriangle },
  error: { box: "bg-danger-50 text-danger-700 ring-[#f0d2d2]", icon: XCircle },
};

/** Inline notice. Use for explanations that change what the user should do, not for decoration. */
export function Callout({ tone = "info", title, children, className, action, ...p }: {
  tone?: keyof typeof CALLOUT; title?: React.ReactNode; children?: React.ReactNode; className?: string; action?: React.ReactNode;
} & Omit<React.HTMLAttributes<HTMLDivElement>, "title">) {
  const { box, icon: Icon } = CALLOUT[tone];
  return (
    <div className={cn("flex items-start gap-2.5 rounded-lg px-3 py-2.5 text-[13px] ring-1 ring-inset", box, className)} {...p}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={cn(title && "mt-0.5", "leading-relaxed")}>{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

/** Label/value pairs for record details. */
export function Field({ k, v, className }: { k: string; v: React.ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0", className)}>
      <dt className="text-xs text-muted">{k}</dt>
      <dd className="mt-0.5 break-words text-sm font-medium text-ink">{v === null || v === undefined || v === "" ? <span className="font-normal text-neutral">—</span> : v}</dd>
    </div>
  );
}
