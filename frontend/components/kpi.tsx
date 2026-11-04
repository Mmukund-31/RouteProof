import Link from "next/link";
import { cn } from "@/lib/utils";

export function Kpi({ label, value, hint, tone = "default", href }: {
  label: string; value: React.ReactNode; hint?: string; tone?: "default" | "amber" | "red" | "green"; href?: string;
}) {
  const body = (
    <div className={cn("rounded-xl border bg-surface px-4 py-3 transition-colors", href && "hover:border-teal",
      tone === "amber" ? "border-amber/50" : tone === "red" ? "border-danger/40" : "border-line")}>
      <div className="text-xs font-medium text-muted">{label}</div>
      <div className={cn("num mt-1 text-2xl font-semibold tracking-tight !text-left",
        tone === "amber" ? "text-[#8a5f12]" : tone === "red" ? "text-danger" : tone === "green" ? "text-teal" : "text-forest")}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
    </div>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}
