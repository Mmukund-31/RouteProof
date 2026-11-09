import { beforeEach, describe, expect, it, vi } from "vitest";
import { captureDb, type Capture } from "@/lib/offline-db";
import { flushQueue, pendingFor, sendable, setQueueOwner } from "@/lib/sync";
import { ApiError } from "@/lib/api";
import { compressWith, nextAttempt, MAX_UPLOAD_BYTES, withinUploadLimit } from "@/lib/compress";

const cap = (id: string, patch: Partial<Capture> = {}): Capture => ({
  id, tripId: "t1", tripRef: "TRP-1", lr: "LR-1", status: "PENDING", original: new Blob(["original-bytes".repeat(50)]), compressed: new Blob(["small"]),
  originalSize: 700, compressedSize: 5, capturedAt: new Date().toISOString(), retryCount: 0, createdAt: new Date().toISOString(), userId: "u1", ...patch,
});
const ok = (id = "pod-1") => vi.fn().mockResolvedValue({ created: true, pod: { id, verification_status: "UPLOADED" } });
const origOk = () => vi.fn().mockResolvedValue({ attached: true });
const origNet = () => vi.fn().mockRejectedValue(new ApiError(0, "network", "Cannot reach the server"));

beforeEach(async () => {
  for (const c of await captureDb.all()) await captureDb.remove(c.id);
  Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
  setQueueOwner("u1");
});

