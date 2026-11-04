"use client";
import { useEffect, useState } from "react";
import { ZoomIn, ZoomOut, RotateCw, Maximize2, ImageOff } from "lucide-react";
import { blob } from "@/lib/api";
import { Skeleton } from "@/components/ui/states";

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

export function ImageViewer({ path, alt }: { path: string; alt: string }) {
  const { src, error } = useAuthImage(path);
  const [zoom, setZoom] = useState(1);
  const [rot, setRot] = useState(0);
  if (error) return <div className="flex h-96 flex-col items-center justify-center gap-2 text-sm text-muted"><ImageOff className="h-8 w-8" />Original image could not be loaded</div>;
  if (!src) return <Skeleton className="h-96 w-full" />;
  const btn = "rounded-md bg-white/90 p-1.5 text-ink shadow hover:bg-white";
  return (
    <div className="relative">
      <div className="absolute right-2 top-2 z-10 flex gap-1" role="toolbar" aria-label="Image controls">
        <button className={btn} aria-label="Zoom in" onClick={() => setZoom((z) => Math.min(z + 0.5, 4))}><ZoomIn className="h-4 w-4" /></button>
        <button className={btn} aria-label="Zoom out" onClick={() => setZoom((z) => Math.max(z - 0.5, 1))}><ZoomOut className="h-4 w-4" /></button>
        <button className={btn} aria-label="Rotate" onClick={() => setRot((r) => (r + 90) % 360)}><RotateCw className="h-4 w-4" /></button>
        <button className={btn} aria-label="Reset view" onClick={() => { setZoom(1); setRot(0); }}><Maximize2 className="h-4 w-4" /></button>
      </div>
      <div className="max-h-[70vh] overflow-auto rounded-lg bg-[#2b2f2e]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt} style={{ width: `${zoom * 100}%`, maxWidth: "none", transform: `rotate(${rot}deg)`, transformOrigin: "center" }} className="mx-auto block" />
      </div>
    </div>
  );
}
