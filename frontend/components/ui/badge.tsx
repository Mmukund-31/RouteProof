import { AlertTriangle, Camera, CheckCircle2, CircleDashed, Clock, FileCheck2, Loader2, RotateCcw, XCircle, UploadCloud, Receipt } from "lucide-react";
import { cn } from "@/lib/utils";
import { humanize } from "@/lib/format";
import type { ReviewCategory } from "@/types";

/** "blue" is kept as an alias of "info" for older call sites; the palette itself has no blue. */
export type Tone = "neutral" | "green" | "teal" | "amber" | "red" | "info" | "blue";
const tones: Record<Tone, string> = {
  neutral: "bg-[#f0f3f1] text-[#55635e] ring-[#e0e6e1]",
  green: "bg-teal-50 text-teal-700 ring-[#cde5dc]",
  teal: "bg-teal-50 text-teal-700 ring-[#cde5dc]",
  amber: "bg-amber-50 text-amber-700 ring-[#efdcb4]",
  red: "bg-danger-50 text-danger-700 ring-[#f0d2d2]",
  info: "bg-forest-50 text-forest ring-[#d3e0db]",
  blue: "bg-forest-50 text-forest ring-[#d3e0db]",
};
export const DOT_TONE: Record<Tone, string> = {
  neutral: "bg-neutral", green: "bg-teal", teal: "bg-teal", amber: "bg-amber", red: "bg-danger", info: "bg-forest", blue: "bg-forest",
};

export function Badge({ tone = "neutral", className, children, icon, title }: { tone?: Tone; className?: string; children: React.ReactNode; icon?: React.ReactNode; title?: string }) {
  return (
    <span title={title} className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset", tones[tone], className)}>
      {icon}{children}
    </span>
  );
}

const ic = "h-3.5 w-3.5";
/**
 * The single source of POD status wording and colour. Every screen uses these labels, so a record never reads
 * "Pending" in one place and "No POD" in another.
 */
export const POD_STATUS: Record<string, { tone: Tone; label: string; icon: React.ReactNode; hint: string }> = {
  PENDING: { tone: "neutral", label: "Awaiting POD", icon: <CircleDashed className={ic} />, hint: "No proof of delivery uploaded yet" },
  UPLOADED: { tone: "info", label: "Uploaded", icon: <UploadCloud className={ic} />, hint: "Received; waiting for AI extraction" },
  AI_PROCESSING: { tone: "info", label: "Processing", icon: <Loader2 className={cn(ic, "animate-spin")} />, hint: "AI is reading the document" },
  NEEDS_REVIEW: { tone: "amber", label: "Needs review", icon: <AlertTriangle className={ic} />, hint: "A person must decide" },
  RETAKE_REQUESTED: { tone: "amber", label: "Retake requested", icon: <RotateCcw className={ic} />, hint: "Waiting for the driver to re-capture" },
  VERIFIED: { tone: "green", label: "Verified", icon: <CheckCircle2 className={ic} />, hint: "POD accepted" },
  REJECTED: { tone: "red", label: "Rejected", icon: <XCircle className={ic} />, hint: "POD rejected; a new attempt is needed" },
};
export const BILLING_STATUS: Record<string, { tone: Tone; label: string; icon: React.ReactNode }> = {
  NOT_READY: { tone: "neutral", label: "Not ready", icon: <Clock className={ic} /> },
  BILLING_READY: { tone: "green", label: "Billing ready", icon: <FileCheck2 className={ic} /> },
  EXPORTED: { tone: "info", label: "Exported", icon: <Receipt className={ic} /> },
  INVOICED: { tone: "info", label: "Invoiced (manual)", icon: <Receipt className={ic} /> },
};

