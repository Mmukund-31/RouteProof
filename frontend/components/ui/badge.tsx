import { AlertTriangle, Camera, CheckCircle2, CircleDashed, Clock, FileCheck2, Loader2, RotateCcw, XCircle, Send, Receipt } from "lucide-react";
import { cn } from "@/lib/utils";
import { humanize } from "@/lib/format";

type Tone = "neutral" | "green" | "teal" | "amber" | "red" | "blue";
const tones: Record<Tone, string> = {
  neutral: "bg-black/5 text-muted",
  green: "bg-teal-50 text-[#1d5c50]",
  teal: "bg-teal-50 text-teal",
  amber: "bg-amber-50 text-[#8a5f12]",
  red: "bg-danger-50 text-danger",
  blue: "bg-[#e8eef7] text-[#2f4f86]",
};

export function Badge({ tone = "neutral", className, children, icon }: { tone?: Tone; className?: string; children: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <span className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium", tones[tone], className)}>
      {icon}{children}
    </span>
  );
}

const ic = "h-3.5 w-3.5";
const POD: Record<string, { tone: Tone; label: string; icon: React.ReactNode }> = {
  PENDING: { tone: "neutral", label: "No POD", icon: <CircleDashed className={ic} /> },
  UPLOADED: { tone: "blue", label: "Uploaded", icon: <Send className={ic} /> },
  AI_PROCESSING: { tone: "blue", label: "Processing", icon: <Loader2 className={cn(ic, "animate-spin")} /> },
  NEEDS_REVIEW: { tone: "amber", label: "Needs review", icon: <AlertTriangle className={ic} /> },
  RETAKE_REQUESTED: { tone: "amber", label: "Retake requested", icon: <RotateCcw className={ic} /> },
  VERIFIED: { tone: "green", label: "Verified", icon: <CheckCircle2 className={ic} /> },
  REJECTED: { tone: "red", label: "Rejected", icon: <XCircle className={ic} /> },
};
const BILL: Record<string, { tone: Tone; label: string; icon: React.ReactNode }> = {
  NOT_READY: { tone: "neutral", label: "Not ready", icon: <Clock className={ic} /> },
  BILLING_READY: { tone: "green", label: "Billing ready", icon: <FileCheck2 className={ic} /> },
  EXPORTED: { tone: "teal", label: "Exported", icon: <Receipt className={ic} /> },
  INVOICED: { tone: "blue", label: "Invoiced (manual)", icon: <Receipt className={ic} /> },
};

export function PodBadge({ status }: { status: string }) {
  const s = POD[status] ?? { tone: "neutral" as Tone, label: humanize(status), icon: <Camera className={ic} /> };
  return <Badge tone={s.tone} icon={s.icon}>{s.label}</Badge>;
}
export function BillingBadge({ status }: { status?: string }) {
  if (!status) return null;
  const s = BILL[status] ?? { tone: "neutral" as Tone, label: humanize(status), icon: null };
  return <Badge tone={s.tone} icon={s.icon}>{s.label}</Badge>;
}
export function PriorityBadge({ p }: { p: string | null }) {
  if (!p) return null;
  return <Badge tone={p === "high" ? "red" : p === "medium" ? "amber" : "neutral"}>{humanize(p)} priority</Badge>;
}

export const REASON_LABELS: Record<string, string> = {
  AI_ERROR: "AI processing error", LR_MISMATCH: "LR number mismatch", CONSIGNEE_MISMATCH: "Consignee mismatch", SHORTAGE: "Shortage remark",
  DAMAGE: "Damage remark", QUANTITY_MISMATCH: "Quantity differs", LOW_CONFIDENCE: "Low confidence", DATE_IMPLAUSIBLE: "Implausible date",
  MISSING_FIELD: "Missing field", UNREADABLE: "Unreadable document", STAMP_NOT_VISIBLE: "Stamp not visible",
  SIGNATURE_NOT_VISIBLE: "Signature not visible", RETAKE_LIMIT_REACHED: "Retake limit reached",
};
export function ReasonBadge({ code }: { code: string }) {
  const bad = ["SHORTAGE", "DAMAGE", "LR_MISMATCH", "CONSIGNEE_MISMATCH", "QUANTITY_MISMATCH"].includes(code);
  return <Badge tone={bad ? "red" : "amber"}>{REASON_LABELS[code] ?? humanize(code)}</Badge>;
}
