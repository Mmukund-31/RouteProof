import { forwardRef } from "react";
import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

const field = "w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink shadow-[0_1px_1px_rgba(23,51,46,0.03)] transition-[border-color,box-shadow] placeholder:text-neutral hover:border-[#cbd5cf] focus:border-teal focus:outline-none focus:ring-3 focus:ring-teal/15 disabled:bg-canvas disabled:text-muted aria-[invalid=true]:border-danger aria-[invalid=true]:ring-danger/15";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...p }, ref) {
  return <input ref={ref} className={cn(field, "h-9", className)} {...p} />;
});

export const Select = forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, children, ...p }, ref) {
  return <select ref={ref} className={cn(field, "h-9 pr-8", className)} {...p}>{children}</select>;
});

export const Textarea = forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...p }, ref) {
  return <textarea ref={ref} className={cn(field, "min-h-20 py-2", className)} {...p} />;
});

/** Search box with a leading icon and a clear button. `label` is the accessible name. */
export function SearchInput({ value, onChange, label, placeholder, className }: {
  value: string; onChange: (v: string) => void; label: string; placeholder?: string; className?: string;
}) {
  return (
    <div className={cn("relative min-w-0", className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral" aria-hidden />
      <input type="search" aria-label={label} placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)}
        className={cn(field, "h-9 pl-9 pr-8 [&::-webkit-search-cancel-button]:hidden")} />
      {value && (
        <button type="button" aria-label="Clear search" onClick={() => onChange("")}
          className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-neutral hover:bg-surface-2 hover:text-ink">
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

export function Label({ children, htmlFor, hint }: { children: React.ReactNode; htmlFor?: string; hint?: string }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-[13px] font-medium text-ink">
      {children}{hint && <span className="ml-1 font-normal text-muted">{hint}</span>}
    </label>
  );
}

/** Field-level error text, linked to its input via aria-describedby. */
export function FieldError({ id, children }: { id: string; children?: React.ReactNode }) {
  if (!children) return null;
  return <p id={id} className="mt-1.5 text-xs font-medium text-danger-700">{children}</p>;
}
