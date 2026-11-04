import Link from "next/link";
import { MapPinOff } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-6 text-center">
      <div className="rounded-full bg-teal-50 p-4"><MapPinOff className="h-8 w-8 text-teal" /></div>
      <h1 className="text-2xl font-semibold text-forest">Page not found</h1>
      <p className="max-w-sm text-sm text-muted">The page you are looking for does not exist or has moved.</p>
      <Link href="/" className="rounded-lg bg-forest px-4 py-2 text-sm font-medium text-white">Back to RouteProof</Link>
    </div>
  );
}
