import { cn } from "@/lib/utils";

export function Logo({ className, light }: { className?: string; light?: boolean }) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/icon.svg" alt="" className="h-8 w-8" />
      <div className="leading-tight">
        <div className={cn("text-base font-semibold tracking-tight", light ? "text-white" : "text-forest")}>RouteProof</div>
        <div className={cn("text-[10px] uppercase tracking-wider", light ? "text-white/60" : "text-muted")}>Proof of Delivery Intelligence</div>
      </div>
    </div>
  );
}