describe("offline upload queue", () => {
  it("persists original and compressed blobs separately", async () => {
    await captureDb.put(cap("a"));
    const got = (await captureDb.get("a"))!;
    expect(got.original).toBeDefined();
    expect(got.compressed).toBeDefined();
    expect(got.originalSize).toBeGreaterThan(got.compressedSize);
  });

  it("uploads with the capture id as idempotency key; keeps the original until the original itself is acknowledged", async () => {
    await captureDb.put(cap("key-1"));
    const upload = ok();
    const original = origNet();
    await flushQueue(upload, original);
    expect(upload).toHaveBeenCalledOnce();
    expect(upload.mock.calls[0][0].id).toBe("key-1");
    let after = (await captureDb.get("key-1"))!;
    expect(after.status).toBe("UPLOADED");
    expect(after.podId).toBe("pod-1");
    expect(after.compressed).toBeUndefined(); // compressed copy released once the server has it
    expect(after.original).toBeDefined(); // original NOT released: its own upload failed
    expect(after.originalStatus).toBe("PENDING");
    const original2 = origOk();
    await flushQueue(upload, original2);
    expect(upload).toHaveBeenCalledOnce(); // the compressed copy is never sent twice
    expect(original2.mock.calls[0][0].podId).toBe("pod-1");
    after = (await captureDb.get("key-1"))!;
    expect(after.original).toBeUndefined();
    expect(after.originalStatus).toBe("UPLOADED");
  });

  it("stops retrying an original after a permanent error but keeps it on the phone", async () => {
    await captureDb.put(cap("key-o", { status: "UPLOADED", podId: "p", compressed: undefined, originalStatus: "PENDING" }));
    const bad = vi.fn().mockRejectedValue(new ApiError(413, "file_too_large", "too big"));
    await flushQueue(ok(), bad);
    await flushQueue(ok(), bad);
    expect(bad).toHaveBeenCalledOnce();
    const c = (await captureDb.get("key-o"))!;
    expect(c.originalStatus).toBe("FAILED");
    expect(c.original).toBeDefined();
  });

  it("keeps the original and retries with the SAME key after a network failure (incl. a lost response)", async () => {
    await captureDb.put(cap("key-2"));
    const net = vi.fn().mockRejectedValue(new ApiError(0, "network", "Cannot reach the server"));
    await flushQueue(net, origOk());
    let c = (await captureDb.get("key-2"))!;
    expect(c.status).toBe("PENDING");
    expect(c.retryCount).toBe(1);
    expect(c.original).toBeDefined();
    // The server had stored it; it answers the retry with the same POD (created: false).
    const again = vi.fn().mockResolvedValue({ created: false, pod: { id: "pod-9", verification_status: "UPLOADED" } });
    await flushQueue(again, origOk());
    expect(again.mock.calls[0][0].id).toBe("key-2");
    c = (await captureDb.get("key-2"))!;
    expect(c.status).toBe("UPLOADED");
    expect(c.podId).toBe("pod-9");
  });

  it("escalates to RETRY_REQUIRED after repeated transient failures (e.g. server timeouts)", async () => {
    await captureDb.put(cap("key-3", { retryCount: 2 }));
    await flushQueue(vi.fn().mockRejectedValue(new ApiError(0, "network", "aborted after timeout")), origOk());
    expect((await captureDb.get("key-3"))!.status).toBe("RETRY_REQUIRED");
  });

  it("marks permanent client errors FAILED without hammering the server", async () => {
    await captureDb.put(cap("key-4"));
    const up = vi.fn().mockRejectedValue(new ApiError(415, "unsupported_image", "File is not a valid JPEG, PNG or WebP image"));
    await flushQueue(up, origOk());
    const c = (await captureDb.get("key-4"))!;
    expect(c.status).toBe("FAILED");
    expect(c.lastError).toContain("valid JPEG");
    await flushQueue(up, origOk());
    expect(up).toHaveBeenCalledOnce();
  });

  it("two queued photos for one trip: the first wins, the second is refused cleanly", async () => {
    await captureDb.put(cap("k-a", { createdAt: "2026-11-01T10:00:00Z" }));
    await captureDb.put(cap("k-b", { createdAt: "2026-11-01T10:05:00Z" }));
    const up = vi.fn()
      .mockResolvedValueOnce({ created: true, pod: { id: "pa", verification_status: "UPLOADED" } })
      .mockRejectedValueOnce(new ApiError(409, "pod_in_progress", "A POD for this trip is already UPLOADED"));
    await flushQueue(up, origOk());
    expect(up.mock.calls.map((c) => c[0].id)).toEqual(["k-a", "k-b"]); // oldest first
    expect((await captureDb.get("k-a"))!.status).toBe("UPLOADED");
    const b = (await captureDb.get("k-b"))!;
    expect(b.status).toBe("FAILED");
    expect(b.original).toBeDefined(); // never thrown away silently
  });

  it("an expired session pauses the queue without losing anything", async () => {
    await captureDb.put(cap("key-401", { createdAt: "2026-11-01T10:00:00Z" }));
    await captureDb.put(cap("key-401b", { createdAt: "2026-11-01T10:05:00Z" }));
    const up = vi.fn().mockRejectedValue(new ApiError(401, "invalid_token", "expired"));
    await flushQueue(up, origOk());
    expect(up).toHaveBeenCalledOnce(); // stops at the first 401
    const c = (await captureDb.get("key-401"))!;
    expect(c.status).toBe("RETRY_REQUIRED");
    expect(c.compressed && c.original).toBeTruthy();
    expect((await captureDb.get("key-401b"))!.status).toBe("PENDING"); // not attempted, still queued
  });

  it("after sign-out, captures stay on the phone and are only sent for the driver who took them", async () => {
    await captureDb.put(cap("mine", { userId: "u1" }));
    await captureDb.put(cap("theirs", { userId: "u2" }));
    await captureDb.put(cap("link", { userId: undefined, linkToken: "tok" }));
    setQueueOwner(null);
    const up = ok();
    await flushQueue(up, origOk());
    expect(up.mock.calls.map((c) => c[0].id)).toEqual(["link"]); // hired-driver link captures carry their own credential
    expect(await pendingFor("u1")).toBe(1);
    setQueueOwner("u1");
    await flushQueue(up, origOk());
    expect(up.mock.calls.map((c) => c[0].id)).toEqual(["link", "mine"]);
    expect((await captureDb.get("theirs"))!.status).toBe("PENDING");
    expect(sendable(cap("x", { userId: "u2" }), "u1")).toBe(false);
  });

  it("does nothing while offline and drains when back online", async () => {
    await captureDb.put(cap("key-5"));
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    const up = ok("p");
    await flushQueue(up, origOk());
    expect(up).not.toHaveBeenCalled();
    expect((await captureDb.get("key-5"))!.status).toBe("PENDING");
    Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
    await flushQueue(up, origOk());
    expect(up).toHaveBeenCalledOnce();
  });

  it("never runs two flushes concurrently (no duplicate uploads)", async () => {
    await captureDb.put(cap("key-6"));
    let resolve!: (v: unknown) => void;
    const up = vi.fn().mockImplementation(() => new Promise((r) => { resolve = r; }));
    const a = flushQueue(up, origOk());
    const b = flushQueue(up, origOk());
    await new Promise((r) => setTimeout(r, 20));
    resolve({ created: true, pod: { id: "p", verification_status: "UPLOADED" } });
    await Promise.all([a, b]);
    expect(up).toHaveBeenCalledTimes(1);
  });
});

