"use client";
import Link from "next/link";
import { ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { homeFor, useAuth } from "@/lib/auth";

export default function Unauthorized() {
  const { user } = useAuth();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-6 text-center">
      <div className="rounded-full bg-amber-50 p-4"><ShieldAlert className="h-8 w-8 text-amber" /></div>
      <h1 className="text-2xl font-semibold text-forest">You don&apos;t have access to this page</h1>
      <p className="max-w-sm text-sm text-muted">Your role does not permit this area. Permissions are also enforced on the server.</p>
      <Link href={user ? homeFor(user.role) : "/login"}><Button>{user ? "Go to my home" : "Sign in"}</Button></Link>
    </div>
  );
}
