import { beforeEach, describe, expect, it, vi } from "vitest";
import { captureDb, type Capture } from "@/lib/offline-db";
import { flushQueue } from "@/lib/sync";
import { ApiError } from "@/lib/api";
import { nextAttempt, MAX_UPLOAD_BYTES } from "@/lib/compress";

const cap = (id: string, patch: Partial<Capture> = {}): Capture => ({
  id, tripId: "t1", tripRef: "TRP-1", lr: "LR-1", status: "PENDING", original: new Blob(["original-bytes".repeat(50)]), compressed: new Blob(["small"]),
  originalSize: 700, compressedSize: 5, capturedAt: new Date().toISOString(), retryCount: 0, createdAt: new Date().toISOString(), ...patch,
});

beforeEach(async () => {
  for (const c of await captureDb.all()) await captureDb.remove(c.id);
  Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
});

describe("offline upload queue", () => {
  it("persists original and compressed blobs separately", async () => {
    await captureDb.put(cap("a"));
    const got = (await captureDb.get("a"))!;
    expect(got.original).toBeDefined();
    expect(got.compressed).toBeDefined();
    expect(got.originalSize).toBeGreaterThan(got.compressedSize);
  });

  it("uploads with the capture id as idempotency key and releases blobs only after server ack", async () => {
    await captureDb.put(cap("key-1"));
    const upload = vi.fn().mockResolvedValue({ created: true, pod: { id: "pod-1", verification_status: "UPLOADED" } });
    await flushQueue(upload);
    expect(upload).toHaveBeenCalledOnce();
    expect(upload.mock.calls[0][0].id).toBe("key-1");
    const after = (await captureDb.get("key-1"))!;
    expect(after.status).toBe("UPLOADED");
    expect(after.podId).toBe("pod-1");
    expect(after.original).toBeUndefined();
    expect(after.compressed).toBeUndefined();
  });

  it("keeps the original and retries with the SAME key after a network failure", async () => {
    await captureDb.put(cap("key-2"));
    const net = vi.fn().mockRejectedValue(new ApiError(0, "network", "Cannot reach the server"));
    await flushQueue(net);
    let c = (await captureDb.get("key-2"))!;
    expect(c.status).toBe("PENDING");
    expect(c.retryCount).toBe(1);
    expect(c.original).toBeDefined();
    const ok = vi.fn().mockResolvedValue({ created: false, pod: { id: "pod-9", verification_status: "UPLOADED" } });
    await flushQueue(ok);
    expect(ok.mock.calls[0][0].id).toBe("key-2");
    c = (await captureDb.get("key-2"))!;
    expect(c.status).toBe("UPLOADED");
  });

  it("escalates to RETRY_REQUIRED after repeated transient failures", async () => {
    await captureDb.put(cap("key-3", { retryCount: 2 }));
    await flushQueue(vi.fn().mockRejectedValue(new ApiError(503, "unavailable", "down")));
    expect((await captureDb.get("key-3"))!.status).toBe("RETRY_REQUIRED");
  });

  it("marks permanent client errors FAILED without hammering the server", async () => {
    await captureDb.put(cap("key-4"));
    const up = vi.fn().mockRejectedValue(new ApiError(409, "pod_in_progress", "A POD for this trip is already VERIFIED"));
    await flushQueue(up);
    const c = (await captureDb.get("key-4"))!;
    expect(c.status).toBe("FAILED");
    expect(c.lastError).toContain("already");
    await flushQueue(up);
    expect(up).toHaveBeenCalledOnce();
  });

  it("does nothing while offline and drains when back online", async () => {
    await captureDb.put(cap("key-5"));
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    const up = vi.fn().mockResolvedValue({ created: true, pod: { id: "p", verification_status: "UPLOADED" } });
    await flushQueue(up);
    expect(up).not.toHaveBeenCalled();
    expect((await captureDb.get("key-5"))!.status).toBe("PENDING");
    Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
    await flushQueue(up);
    expect(up).toHaveBeenCalledOnce();
  });

  it("never runs two flushes concurrently (no duplicate uploads)", async () => {
    await captureDb.put(cap("key-6"));
    let resolve!: (v: unknown) => void;
    const up = vi.fn().mockImplementation(() => new Promise((r) => { resolve = r; }));
    const a = flushQueue(up);
    const b = flushQueue(up);
    await new Promise((r) => setTimeout(r, 20));
    resolve({ created: true, pod: { id: "p", verification_status: "UPLOADED" } });
    await Promise.all([a, b]);
    expect(up).toHaveBeenCalledTimes(1);
  });
});

describe("compression policy", () => {
  it("lowers quality first, then dimensions, and eventually gives up", () => {
    let step: { dim: number; quality: number } | null = { dim: 1600, quality: 0.8 };
    let n = 0;
    while (step && n < 30) { const nx = nextAttempt(step.dim, step.quality); if (!nx) break; step = nx; n++; }
    expect(n).toBeGreaterThan(3);
    expect(nextAttempt(700, 0.5)).toBeNull();
    expect(MAX_UPLOAD_BYTES).toBe(300 * 1024);
  });
});
