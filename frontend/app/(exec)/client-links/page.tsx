"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Kept for old bookmarks: client links are now a tab of the Billing screen. */
export default function ClientLinksRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace("/billing?tab=links"); }, [router]);
  return null;
}
