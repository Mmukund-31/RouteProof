"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AlertOctagon, ClipboardCheck, FileSpreadsheet, History, LayoutDashboard, LogOut, Menu, PackageSearch, Route, Search, X } from "lucide-react";
import { Logo } from "@/components/logo";
import { useRequireRole, useAuth } from "@/lib/auth";
import { services } from "@/services";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/states";

type CountKey = "review" | "exceptions" | "billing";
type Item = { href: string; label: string; icon: React.ElementType; also?: string[]; count?: CountKey; hint: string };

/**
 * One item per job, in the order a billing executive works: decide on documents, settle exceptions, chase missing
 * PODs, export. Trips and the audit log are the records behind that work.
 */
const SECTIONS: { title: string; items: Item[] }[] = [
  { title: "Overview", items: [{ href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, hint: "What needs attention today" }] },
  {
    title: "Work queues", items: [
      { href: "/reviews", label: "Review queue", icon: ClipboardCheck, also: ["/pods"], count: "review", hint: "PODs waiting for a decision" },
      { href: "/exceptions", label: "Exceptions", icon: AlertOctagon, count: "exceptions", hint: "Shortage, damage and mismatch cases" },
      { href: "/operations", label: "Missing PODs", icon: PackageSearch, hint: "Delivered trips with no usable POD" },
      { href: "/billing", label: "Billing & exports", icon: FileSpreadsheet, also: ["/client-links"], count: "billing", hint: "Verified trips ready to export" },
    ],
  },
  {
    title: "Records", items: [
      { href: "/trips", label: "Trips", icon: Route, hint: "All trips and POD records" },
      { href: "/audit", label: "Audit history", icon: History, hint: "Every upload, decision and export" },
    ],
  },
];
const ALL = SECTIONS.flatMap((s) => s.items);
const isActive = (path: string, it: Item) => path === it.href || path.startsWith(it.href + "/") || (it.also ?? []).some((a) => path.startsWith(a));

/** Work waiting for the billing executive, shown beside the nav items. Refreshed on every navigation. */
function useCounts(path: string) {
  const [c, setC] = useState<Partial<Record<CountKey, number>> & { demo?: boolean }>({});
  useEffect(() => {
    let live = true;
    Promise.allSettled([
      services.reviews({ status: "NEEDS_REVIEW", page_size: 1 }),
      services.reviews({ status: "NEEDS_REVIEW", category: "business", page_size: 1 }),
      services.billingQueue({ export_status: "NOT_EXPORTED", page_size: 1 }),
      services.options(),
    ]).then(([r, e, b, o]) => {
      if (!live) return;
      setC({
        review: r.status === "fulfilled" ? r.value.total : undefined,
        exceptions: e.status === "fulfilled" ? e.value.total : undefined,
        billing: b.status === "fulfilled" ? b.value.total : undefined,
        demo: o.status === "fulfilled" ? o.value.data_source === "demo" : undefined,
      });
    });
    return () => { live = false; };
  }, [path]);
  return c;
}

