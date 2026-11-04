"use client";
import { useEffect, useRef, useState } from "react";
import { Camera, CheckCircle2, MapPin, MapPinOff, RotateCcw, Send, Volume2 } from "lucide-react";
import { useDriver } from "@/hooks/use-driver";
import { StateIcon, stateFor, stateLabelKey } from "@/components/driver/ui";
import { compressImage } from "@/lib/compress";
import { captureDb, type Capture } from "@/lib/offline-db";
import { flushQueue } from "@/lib/sync";
import { speak, speechSupported } from "@/lib/i18n";
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
type Geo = { state: "pending" | "ok" | "denied" | "unavailable"; lat?: number; lon?: number; acc?: number };

function getPosition(): Promise<Geo> {
  return new Promise((res) => {
    if (!("geolocation" in navigator)) return res({ state: "unavailable" });
    navigator.geolocation.getCurrentPosition(
      (p) => res({ state: "ok", lat: p.coords.latitude, lon: p.coords.longitude, acc: p.coords.accuracy }),
      (e) => res({ state: e.code === e.PERMISSION_DENIED ? "denied" : "unavailable" }),
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 },
    );
  });
}

export function CaptureFlow({ tripId, tripRef, lr, destination, linkToken, podStatus, retakesRemaining, refreshStatus }: Props) {
  const { lang, online, captures, tr } = useDriver();
  const input = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<{ original: File; compressed: Blob; url: string; geo: Geo; capturedAt: string } | null>(null);
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

  // Speak outcome changes (needs a prior user tap, which capture always has).
  const lastSpoken = useRef<string>("");
  useEffect(() => {
    if (state === "ready" || lastSpoken.current === state) return;
    lastSpoken.current = state;
    if (["verified", "retake", "queued", "waiting", "failed"].includes(state)) speak(label, lang);
  }, [state, label, lang]);

  useEffect(() => () => { if (pending) URL.revokeObjectURL(pending.url); }, [pending]);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return; // user cancelled the camera / denied permission: nothing to do
    setError(null); setBusy(true);
    const capturedAt = new Date().toISOString();
    try {
      const [compressed, geo] = await Promise.all([compressImage(file), getPosition()]);
      setPending({ original: file, compressed, url: URL.createObjectURL(compressed), geo, capturedAt });
    } catch {
      setError("Could not read this photo. Please try again.");
    } finally { setBusy(false); }
  }

  async function send() {
    if (!pending) return;
    setBusy(true);
    const c: Capture = {
      id: uuid(), tripId, tripRef, lr, linkToken, status: "PENDING", original: pending.original, compressed: pending.compressed,
      originalSize: pending.original.size, compressedSize: pending.compressed.size, capturedAt: pending.capturedAt,
      latitude: pending.geo.lat, longitude: pending.geo.lon, accuracy: pending.geo.acc, retryCount: 0, createdAt: new Date().toISOString(),
    };
    try {
      await captureDb.put(c); // persisted locally BEFORE any network call
      setPending(null);
      void flushQueue().then(() => refreshStatus());
    } catch { setError("Could not save the photo on this phone. Free some storage and try again."); }
    finally { setBusy(false); }
  }

  const showCamera = !pending && (state === "ready" || state === "retake" || (state === "failed"));
  const canRetake = state === "retake" && retakesRemaining >= 0;

  return (
    <div className="space-y-5">
      <div className="rounded-2xl bg-surface p-4 shadow-sm ring-1 ring-line">
        <div className="text-sm text-muted">{destination}</div>
        <div className="text-3xl font-extrabold tracking-tight text-forest" data-testid="lr">{lr}</div>
        <div className="text-sm text-muted">{tripRef}</div>
      </div>

      {pending ? (
        <div className="space-y-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={pending.url} alt="Receipt preview" className="max-h-[55vh] w-full rounded-2xl object-contain ring-1 ring-line bg-black/5" />
          <div className="flex items-center justify-between text-sm text-muted">
            <span data-testid="size">{Math.round(pending.compressed.size / 1024)} KB</span>
            <span className={cn("flex items-center gap-1", pending.geo.state === "ok" ? "text-teal" : "text-[#8a5f12]")}>
              {pending.geo.state === "ok" ? <MapPin className="h-4 w-4" /> : <MapPinOff className="h-4 w-4" />}
              {pending.geo.state === "ok" ? tr("locationOn") : tr("locationOff")}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <button onClick={() => setPending(null)} className="flex h-16 items-center justify-center gap-2 rounded-2xl border-2 border-amber bg-amber-50 text-lg font-bold text-[#8a5f12]"><RotateCcw className="h-6 w-6" />{tr("retake")}</button>
            <button disabled={busy} onClick={send} data-testid="send" className="flex h-16 items-center justify-center gap-2 rounded-2xl bg-teal text-lg font-bold text-white disabled:opacity-60"><Send className="h-6 w-6" />{tr("send")}</button>
          </div>
        </div>
      ) : showCamera ? (
        <div className="space-y-3">
          {canRetake && <div className="flex items-center gap-3 rounded-2xl bg-amber-50 p-4 text-[#8a5f12]" role="status" data-testid="retake-banner"><RotateCcw className="h-8 w-8" /><span className="text-lg font-bold">{tr("retakeRequired")}</span></div>}
          <button type="button" onClick={() => input.current?.click()} disabled={busy} data-testid="camera"
            className="flex h-44 w-full flex-col items-center justify-center gap-3 rounded-3xl bg-forest text-white shadow-lg active:scale-[0.99] disabled:opacity-70">
            <Camera className="h-16 w-16" /><span className="px-4 text-center text-xl font-bold">{busy ? "…" : tr("takePhoto")}</span>
          </button>
          <input ref={input} type="file" accept="image/*" capture="environment" className="sr-only" aria-label={tr("takePhoto")} onChange={onFile} data-testid="file" />
          <p className="text-center text-sm text-muted">{tr("photoHint")}</p>
          {state === "failed" && mine?.lastError && <p className="text-center text-sm text-danger">{mine.lastError}</p>}
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 rounded-3xl bg-surface p-8 text-center shadow-sm ring-1 ring-line" data-testid="status-card" data-state={state}>
          <StateIcon state={state} size="lg" />
          <div className={cn("text-2xl font-extrabold", state === "verified" ? "text-teal" : "text-forest")}>{label}</div>
          {state === "verified" && <CheckCircle2 className="h-6 w-6 text-teal" />}
          {mine && (mine.status === "FAILED" || mine.status === "RETRY_REQUIRED") && mine.lastError && <p className="text-sm text-danger">{mine.lastError}</p>}
          {speechSupported() && <button onClick={() => speak(label, lang)} className="mt-1 flex items-center gap-2 rounded-xl border border-line px-4 py-2 text-base font-medium"><Volume2 className="h-5 w-5" />{tr("listen")}</button>}
        </div>
      )}
      {error && <p role="alert" className="rounded-xl bg-danger-50 p-3 text-center text-danger">{error}</p>}
    </div>
  );
}