describe("compression policy (strictly under 300 KB)", () => {
  const KB = 1024;
  it.each([[100, true], [299, true], [300, false], [301, false]])("%i KB is within the limit: %s", (kb, within) => {
    expect(withinUploadLimit(kb * KB)).toBe(within);
  });

  it("the boundary is 307,199 bytes accepted, 307,200 refused", () => {
    expect(MAX_UPLOAD_BYTES).toBe(300 * KB);
    expect(withinUploadLimit(300 * KB - 1)).toBe(true);
    expect(withinUploadLimit(300 * KB)).toBe(false);
  });

  it("checks the actual blob size and retries at lower quality, then lower resolution", async () => {
    const sizes = [420, 360, 301, 300, 299]; // KB per successive attempt
    const calls: [number, number][] = [];
    const r = await compressWith(async (dim, q) => { calls.push([dim, q]); return new Blob([new Uint8Array(sizes[calls.length - 1] * KB)]); });
    expect(r.withinLimit).toBe(true);
    expect(r.blob.size).toBe(299 * KB); // 300 KB exactly was NOT accepted
    expect(r.attempts).toBe(5);
    expect(calls[1][1]).toBeLessThan(calls[0][1]); // quality first
    expect(calls.some(([dim]) => dim < 1600)).toBe(true); // then resolution
  });

  it("accepts the first result that is already small enough", async () => {
    const r = await compressWith(async () => new Blob([new Uint8Array(100 * KB)]));
    expect(r).toMatchObject({ withinLimit: true, attempts: 1 });
  });

  it("when it cannot get under the limit it returns the smallest result, flagged, instead of failing", async () => {
    const r = await compressWith(async (dim) => new Blob([new Uint8Array((dim >= 1000 ? 900 : 400) * KB)]));
    expect(r.withinLimit).toBe(false);
    expect(r.blob.size).toBe(400 * KB);
  });

  it("an encoder failure moves on to the next setting", async () => {
    let n = 0;
    const r = await compressWith(async () => { n++; if (n === 1) throw new Error("encode failed"); return new Blob([new Uint8Array(50 * KB)]); });
    expect(r).toMatchObject({ withinLimit: true, attempts: 2 });
  });

  it("lowers quality first, then dimensions, then one last low-quality pass, and eventually gives up", () => {
    let step: { dim: number; quality: number } | null = { dim: 1600, quality: 0.8 };
    let n = 0;
    while (step && n < 30) { const nx = nextAttempt(step.dim, step.quality); if (!nx) break; step = nx; n++; }
    expect(n).toBeGreaterThan(3);
    expect(step!.dim).toBeGreaterThanOrEqual(640); // never shrinks below legibility
    expect(nextAttempt(700, 0.5)).toEqual({ dim: 700, quality: 0.4 });
    expect(nextAttempt(700, 0.4)).toBeNull();
  });
});
