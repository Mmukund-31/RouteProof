"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { BarChart3, ClipboardCheck, FileSpreadsheet, History, LogOut, Menu, PackageSearch, Route, Siren, X } from "lucide-react";
import { Logo } from "@/components/logo";
import { useRequireRole, useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/states";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/trips", label: "Trips", icon: Route },
  { href: "/reviews", label: "Review queue", icon: ClipboardCheck },
  { href: "/billing", label: "Billing queue", icon: FileSpreadsheet },
  { href: "/operations", label: "Missing PODs", icon: Siren },
  { href: "/audit", label: "Audit history", icon: History },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading } = useRequireRole("billing_executive");
  const { logout } = useAuth();
  const path = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  if (loading || !user) {
    return <div className="p-8"><Skeleton className="mb-4 h-8 w-64" /><Skeleton className="h-64 w-full" /></div>;
  }
  const nav = (
    <nav aria-label="Main" className="flex flex-1 flex-col gap-1 px-3">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = path === href || (href !== "/dashboard" && path.startsWith(href));
        return (
          <Link key={href} href={href} onClick={() => setOpen(false)}
            className={cn("flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
              active ? "bg-white/12 text-white" : "text-white/70 hover:bg-white/8 hover:text-white")}>
            <Icon className="h-4 w-4" />{label}
          </Link>
        );
      })}
    </nav>
  );
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[240px_1fr]">
      <aside className="hidden flex-col bg-forest py-5 lg:flex lg:sticky lg:top-0 lg:h-screen">
        <Logo light className="mb-6 px-5" />
        {nav}
        <div className="mx-3 mt-4 rounded-lg bg-white/8 p-3 text-xs text-white/80">
          <div className="flex items-center gap-2 font-medium text-white"><PackageSearch className="h-4 w-4" />{user.name}</div>
          <div className="mt-0.5 text-white/60">Billing executive</div>
          <button onClick={async () => { await logout(); router.replace("/login"); }} className="mt-2 flex items-center gap-1.5 text-white/80 hover:text-white">
            <LogOut className="h-3.5 w-3.5" />Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-h-screen flex-col">
        <header className="flex items-center justify-between border-b border-line bg-surface px-4 py-3 lg:hidden">
          <Logo />
          <button aria-label="Open menu" onClick={() => setOpen(true)}><Menu className="h-6 w-6" /></button>
        </header>
        {open && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
            <div className="absolute inset-y-0 left-0 flex w-64 flex-col bg-forest py-5">
              <button aria-label="Close menu" className="absolute right-3 top-3 text-white" onClick={() => setOpen(false)}><X className="h-5 w-5" /></button>
              <Logo light className="mb-6 px-5" />{nav}
              <button onClick={async () => { await logout(); router.replace("/login"); }} className="m-3 flex items-center gap-2 text-sm text-white/80"><LogOut className="h-4 w-4" />Sign out</button>
            </div>
          </div>
        )}
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 lg:px-8 lg:py-8">{children}</main>
      </div>
    </div>
  );
}
