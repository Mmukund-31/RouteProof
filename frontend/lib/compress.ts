/**
 * Upload-size policy: the compressed POD a phone uploads must be STRICTLY UNDER 300 KB (300 × 1024 = 307,200 bytes).
 * 307,199 bytes is accepted; 307,200 is not. The server applies the same rule and flags (never drops) anything at or
 * above it, so evidence is not lost on a phone that cannot compress enough.
 */
export const MAX_UPLOAD_BYTES = 300 * 1024;

export const withinUploadLimit = (bytes: number, limit = MAX_UPLOAD_BYTES) => bytes < limit;

/** Below this the document text stops being reliably legible, so we stop shrinking and flag instead. */
export const MIN_DIMENSION = 640;
export const MIN_QUALITY = 0.4;

/** Pure helper (unit-tested): choose the next (maxDimension, quality) attempt when the result is still too big.
 * Order: lower JPEG quality, then lower resolution, then one last-resort low-quality pass, then give up. */
export function nextAttempt(dim: number, quality: number): { dim: number; quality: number } | null {
  if (quality > 0.5) return { dim, quality: Math.round((quality - 0.1) * 100) / 100 };
  if (dim > 700) return { dim: Math.max(MIN_DIMENSION, Math.round(dim * 0.8)), quality: 0.7 };
  if (quality > MIN_QUALITY) return { dim, quality: MIN_QUALITY };
  return null;
}

export interface CompressResult {
  blob: Blob;
  /** True when the blob is strictly under the limit. False: best effort, still uploaded, flagged by the server. */
  withinLimit: boolean;
  attempts: number;
  dim: number;
  quality: number;
}

/** Encoder-agnostic loop (unit-tested with a fake encoder): checks the ACTUAL blob size after every attempt. */
export async function compressWith(encode: (dim: number, quality: number) => Promise<Blob>, limit = MAX_UPLOAD_BYTES,
  start = { dim: 1600, quality: 0.8 }): Promise<CompressResult> {
  let { dim, quality } = start;
  let best: Blob | null = null;
  for (let attempt = 1; attempt <= 20; attempt++) {
    let out: Blob;
    try { out = await encode(dim, quality); }
    catch { out = new Blob(); } // a failed encode is treated as unusable and we move to the next setting
    if (out.size > 0 && (!best || out.size < best.size)) best = out;
    if (out.size > 0 && withinUploadLimit(out.size, limit)) return { blob: out, withinLimit: true, attempts: attempt, dim, quality };
    const n = nextAttempt(dim, quality);
    if (!n) {
      if (!best) throw new Error("Could not encode this photo");
      return { blob: best, withinLimit: withinUploadLimit(best.size, limit), attempts: attempt, dim, quality };
    }
    dim = n.dim; quality = n.quality;
  }
  if (!best) throw new Error("Could not encode this photo");
  return { blob: best, withinLimit: withinUploadLimit(best.size, limit), attempts: 20, dim, quality };
}

function toBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob> {
  return new Promise((res, rej) => canvas.toBlob((b) => (b ? res(b) : rej(new Error("encode failed"))), "image/jpeg", quality));
}

/**
 * Compresses a captured photo for upload. The ORIGINAL file is never modified: the caller keeps it and sends it
 * separately once the compressed copy is acknowledged, so the server never holds only the small copy.
 */
export async function compressImage(file: Blob, limit = MAX_UPLOAD_BYTES): Promise<CompressResult> {
  const bmp = await createImageBitmap(file);
  try {
    return await compressWith(async (dim, quality) => {
      const scale = Math.min(1, dim / Math.max(bmp.width, bmp.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(bmp.width * scale);
      canvas.height = Math.round(bmp.height * scale);
      canvas.getContext("2d")!.drawImage(bmp, 0, 0, canvas.width, canvas.height);
      return toBlob(canvas, quality);
    }, limit);
  } finally { bmp.close?.(); }
}
