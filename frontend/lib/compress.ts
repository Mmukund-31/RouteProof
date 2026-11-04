export const MAX_UPLOAD_BYTES = 300 * 1024;

/** Pure helper (unit-tested): choose the next (maxDimension, quality) attempt when the result is still too big. */
export function nextAttempt(dim: number, quality: number): { dim: number; quality: number } | null {
  if (quality > 0.5) return { dim, quality: Math.round((quality - 0.1) * 100) / 100 };
  if (dim > 700) return { dim: Math.round(dim * 0.8), quality: 0.7 };
  return null;
}

function toBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob> {
  return new Promise((res, rej) => canvas.toBlob((b) => (b ? res(b) : rej(new Error("encode failed"))), "image/jpeg", quality));
}

/**
 * Compresses a captured photo to < 300 KB JPEG. The ORIGINAL file is never modified; the caller keeps it
 * separately until the server acknowledges the upload.
 */
export async function compressImage(file: Blob, limit = MAX_UPLOAD_BYTES): Promise<Blob> {
  const bmp = await createImageBitmap(file);
  let dim = 1600, quality = 0.8;
  for (let i = 0; i < 20; i++) {
    const scale = Math.min(1, dim / Math.max(bmp.width, bmp.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * scale);
    canvas.height = Math.round(bmp.height * scale);
    canvas.getContext("2d")!.drawImage(bmp, 0, 0, canvas.width, canvas.height);
    const out = await toBlob(canvas, quality);
    if (out.size < limit) { bmp.close?.(); return out; }
    const n = nextAttempt(dim, quality);
    if (!n) { bmp.close?.(); return out; }
    dim = n.dim; quality = n.quality;
  }
  bmp.close?.();
  throw new Error("Could not compress image under limit");
}
