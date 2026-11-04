const TZ = "Asia/Kolkata";

export const inr = (v: string | number | null | undefined) =>
  v === null || v === undefined || v === "" ? "—" : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(v));

export const inrCompact = (v: number) =>
  v >= 1e7 ? `₹${(v / 1e7).toFixed(2)} Cr` : v >= 1e5 ? `₹${(v / 1e5).toFixed(1)} L` : inr(v);

/** Timestamps are stored in UTC and rendered in IST. */
export const dt = (iso: string | null | undefined) =>
  iso ? new Intl.DateTimeFormat("en-IN", { timeZone: TZ, day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(iso)) : "—";

export const d = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const date = iso.length === 10 ? new Date(iso + "T00:00:00") : new Date(iso);
  return new Intl.DateTimeFormat("en-IN", { timeZone: iso.length === 10 ? undefined : TZ, day: "2-digit", month: "short", year: "numeric" }).format(date);
};

export const pct = (v: number) => `${Math.round(v * 100)}%`;
export const hours = (h: number | null) => (h === null ? "—" : h >= 48 ? `${(h / 24).toFixed(1)} d` : `${h.toFixed(1)} h`);
export const humanize = (s: string) => s.toLowerCase().replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