export function PodBadge({ status }: { status: string }) {
  const s = POD_STATUS[status] ?? { tone: "neutral" as Tone, label: humanize(status), icon: <Camera className={ic} />, hint: "" };
  return <Badge tone={s.tone} icon={s.icon} title={s.hint}>{s.label}</Badge>;
}
export function BillingBadge({ status }: { status?: string }) {
  if (!status) return null;
  const s = BILLING_STATUS[status] ?? { tone: "neutral" as Tone, label: humanize(status), icon: null };
  return <Badge tone={s.tone} icon={s.icon}>{s.label}</Badge>;
}
export function PriorityBadge({ p }: { p: string | null }) {
  if (!p) return null;
  const tone: Tone = p === "high" ? "red" : p === "medium" ? "amber" : "neutral";
  return (
    <Badge tone={tone} icon={<span className={cn("h-1.5 w-1.5 rounded-full", DOT_TONE[tone])} aria-hidden />}>{humanize(p)} priority</Badge>
  );
}

export const REASON_LABELS: Record<string, string> = {
  AI_ERROR: "System error (AI)", PROCESSING_STALLED: "Processing stalled", LR_MISMATCH: "LR number mismatch",
  CONSIGNEE_MISMATCH: "Consignee mismatch", SHORTAGE: "Shortage remark", DAMAGE: "Damage remark", QUANTITY_MISMATCH: "Quantity differs",
  LOW_CONFIDENCE: "Low confidence", QUANTITY_UNREADABLE: "Quantity not readable", DATE_IMPLAUSIBLE: "Implausible date",
  DATE_DIFFERS_FROM_TRIP: "Date differs from trip record",
  MISSING_FIELD: "Missing field", UNREADABLE: "Unreadable document", STAMP_NOT_VISIBLE: "Stamp not visible",
  SIGNATURE_NOT_VISIBLE: "Signature not visible", RETAKE_LIMIT_REACHED: "Retake limit reached",
};

/** Which POD field each reason concerns, so exception lists can say what is affected rather than only why. */
export const REASON_FIELDS: Record<string, string[]> = {
  LR_MISMATCH: ["LR number"], CONSIGNEE_MISMATCH: ["Consignee"], SHORTAGE: ["Remarks", "Delivered quantity"],
  DAMAGE: ["Remarks"], QUANTITY_MISMATCH: ["Delivered quantity"], QUANTITY_UNREADABLE: ["Delivered quantity"],
  DATE_IMPLAUSIBLE: ["Delivery date"], DATE_DIFFERS_FROM_TRIP: ["Delivery date"], STAMP_NOT_VISIBLE: ["Consignee stamp"],
  SIGNATURE_NOT_VISIBLE: ["Signature"], UNREADABLE: ["Whole document"], LOW_CONFIDENCE: ["Low-confidence fields"],
  MISSING_FIELD: ["Required fields"],
};
export const affectedFields = (reasons: string[]) => [...new Set(reasons.flatMap((r) => REASON_FIELDS[r] ?? []))];

/** Mirrors the backend categories: system failure vs. unreadable document vs. a real business exception. */
export const REASON_CATEGORY: Record<string, ReviewCategory> = {
  AI_ERROR: "system", PROCESSING_STALLED: "system",
  LR_MISMATCH: "business", CONSIGNEE_MISMATCH: "business", SHORTAGE: "business", DAMAGE: "business",
  QUANTITY_MISMATCH: "business", DATE_IMPLAUSIBLE: "business", DATE_DIFFERS_FROM_TRIP: "business",
};
export const CATEGORY_LABELS: Record<ReviewCategory, string> = {
  system: "System error", document_quality: "Document quality", business: "Business exception",
};
export const CATEGORY_TONE: Record<ReviewCategory, Tone> = { business: "red", document_quality: "amber", system: "info" };
export const reasonCategory = (code: string): ReviewCategory => REASON_CATEGORY[code] ?? "document_quality";

export function ReasonBadge({ code }: { code: string }) {
  const cat = reasonCategory(code);
  return <Badge tone={CATEGORY_TONE[cat]} title={CATEGORY_LABELS[cat]}>{REASON_LABELS[code] ?? humanize(code)}</Badge>;
}
export function CategoryBadge({ c }: { c: ReviewCategory }) {
  return <Badge tone={CATEGORY_TONE[c]}>{CATEGORY_LABELS[c]}</Badge>;
}
