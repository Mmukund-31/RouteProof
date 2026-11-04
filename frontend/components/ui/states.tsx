import { AlertCircle, Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-black/[0.07]", className)} aria-hidden />;
}

export function TableSkeleton({ rows = 6, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-3 p-4" role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4">{Array.from({ length: cols }).map((__, j) => <Skeleton key={j} className="h-5 flex-1" />)}</div>
      ))}
    </div>
  );
}

export function EmptyState({ title, text, action }: { title: string; text?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="mb-3 rounded-full bg-teal-50 p-3"><Inbox className="h-6 w-6 text-teal" /></div>
      <p className="font-medium text-ink">{title}</p>
      {text && <p className="mt-1 max-w-sm text-sm text-muted">{text}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="mb-3 rounded-full bg-danger-50 p-3"><AlertCircle className="h-6 w-6 text-danger" /></div>
      <p className="font-medium text-ink">Something went wrong</p>
      <p className="mt-1 max-w-sm text-sm text-muted">{message}</p>
      {onRetry && <Button className="mt-4" variant="outline" onClick={onRetry}>Try again</Button>}
    </div>
  );
}
