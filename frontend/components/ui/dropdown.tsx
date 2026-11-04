"use client";
import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";

export function Dropdown({ label, items, align = "right" }: {
  label: React.ReactNode; align?: "left" | "right";
  items: { label: string; onSelect: () => void; icon?: React.ReactNode; disabled?: boolean }[];
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, []);
  return (
    <div className="relative" ref={ref}>
      <Button variant="outline" size="sm" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {label}<ChevronDown className="h-4 w-4" />
      </Button>
      {open && (
        <div role="menu" className={`absolute z-30 mt-1 min-w-44 rounded-lg border border-line bg-surface p-1 shadow-lg ${align === "right" ? "right-0" : "left-0"}`}>
          {items.map((it) => (
            <button key={it.label} role="menuitem" disabled={it.disabled}
              onClick={() => { setOpen(false); it.onSelect(); }}
              className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-canvas disabled:opacity-40">
              {it.icon}{it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
