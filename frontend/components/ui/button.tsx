import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export const buttonClass = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal",
  {
    variants: {
      variant: {
        primary: "bg-forest text-white shadow-[0_1px_1px_rgba(23,51,46,0.12)] hover:bg-forest-700",
        accent: "bg-teal text-white shadow-[0_1px_1px_rgba(23,51,46,0.12)] hover:bg-teal-700",
        outline: "border border-line bg-surface text-ink shadow-[0_1px_1px_rgba(23,51,46,0.04)] hover:border-[#cfd8d2] hover:bg-surface-2",
        ghost: "text-ink hover:bg-forest-50",
        danger: "bg-danger text-white hover:bg-danger-700",
        "danger-outline": "border border-[#ecc9c9] bg-surface text-danger-700 hover:bg-danger-50",
        warn: "bg-amber text-forest hover:bg-[#c58b2c]",
        link: "h-auto px-0 text-teal-700 hover:underline",
      },
      size: { xs: "h-7 px-2.5 text-xs", sm: "h-8 px-3 text-[13px]", md: "h-9 px-3.5 text-sm", lg: "h-11 px-5 text-[15px]", xl: "h-16 px-6 text-lg" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonClass> {
  loading?: boolean;
}

export function Button({ className, variant, size, loading, children, disabled, type = "button", ...p }: ButtonProps) {
  return (
    <button type={type} className={cn(buttonClass({ variant, size }), className)} disabled={disabled || loading} aria-busy={loading || undefined} {...p}>
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}
