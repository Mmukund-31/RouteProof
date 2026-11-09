"use client";
import { useEffect, useRef, useState } from "react";
import { AlertCircle, Camera, CheckCircle2, MapPin, MapPinOff, Phone, RefreshCw, RotateCcw, Send, Volume2 } from "lucide-react";
import { useDriver } from "@/hooks/use-driver";
import { useAuth } from "@/lib/auth";
import { StateIcon, stateFor, stateLabelKey, type DState } from "@/components/driver/ui";
import { compressImage } from "@/lib/compress";
import { captureDb, type Capture, type LocationStatus } from "@/lib/offline-db";
import { flushQueue, retryCapture } from "@/lib/sync";
import { ERROR_KEY, speak, speechSupported, type I18nKey } from "@/lib/i18n";
import { cn, uuid } from "@/lib/utils";
import type { PodStatus } from "@/types";

interface Props {
  tripId: string; tripRef: string; lr: string; destination: string;
  linkToken?: string;
  podStatus: PodStatus;
  retakesRemaining: number;
  /** Called after a send so the parent can refresh server status. */
  refreshStatus: () => Promise<void> | void;
}
/** "ok" carries real coordinates; every other state says why there are none (sent to the server as location_status). */
type Geo = { state: "ok" | LocationStatus; lat?: number; lon?: number; acc?: number };

const OFFICE_PHONE = process.env.NEXT_PUBLIC_OFFICE_PHONE ?? "";

function getPosition(): Promise<Geo> {
  return new Promise((res) => {
    if (!("geolocation" in navigator)) return res({ state: "unsupported" });
    navigator.geolocation.getCurrentPosition(
      (p) => res({ state: "ok", lat: p.coords.latitude, lon: p.coords.longitude, acc: p.coords.accuracy }),
      (e) => res({ state: e.code === e.PERMISSION_DENIED ? "permission_denied" : e.code === e.TIMEOUT ? "timeout" : "unavailable" }),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 },
    );
  });
}

/** What to say aloud for each outcome: a full instruction in the driver's language, not just a label. */
const SAY: Partial<Record<DState, I18nKey>> = {
  ready: "sayTakePhoto", retake: "sayRetake", verified: "sayVerified", waiting: "sayQueued", queued: "sayUploading",
  uploading: "sayUploading", review: "sayReview", processing: "sayReview", failed: "sayFailed", retryRequired: "sayFailed",
};

/** Big, colour-coded result panel: green = done, amber = act again / wait, red = problem. Icon first, text second. */
const CARD: Partial<Record<DState, string>> = {
  verified: "bg-teal text-white ring-teal", review: "bg-amber-50 text-[#8a5f12] ring-amber/40",
  processing: "bg-[#e8eef7] text-[#2f4f86] ring-[#2f4f86]/20", waiting: "bg-amber-50 text-[#8a5f12] ring-amber/40",
  queued: "bg-[#e8eef7] text-[#2f4f86] ring-[#2f4f86]/20", uploading: "bg-[#e8eef7] text-[#2f4f86] ring-[#2f4f86]/20",
  failed: "bg-danger-50 text-danger ring-danger/30", retryRequired: "bg-danger-50 text-danger ring-danger/30",
};

