import { actionLabel, actionTone, dt } from "@/lib/format";
import { cn } from "@/lib/utils";

const DOT = { good: "border-teal bg-teal", bad: "border-danger bg-danger", warn: "border-amber bg-amber", plain: "border-neutral bg-surface" };

export interface ActivityItem { id: string; action: string; user: string | null; timestamp: string; detail?: React.ReactNode }

/** Vertical timeline of audit events. Problem events get a red/amber marker; everything else stays quiet. */
export function ActivityTimeline({ items, className }: { items: ActivityItem[]; className?: string }) {
  return (
    <ol className={cn("relative", className)}>
      {items.map((a, i) => (
        <li key={a.id} className="relative flex gap-3 pb-3.5 last:pb-0">
          {i < items.length - 1 && <span className="absolute left-[4.5px] top-3.5 h-full w-px bg-line" aria-hidden />}
          <span className={cn("mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full border-2", DOT[actionTone(a.action)])} aria-hidden />
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-medium text-ink">{actionLabel(a.action)}</div>
            <div className="text-xs text-muted">{a.user ?? "System / link"} · <time dateTime={a.timestamp}>{dt(a.timestamp)}</time></div>
            {a.detail && <div className="mt-1 text-xs text-muted">{a.detail}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}
