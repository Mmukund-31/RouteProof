"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { CloudUpload, LogOut, Wifi, WifiOff } from "lucide-react";
import { DriverProvider, useDriver } from "@/hooks/use-driver";
import { useAuth, useRequireRole } from "@/lib/auth";
import { LANGS } from "@/lib/i18n";
import { pendingFor, startAutoSync } from "@/lib/sync";
import { Logo } from "@/components/logo";
import { Skeleton } from "@/components/ui/states";
import { cn } from "@/lib/utils";

function Bar() {
  const { lang, setLang, online, captures, tr } = useDriver();
  const { logout, user } = useAuth();
  const [unsent, setUnsent] = useState<number | null>(null);
  async function doLogout() { await logout(); router.replace("/login"); }
  async function askLogout() {
    // Signing out never deletes captures; warn so the driver knows they are still on the phone.
    const n = await pendingFor(user?.id ?? null).catch(() => 0);
    if (n > 0) setUnsent(n); else await doLogout();
  }
  const router = useRouter();
  const path = usePathname();
  const waiting = captures.filter((c) => c.status !== "UPLOADED").length;
  return (
    <header className="sticky top-0 z-20 bg-forest text-white">
      <div className="mx-auto flex max-w-lg items-center justify-between px-4 py-3">
        <Link href="/driver"><Logo light /></Link>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg bg-white/10 p-0.5" role="group" aria-label="Language">
            {LANGS.map((l) => (
              <button key={l.code} onClick={() => setLang(l.code)} aria-pressed={lang === l.code}
                className={cn("rounded-md px-2.5 py-1.5 text-sm font-medium", lang === l.code ? "bg-white text-forest" : "text-white/80")}>{l.label}</button>
            ))}
          </div>
          <button aria-label={tr("logout")} data-testid="logout" onClick={() => void askLogout()} className="rounded-lg p-2 hover:bg-white/10"><LogOut className="h-5 w-5" /></button>
        </div>
      </div>
      <div role="status" data-testid="net-status" className={cn("flex items-center justify-center gap-2 py-1.5 text-sm font-medium", online ? "bg-teal text-white" : "bg-amber text-forest")}>
        {online ? <Wifi className="h-4 w-4" /> : <WifiOff className="h-4 w-4" />}
        {online ? tr("online") : tr("offline")}
        {waiting > 0 && path !== "/driver/queue" && <Link href="/driver/queue" className="ml-2 rounded-full bg-white/25 px-2 text-xs underline">{waiting} · {tr("queue")}</Link>}
      </div>
      {unsent !== null && (
        <div role="dialog" aria-modal="true" aria-labelledby="unsent-title" data-testid="unsent-dialog" className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-4 sm:items-center">
          <div className="w-full max-w-sm space-y-4 rounded-3xl bg-surface p-6 text-center text-ink">
            <CloudUpload className="mx-auto h-16 w-16 text-[#8a5f12]" />
            <h2 id="unsent-title" className="text-xl font-extrabold text-forest">{tr("pendingLogoutTitle").replace("{n}", String(unsent))}</h2>
            <p className="text-base text-muted">{tr("pendingLogoutText")}</p>
            <div className="grid grid-cols-2 gap-3">
              <button onClick={() => setUnsent(null)} className="h-14 rounded-2xl bg-teal text-lg font-bold text-white">{tr("stay")}</button>
              <button onClick={() => { setUnsent(null); void doLogout(); }} className="h-14 rounded-2xl border-2 border-line text-lg font-bold">{tr("logoutAnyway")}</button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}

export default function DriverLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useRequireRole("driver");
  useEffect(() => (user ? startAutoSync() : undefined), [user]);
  if (loading || !user) return <div className="mx-auto max-w-lg p-6"><Skeleton className="h-10 w-full" /><Skeleton className="mt-4 h-40 w-full" /></div>;
  return (
    <DriverProvider initialLang={user.preferred_language}>
      <div className="min-h-screen bg-canvas">
        <Bar />
        <main className="mx-auto max-w-lg px-4 pb-24 pt-5">{children}</main>
      </div>
    </DriverProvider>
  );
}