/** Jump straight to a trip by reference, LR, e-way bill or vehicle from any screen. */
function QuickFind({ className }: { className?: string }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  return (
    <form role="search" className={cn("relative", className)} onSubmit={(e) => { e.preventDefault(); if (q.trim()) { router.push(`/trips?q=${encodeURIComponent(q.trim())}`); setQ(""); } }}>
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral" aria-hidden />
      <input aria-label="Find a trip" placeholder="Find trip, LR or e-way bill…" value={q} onChange={(e) => setQ(e.target.value)}
        className="h-8 w-full rounded-lg border border-line bg-surface-2 pl-8 pr-3 text-[13px] text-ink placeholder:text-neutral focus:border-teal focus:bg-surface focus:outline-none focus:ring-3 focus:ring-teal/15" />
    </form>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading } = useRequireRole("billing_executive");
  const { logout } = useAuth();
  const path = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const counts = useCounts(path);

  useEffect(() => { setOpen(false); }, [path]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; };
  }, [open]);

  if (loading || !user) {
    return <div className="p-8" role="status" aria-label="Loading"><Skeleton className="mb-4 h-8 w-64" /><Skeleton className="h-64 w-full" /></div>;
  }
  const initials = user.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  const signOut = async () => { await logout(); router.replace("/login"); };
  const current = ALL.find((it) => isActive(path, it));

  const nav = (
    <nav aria-label="Main" className="flex flex-1 flex-col gap-5 overflow-y-auto px-3">
      {SECTIONS.map((s) => (
        <div key={s.title}>
          <p className="mb-1 px-2.5 text-[11px] font-medium text-white/45">{s.title}</p>
          <ul className="flex flex-col gap-px">
            {s.items.map((it) => {
              const { href, label, icon: Icon, count, hint } = it;
              const active = isActive(path, it);
              const n = count ? counts[count] : undefined;
              return (
                <li key={href}>
                  <Link href={href} onClick={() => setOpen(false)} aria-current={active ? "page" : undefined} title={hint}
                    className={cn("relative flex h-9 items-center gap-2.5 rounded-md px-2.5 text-[13.5px] font-medium transition-colors",
                      active ? "bg-white/[0.12] text-white" : "text-white/70 hover:bg-white/[0.06] hover:text-white")}>
                    {active && <span className="absolute inset-y-2 -left-3 w-[3px] rounded-r bg-amber" aria-hidden />}
                    <Icon className={cn("h-4 w-4 shrink-0", active ? "text-white" : "text-white/60")} aria-hidden />
                    <span className="flex-1 truncate">{label}</span>
                    {n !== undefined && n > 0 && (
                      <span className={cn("min-w-5 rounded px-1.5 text-center text-[11px] font-semibold tabular-nums leading-[18px]",
                        count === "billing" ? "bg-white/15 text-white" : "bg-amber text-forest")} data-testid={`nav-count-${count}`}>
                        {n}<span className="sr-only"> {count === "billing" ? "ready" : "open"}</span>
                      </span>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );

  const userCard = (
    <div className="mx-3 mt-3 flex items-center gap-2.5 border-t border-white/10 px-1 pt-3">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/15 text-xs font-semibold text-white" aria-hidden>{initials}</span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium text-white">{user.name}</div>
        <div className="text-xs text-white/55">Billing executive</div>
      </div>
      <button type="button" onClick={signOut} aria-label="Sign out" title="Sign out" className="rounded-md p-2 text-white/60 hover:bg-white/10 hover:text-white">
        <LogOut className="h-4 w-4" />
      </button>
    </div>
  );

  const dataPill = counts.demo !== undefined && (
    <span className={cn("inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
      counts.demo ? "bg-amber-50 text-amber-700 ring-[#efdcb4]" : "bg-teal-50 text-teal-700 ring-[#cde5dc]")}
      title={counts.demo ? "Figures come from seeded demo records" : "Figures come from live records"}>
      <span className={cn("h-1.5 w-1.5 rounded-full", counts.demo ? "bg-amber" : "bg-teal")} aria-hidden />{counts.demo ? "Demo data" : "Live data"}
    </span>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[232px_minmax(0,1fr)]">
      <aside className="hidden flex-col bg-forest pb-3 pt-4 lg:sticky lg:top-0 lg:flex lg:h-screen">
        <Logo light className="mb-6 px-5" />
        {nav}
        {userCard}
      </aside>

      <div className="flex min-h-screen min-w-0 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface/95 px-4 backdrop-blur lg:px-8">
          <button type="button" aria-label="Open menu" className="-ml-1 rounded-md p-1.5 text-ink hover:bg-surface-2 lg:hidden" onClick={() => setOpen(true)}><Menu className="h-5 w-5" /></button>
          <span className="truncate text-sm font-semibold text-ink lg:hidden">{current?.label ?? "RouteProof"}</span>
          <QuickFind className="ml-auto hidden w-full max-w-xs sm:block lg:ml-0" />
          <div className="ml-auto flex shrink-0 items-center gap-3">{dataPill}</div>
        </header>
        {open && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 bg-[#0f2420]/45" onClick={() => setOpen(false)} aria-hidden />
            <div className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-forest pb-3 pt-4" role="dialog" aria-modal="true" aria-label="Menu">
              <button type="button" aria-label="Close menu" className="absolute right-3 top-3 rounded-md p-1 text-white/80 hover:bg-white/10" onClick={() => setOpen(false)}><X className="h-5 w-5" /></button>
              <Logo light className="mb-5 px-5" />
              <div className="mb-4 px-3 sm:hidden"><QuickFind /></div>
              {nav}{userCard}
            </div>
          </div>
        )}
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-5 sm:px-6 lg:px-8 lg:py-6">{children}</main>
      </div>
    </div>
  );
}