export function CaptureFlow({ tripId, tripRef, lr, destination, linkToken, podStatus, retakesRemaining, refreshStatus }: Props) {
  const { lang, online, captures, tr } = useDriver();
  const { user } = useAuth();
  const input = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<{ original: File; compressed: Blob; url: string; geo: Geo; capturedAt: string; oversize: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const state = stateFor({ id: tripId, pod_status: podStatus }, captures, online);
  const label = tr(stateLabelKey(state));
  const mine = captures.find((c) => c.tripId === tripId);

  // Poll the server while a document is being checked.
  useEffect(() => {
    if (state !== "processing" && state !== "queued") return;
    const t = setInterval(() => { void refreshStatus(); }, 4000);
    return () => clearInterval(t);
  }, [state, refreshStatus]);

  // Speak the action on arrival and every outcome change (the driver tapped to get here, so speech is allowed).
  const lastSpoken = useRef<string>("");
  useEffect(() => {
    if (pending || lastSpoken.current === state) return;
    lastSpoken.current = state;
    const key = SAY[state];
    if (key) speak(tr(key), lang);
  }, [state, lang, tr, pending]);

  useEffect(() => () => { if (pending) URL.revokeObjectURL(pending.url); }, [pending]);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return; // user cancelled the camera / denied permission: nothing to do
    setError(null); setBusy(true);
    const capturedAt = new Date().toISOString();
    try {
      const [res, geo] = await Promise.all([compressImage(file), getPosition()]);
      setPending({ original: file, compressed: res.blob, url: URL.createObjectURL(res.blob), geo, capturedAt, oversize: !res.withinLimit });
      if (geo.state !== "ok") speak(tr(geo.state === "permission_denied" ? "locationDenied" : "locationUnavailable"), lang);
    } catch {
      setError(tr("errBadPhoto"));
    } finally { setBusy(false); }
  }

  async function send() {
    if (!pending) return;
    setBusy(true);
    const c: Capture = {
      id: uuid(), tripId, tripRef, lr, linkToken, userId: linkToken ? undefined : user?.id, status: "PENDING",
      original: pending.original, compressed: pending.compressed, originalSize: pending.original.size,
      compressedSize: pending.compressed.size, oversize: pending.oversize, capturedAt: pending.capturedAt,
      latitude: pending.geo.lat, longitude: pending.geo.lon, accuracy: pending.geo.acc,
      locationStatus: pending.geo.state === "ok" ? "captured" : pending.geo.state, retryCount: 0, createdAt: new Date().toISOString(),
    };
    try {
      await captureDb.put(c); // persisted locally BEFORE any network call
      setPending(null);
      void flushQueue().then(() => refreshStatus());
    } catch (err) {
      const quota = err instanceof DOMException && err.name === "QuotaExceededError";
      setError(tr(quota ? "errStorage" : "errGeneric"));
    } finally { setBusy(false); }
  }

  const showCamera = !pending && (state === "ready" || state === "retake");
  const failed = state === "failed" || state === "retryRequired";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between rounded-2xl bg-surface px-4 py-3 shadow-sm ring-1 ring-line">
        <div>
          <div className="text-2xl font-extrabold tracking-tight text-forest" data-testid="lr">{lr}</div>
          <div className="text-sm text-muted">{destination} · {tripRef}</div>
        </div>
        {speechSupported() && (
          <button onClick={() => speak(tr(SAY[state] ?? "sayTakePhoto"), lang)} aria-label={tr("listen")} data-testid="listen"
            className="flex h-14 w-14 items-center justify-center rounded-2xl bg-canvas ring-1 ring-line"><Volume2 className="h-7 w-7 text-forest" /></button>
        )}
      </div>

      {pending ? (
        <div className="space-y-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={pending.url} alt="Receipt preview" className="max-h-[36vh] w-full rounded-2xl bg-black/5 object-contain ring-1 ring-line" />
          <div data-testid="gps-status" data-state={pending.geo.state}
            className={cn("flex items-center gap-3 rounded-2xl p-3 text-base font-semibold", pending.geo.state === "ok" ? "bg-teal-50 text-teal" : "bg-amber-50 text-[#8a5f12]")}>
            {pending.geo.state === "ok" ? <MapPin className="h-7 w-7 shrink-0" /> : <MapPinOff className="h-7 w-7 shrink-0" />}
            <span>{pending.geo.state === "ok" ? tr("locationOn") : tr(pending.geo.state === "permission_denied" ? "locationDenied" : "locationUnavailable")}</span>
          </div>
          <div className="flex items-center justify-between px-1 text-sm text-muted">
            <span data-testid="size">{Math.round(pending.compressed.size / 1024)} KB</span>
            {pending.oversize && <span className="font-semibold text-[#8a5f12]" data-testid="oversize">{tr("largePhoto")}</span>}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <button onClick={() => setPending(null)} aria-label={tr("retake")} className="flex h-20 flex-col items-center justify-center gap-1 rounded-2xl border-2 border-amber bg-amber-50 text-base font-bold text-[#8a5f12]"><RotateCcw className="h-8 w-8" />{tr("retake")}</button>
            <button disabled={busy} onClick={send} data-testid="send" aria-label={tr("send")} className="flex h-20 flex-col items-center justify-center gap-1 rounded-2xl bg-teal text-base font-bold text-white disabled:opacity-60"><Send className="h-8 w-8" />{tr("send")}</button>
          </div>
        </div>
      ) : showCamera ? (
        <div className="space-y-3">
          {state === "retake" && retakesRemaining >= 0 && (
            <div className="flex items-center gap-3 rounded-2xl bg-amber p-4 text-forest" role="status" data-testid="retake-banner">
              <RotateCcw className="h-10 w-10 shrink-0" /><span className="text-lg font-extrabold">{tr("retakeRequired")}</span>
            </div>
          )}
          <button type="button" onClick={() => input.current?.click()} disabled={busy} data-testid="camera" aria-label={tr("takePhoto")}
            className={cn("flex h-[52vh] min-h-64 w-full flex-col items-center justify-center gap-4 rounded-3xl text-white shadow-lg active:scale-[0.99] disabled:opacity-70",
              state === "retake" ? "bg-[#8a5f12]" : "bg-forest")}>
            <Camera className="h-28 w-28" strokeWidth={1.5} /><span className="px-4 text-center text-xl font-bold">{busy ? "…" : tr("takePhoto")}</span>
          </button>
          {/* capture="environment" opens the rear camera directly on Android/iOS; no typing anywhere in this flow */}
          <input ref={input} type="file" accept="image/*" capture="environment" className="sr-only" aria-label={tr("takePhoto")} onChange={onFile} data-testid="file" />
          <p className="text-center text-sm text-muted">{tr("photoHint")}</p>
        </div>
      ) : (
        <div className={cn("flex flex-col items-center gap-4 rounded-3xl p-8 text-center shadow-sm ring-1", CARD[state] ?? "bg-surface ring-line")}
          data-testid="status-card" data-state={state}>
          {state === "verified" ? <CheckCircle2 className="h-28 w-28" strokeWidth={1.5} /> : failed ? <AlertCircle className="h-24 w-24" strokeWidth={1.5} /> : <StateIcon state={state} size="lg" />}
          <div className="text-2xl font-extrabold">{state === "verified" ? tr("sentOk") : label}</div>
          {mine && failed && <p className="text-base font-semibold" data-testid="driver-error">{tr(ERROR_KEY[mine.lastErrorKind ?? "generic"])}</p>}
          {failed && mine && (
            <button onClick={() => void retryCapture(mine.id).then(() => refreshStatus())} data-testid="retry"
              className="flex h-16 w-full items-center justify-center gap-2 rounded-2xl bg-forest text-lg font-bold text-white"><RefreshCw className="h-6 w-6" />{tr("retry")}</button>
          )}
          {state === "failed" && !mine?.linkToken && (
            <button onClick={() => input.current?.click()} className="flex h-14 w-full items-center justify-center gap-2 rounded-2xl border-2 border-current text-base font-bold">
              <Camera className="h-6 w-6" />{tr("takePhoto")}
            </button>
          )}
          {(failed || state === "review") && OFFICE_PHONE && (
            <a href={`tel:${OFFICE_PHONE}`} className="flex items-center gap-2 text-base font-semibold underline"><Phone className="h-5 w-5" />{tr("help")}</a>
          )}
          <input ref={input} type="file" accept="image/*" capture="environment" className="sr-only" aria-hidden tabIndex={-1} onChange={onFile} />
        </div>
      )}
      {error && <p role="alert" className="rounded-xl bg-danger-50 p-3 text-center text-danger">{error}</p>}
    </div>
  );
}
