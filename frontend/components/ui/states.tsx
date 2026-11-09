import { AlertCircle, Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-[#e7ece8]", className)} aria-hidden />;
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

export function EmptyState({ title, text, action, icon: Icon = Inbox, compact }: {
  title: string; text?: React.ReactNode; action?: React.ReactNode; icon?: React.ElementType; compact?: boolean;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 text-center", compact ? "py-8" : "py-14")}>
      <div className="mb-3 rounded-lg bg-surface-2 p-2.5 ring-1 ring-line"><Icon className="h-5 w-5 text-muted" aria-hidden /></div>
      <p className="text-sm font-medium text-ink">{title}</p>
      {text && <p className="mt-1 max-w-sm text-[13px] text-muted">{text}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="mb-3 rounded-lg bg-danger-50 p-2.5"><AlertCircle className="h-5 w-5 text-danger" aria-hidden /></div>
      <p className="text-sm font-medium text-ink">Something went wrong</p>
      <p className="mt-1 max-w-sm text-[13px] text-muted">{message}</p>
      {onRetry && <Button className="mt-4" variant="outline" size="sm" onClick={onRetry}>Try again</Button>}
    </div>
  );
}
