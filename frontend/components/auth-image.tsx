"use client";
import { useEffect, useState } from "react";
import { Expand, ImageOff, Minimize2, RotateCw, ZoomIn, ZoomOut } from "lucide-react";
import { blob } from "@/lib/api";
import { Skeleton } from "@/components/ui/states";
import { cn } from "@/lib/utils";

/** Private images require the bearer token, so we fetch as a blob and show it through an object URL. */
export function useAuthImage(path: string | null) {
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!path) return;
    let url: string | null = null;
    let live = true;
    setSrc(null); setError(false);
    blob(path).then((b) => { if (live) { url = URL.createObjectURL(b); setSrc(url); } }).catch(() => live && setError(true));
    return () => { live = false; if (url) URL.revokeObjectURL(url); };
  }, [path]);
  return { src, error };
}

const ZOOMS = [1, 1.5, 2, 3, 4];

/**
 * Evidence viewer: zoom (buttons, +/- keys), rotate (R), full screen (F, Esc to leave). Zoom widens the image inside a
 * scrolling frame so any corner of the document can be inspected without losing the rest of the page.
 */
export function ImageViewer({ path, alt, height = "h-[min(70vh,640px)]" }: { path: string; alt: string; height?: string }) {
  const { src, error } = useAuthImage(path);
  const [zi, setZi] = useState(0);
  const [rot, setRot] = useState(0);
  const [full, setFull] = useState(false);
  const zoom = ZOOMS[zi];
  const zoomIn = () => setZi((z) => Math.min(z + 1, ZOOMS.length - 1));
  const zoomOut = () => setZi((z) => Math.max(z - 1, 0));
  const reset = () => { setZi(0); setRot(0); };

  useEffect(() => {
    if (!full) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setFull(false); };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; };
  }, [full]);

  if (error) return <div className={cn("flex flex-col items-center justify-center gap-2 rounded-lg bg-surface-2 text-sm text-muted", height)}><ImageOff className="h-8 w-8" aria-hidden />The document image could not be loaded</div>;
  if (!src) return <Skeleton className={cn("w-full", height)} />;

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "+" || e.key === "=") { e.preventDefault(); zoomIn(); }
    else if (e.key === "-") { e.preventDefault(); zoomOut(); }
    else if (e.key === "r" || e.key === "R") setRot((r) => (r + 90) % 360);
    else if (e.key === "0") reset();
    else if (e.key === "f" || e.key === "F") setFull((f) => !f);
  };
  const btn = "inline-flex h-8 w-8 items-center justify-center rounded-md text-white/85 hover:bg-white/15 hover:text-white disabled:opacity-35";
  const toolbar = (
    <div className="flex items-center gap-0.5 rounded-lg bg-[#132a26]/85 p-1 shadow-raised backdrop-blur" role="toolbar" aria-label="Image controls">
      <button type="button" className={btn} aria-label="Zoom out" disabled={zi === 0} onClick={zoomOut}><ZoomOut className="h-4 w-4" /></button>
      <button type="button" className="h-8 min-w-12 rounded-md px-1 text-xs font-medium tabular-nums text-white/85 hover:bg-white/15" aria-label="Reset view" title="Reset view (0)" onClick={reset}>{Math.round(zoom * 100)}%</button>
      <button type="button" className={btn} aria-label="Zoom in" disabled={zi === ZOOMS.length - 1} onClick={zoomIn}><ZoomIn className="h-4 w-4" /></button>
      <span className="mx-0.5 h-5 w-px bg-white/20" aria-hidden />
      <button type="button" className={btn} aria-label="Rotate" title="Rotate (R)" onClick={() => setRot((r) => (r + 90) % 360)}><RotateCw className="h-4 w-4" /></button>
      <button type="button" className={btn} aria-label={full ? "Exit full screen" : "Full screen"} title={full ? "Exit full screen (Esc)" : "Full screen (F)"} onClick={() => setFull((f) => !f)}>
        {full ? <Minimize2 className="h-4 w-4" /> : <Expand className="h-4 w-4" />}
      </button>
    </div>
  );
  const frame = (
    <div tabIndex={0} onKeyDown={onKey} aria-label={`${alt}. Use + and - to zoom, R to rotate, F for full screen.`}
      className={cn("overflow-auto rounded-lg bg-[#1d2725] outline-none focus-visible:ring-2 focus-visible:ring-teal", full ? "h-full" : height)}>
      {/* At 100% the image fits the frame; above that the canvas widens and the frame scrolls. */}
      <div className={cn("flex items-center justify-center p-2", zoom === 1 ? "h-full" : "min-h-full")} style={{ width: `${zoom * 100}%` }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt} draggable={false} style={{ transform: `rotate(${rot}deg)` }}
          className={cn("block max-w-full select-none object-contain transition-transform", zoom === 1 && "max-h-full")} />
      </div>
    </div>
  );

  if (full) {
    return (
      <>
        <Skeleton className={cn("w-full", height)} />
        <div className="fixed inset-0 z-[70] flex flex-col bg-[#0d1614]/95 p-4" role="dialog" aria-modal="true" aria-label={alt}>
          <div className="mb-3 flex items-center justify-between gap-4">
            <p className="truncate text-sm text-white/80">{alt}</p>{toolbar}
          </div>
          <div className="min-h-0 flex-1">{frame}</div>
        </div>
      </>
    );
  }
  return (
    <div className="relative">
      <div className="absolute right-2 top-2 z-10">{toolbar}</div>
      {frame}
    </div>
  );
}
