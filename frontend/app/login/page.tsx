"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Camera, LayoutDashboard, ShieldCheck } from "lucide-react";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { homeFor, useAuth } from "@/lib/auth";

const DEMO = [
  { label: "Billing executive", email: "billing@routeproof.demo", icon: LayoutDashboard },
  { label: "Driver", email: "driver1@routeproof.demo", icon: Camera },
];

export default function LoginPage() {
  const { user, login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (user) router.replace(homeFor(user.role)); }, [user, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const u = await login(email.trim(), password);
      router.replace(homeFor(u.role));
    } catch (err) {
      setError((err as Error).message);
    } finally { setBusy(false); }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="hidden flex-col justify-between bg-forest p-12 text-white lg:flex">
        <Logo light />
        <div>
          <h1 className="max-w-md text-4xl font-semibold leading-tight tracking-tight">From delivery to billing-ready, with the document as the source of truth.</h1>
          <ul className="mt-8 space-y-3 text-white/80">
            <li className="flex items-center gap-3"><Camera className="h-5 w-5 text-amber" />Drivers capture the POD, even without signal</li>
            <li className="flex items-center gap-3"><ShieldCheck className="h-5 w-5 text-amber" />AI reads it; people decide the exceptions</li>
            <li className="flex items-center gap-3"><LayoutDashboard className="h-5 w-5 text-amber" />Only verified trips reach the billing queue</li>
          </ul>
        </div>
        <p className="text-xs text-white/50">Demo environment · all data is fictional</p>
      </div>
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <Logo className="mb-8 lg:hidden" />
          <h2 className="text-2xl font-semibold text-forest">Sign in</h2>
          <p className="mt-1 text-sm text-muted">Use your RouteProof account.</p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <div><Label htmlFor="email">Email</Label><Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
            <div><Label htmlFor="password">Password</Label><Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></div>
            {error && <p role="alert" className="rounded-lg bg-danger-50 px-3 py-2 text-sm text-danger">{error}</p>}
            <Button type="submit" className="w-full" size="lg" loading={busy}>Sign in</Button>
          </form>
          <div className="mt-8 rounded-xl border border-line bg-surface p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted">Demo accounts (non-production)</p>
            <div className="mt-3 grid gap-2">
              {DEMO.map(({ label, email: em, icon: Icon }) => (
                <button key={em} type="button" onClick={() => { setEmail(em); setPassword("Demo@12345"); }}
                  className="flex items-center gap-3 rounded-lg border border-line px-3 py-2 text-left text-sm hover:bg-canvas">
                  <Icon className="h-4 w-4 text-teal" /><span className="font-medium">{label}</span><span className="ml-auto text-xs text-muted">Fill</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
