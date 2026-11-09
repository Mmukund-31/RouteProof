import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

type Tone = "default" | "amber" | "red" | "green";
const BAR: Record<Tone, string> = { default: "bg-line", green: "bg-teal", amber: "bg-amber", red: "bg-danger" };

/**
 * Metric card: the number is the hero. Tone is a thin status marker, never a coloured card. When `href` is set the card
 * is a link and says where it goes (`action`), so the figure is always one click from the records behind it.
 */
export function Kpi({ label, value, hint, tone = "default", href, action, icon: Icon, testId }: {
  label: string; value: React.ReactNode; hint?: React.ReactNode; tone?: Tone; href?: string; action?: string; icon?: React.ElementType; testId?: string;
}) {
  const body = (
    <div data-testid={testId} className={cn("group relative flex h-full flex-col overflow-hidden rounded-xl border border-line bg-surface px-4 pb-3 pt-3.5 shadow-card transition-colors",
      href && "hover:border-[#c6d3cc]")}>
      <span className={cn("absolute inset-y-0 left-0 w-[3px]", BAR[tone])} aria-hidden />
      <div className="flex items-center gap-2 text-[13px] font-medium text-muted">
        {Icon && <Icon className="h-4 w-4 shrink-0 text-neutral" aria-hidden />}
        <span className="truncate">{label}</span>
      </div>
      <div className="num mt-1.5 !text-left text-[26px] font-semibold leading-tight tracking-tight text-ink">{value}</div>
      {hint && <div className="mt-1 text-xs leading-snug text-muted">{hint}</div>}
      {href && action && (
        <div className="mt-auto flex items-center gap-1 pt-2.5 text-xs font-medium text-teal-700 group-hover:underline">{action}<ArrowRight className="h-3.5 w-3.5" aria-hidden /></div>
      )}
    </div>
  );
  return href ? <Link href={href} className="block h-full rounded-xl">{body}</Link> : body;
}
