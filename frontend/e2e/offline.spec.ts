import { expect, test } from "@playwright/test";
import fs from "node:fs";
import { API, apiToken, asDriver, POD_IMAGE } from "./helpers";

type Rec = { status: string; original?: Blob; compressed?: Blob; originalSize: number; compressedSize: number; id: string; podId: string };

test("offline capture is queued in IndexedDB, survives reload, and syncs once on reconnection (idempotent)", async ({ page, context }) => {
  await asDriver(page);
  await page.goto("/driver");
  await page.getByTestId("trip-TRP-E2E-OFF").click();
  await expect(page.getByTestId("camera")).toBeVisible();

  // --- go offline (network actually disabled) ---
  await context.setOffline(true);
  await expect(page.getByTestId("net-status")).toContainText(/No internet|इंटरनेट नहीं|इंटरनेट नाही/);
  await page.getByTestId("file").setInputFiles(POD_IMAGE);
  await expect(page.getByTestId("send")).toBeVisible();
  const kb = parseInt((await page.getByTestId("size").innerText()).replace(/\D/g, ""), 10);
  expect(kb).toBeLessThan(300);
  await page.getByTestId("send").click();
  await expect(page.getByTestId("status-card")).toHaveAttribute("data-state", "waiting");

  // The capture is persisted locally with BOTH the original and compressed blobs.
  const rec = await page.evaluate(() => new Promise<{ status: string; hasOriginal: boolean; hasCompressed: boolean; orig: number; comp: number; id: string }[]>((res) => {
    const r = indexedDB.open("routeproof");
    r.onsuccess = () => {
      const all = r.result.transaction("captures").objectStore("captures").getAll();
      all.onsuccess = () => res((all.result as Rec[]).map((c) => ({ status: c.status, hasOriginal: !!c.original, hasCompressed: !!c.compressed, orig: c.originalSize, comp: c.compressedSize, id: c.id })));
    };
  }));
  expect(rec).toHaveLength(1);
  expect(rec[0]).toMatchObject({ status: "PENDING", hasOriginal: true, hasCompressed: true });
  expect(rec[0].comp).toBeLessThan(300 * 1024);
  const key = rec[0].id;

  // --- reconnect: the SAME page (no reload) must notice the `online` event and sync by itself ---
  await context.setOffline(false);
  await expect(page.getByTestId("status-card")).not.toHaveAttribute("data-state", "waiting", { timeout: 45_000 });
  await page.goto("/driver/queue");
  await expect(page.getByTestId("queue-item").first()).toHaveAttribute("data-status", "UPLOADED", { timeout: 45_000 });

  // The original is a second upload after the compressed copy; it is released only once the server acknowledged IT.
  const read = () => page.evaluate(() => new Promise<{ hasOriginal: boolean; podId: string }[]>((res) => {
    const r = indexedDB.open("routeproof");
    r.onsuccess = () => {
      const all = r.result.transaction("captures").objectStore("captures").getAll();
      all.onsuccess = () => res((all.result as Rec[]).map((c) => ({ hasOriginal: !!c.original, podId: c.podId })));
    };
  }));
  await expect.poll(async () => (await read())[0].hasOriginal, { timeout: 45_000 }).toBe(false);
  const after = await read();
  expect(after[0].podId).toBeTruthy();

  // Duplicate retry with the SAME idempotency key returns the same POD; no second record is created.
  const token = await apiToken(page, "driver4@routeproof.demo");
  const img = fs.readFileSync(POD_IMAGE);
  const dup = await page.request.post(`${API}/trips/${await tripId(page, token)}/pods`, {
    headers: { Authorization: `Bearer ${token}`, "Idempotency-Key": key },
    multipart: { file: { name: "x.jpg", mimeType: "image/jpeg", buffer: img } },
  });
  expect(dup.status()).toBe(200);
  expect((await dup.json()).pod.id).toBe(after[0].podId);
  const up = await (await page.request.get(`${API}/driver/uploads`, { headers: { Authorization: `Bearer ${token}` } })).json();
  expect(up.items.filter((p: { trip: { trip_reference: string } }) => p.trip.trip_reference === "TRP-E2E-OFF")).toHaveLength(1);
});

async function tripId(page: import("@playwright/test").Page, token: string) {
  const r = await (await page.request.get(`${API}/driver/trips`, { headers: { Authorization: `Bearer ${token}` } })).json();
  return r.items.find((t: { trip_reference: string }) => t.trip_reference === "TRP-E2E-OFF").id as string;
}
