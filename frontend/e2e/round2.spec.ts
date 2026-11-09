import { expect, request, test, type Page } from "@playwright/test";
import fs from "node:fs";
import { API, apiToken, asBilling, asDriver, POD_IMAGE } from "./helpers";

type Row = { id: string; status: string; hasOriginal: boolean; podId?: string; originalStatus?: string; tripRef: string };

const queue = (page: Page) => page.evaluate(() => new Promise<Row[]>((res) => {
  const r = indexedDB.open("routeproof");
  r.onsuccess = () => {
    const all = r.result.transaction("captures").objectStore("captures").getAll();
    all.onsuccess = () => res((all.result as Array<Row & { original?: Blob }>).map((c) => ({
      id: c.id, status: c.status, hasOriginal: !!c.original, podId: c.podId, originalStatus: c.originalStatus, tripRef: c.tripRef })));
  };
}));

async function podsFor(page: Page, ref: string) {
  const token = await apiToken(page, "driver4@routeproof.demo");
  const up = await (await page.request.get(`${API}/driver/uploads`, { headers: { Authorization: `Bearer ${token}` } })).json();
  return up.items.filter((p: { trip: { trip_reference: string } }) => p.trip.trip_reference === ref) as { id: string; has_separate_original: boolean }[];
}

async function capture(page: Page, ref: string) {
  await page.goto("/driver");
  await page.getByTestId(`trip-${ref}`).click();
  await page.getByTestId("file").setInputFiles(POD_IMAGE);
  await page.getByTestId("send").click();
}

test("hired driver: link → mock SMS log → no-login upload without GPS → AI → office sees it → original attached", async ({ browser, page }) => {
  await asBilling(page);
  await page.goto("/trips");
  await page.getByLabel("Search trips").fill("TRP-E2E-H");
  await page.getByRole("link", { name: "TRP-E2E-H" }).click();
  await page.getByRole("button", { name: /Hired-driver upload link/ }).click();
  await page.getByLabel(/Driver mobile number/).fill("9000077777");
  await page.getByRole("button", { name: "Create link" }).click();
  const url = await page.getByLabel(/One-time link/).inputValue();
  expect(url.split("/upload/")[1].length).toBeGreaterThanOrEqual(43);
  await page.getByRole("button", { name: "Done" }).click();
  const log = page.getByTestId("driver-links");
  await expect(log).toContainText("LOGGED_NOT_SENT");
  await expect(log).toContainText("7777");
  await expect(log).not.toContainText("9000077777");

  // Separate, signed-out browser with location permission NOT granted (the config grants it by default).
  const ctx = await browser.newContext({ permissions: [], geolocation: undefined });
  const anon = await ctx.newPage();
  await anon.goto(url);
  await expect(anon.getByTestId("lr")).toHaveText("LR-E2E-H");
  await expect(anon.getByTestId("camera")).toBeVisible();
  await anon.getByTestId("file").setInputFiles(POD_IMAGE);
  await expect(anon.getByTestId("gps-status")).not.toHaveAttribute("data-state", "ok");
  await anon.getByTestId("send").click();
  await expect(anon.getByTestId("status-card")).toHaveAttribute("data-state", "verified", { timeout: 45_000 });
  await expect.poll(async () => (await queue(anon))[0]?.originalStatus, { timeout: 30_000 }).toBe("UPLOADED");
  await ctx.close();

  // Office: the result is in the billing queue, from the link, with the GPS status recorded.
  await page.goto("/billing");
  await page.getByLabel("Search").fill("TRP-E2E-H");
  await expect(page.getByRole("row", { name: /TRP-E2E-H/ })).toBeVisible();
  const token = await apiToken(page, "billing@routeproof.demo");
  const trip = (await (await page.request.get(`${API}/trips?q=TRP-E2E-H`, { headers: { Authorization: `Bearer ${token}` } })).json()).items[0];
  const pod = await (await page.request.get(`${API}/pods/${trip.latest_pod_id}`, { headers: { Authorization: `Bearer ${token}` } })).json();
  expect(pod.source).toBe("sms_link");
  expect(pod.location_status).not.toBe("captured");
  expect(pod.has_separate_original).toBe(true);
  expect(pod.upload_size_policy).toBe("OK");
});

test("client view link: share verified PODs, client opens without login, revoke ends access", async ({ browser, page }) => {
  // Verify a POD for TRP-E2E-CL through the API.
  const drv = await apiToken(page, "driver4@routeproof.demo");
  const trips = (await (await page.request.get(`${API}/driver/trips`, { headers: { Authorization: `Bearer ${drv}` } })).json()).items;
  const cl = trips.find((t: { trip_reference: string }) => t.trip_reference === "TRP-E2E-CL");
  const up = await page.request.post(`${API}/trips/${cl.id}/pods`, { headers: { Authorization: `Bearer ${drv}`, "Idempotency-Key": "e2e-client-view-1" },
    multipart: { file: { name: "p.jpg", mimeType: "image/jpeg", buffer: fs.readFileSync(POD_IMAGE) } } });
  expect(up.status()).toBe(201);

  await asBilling(page);
  await page.goto("/billing");
  await page.getByLabel("Search").fill("TRP-E2E-CL");
  const row = page.getByRole("row", { name: /TRP-E2E-CL/ });
  await row.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Share PODs" }).click();
  await page.getByRole("dialog").getByRole("button", { name: /Create view link/ }).click();
  const link = await page.getByTestId("client-link-url").inputValue();

  const ctx = await browser.newContext();
  const client = await ctx.newPage();
  await client.goto(link);
  const table = client.getByTestId("client-view-table");
  await expect(table).toContainText("TRP-E2E-CL");
  await expect(table).toContainText("LR-E2E-CL");
  await expect(table).not.toContainText("40000"); // no freight
  await client.getByRole("button", { name: "View POD" }).click();
  await expect(client.getByRole("img", { name: /Proof of delivery for TRP-E2E-CL/ })).toBeVisible();

  await page.goto("/client-links");
  await page.getByRole("button", { name: "Revoke" }).first().click();
  await client.reload();
  await expect(client.getByTestId("client-view-error")).toContainText(/expired or was withdrawn/);
  await ctx.close();
});

test("offline capture survives closing the app; restarts sync it exactly once", async ({ context, page }) => {
  await asDriver(page);
  await page.goto("/driver");
  await page.getByTestId("trip-TRP-E2E-OFF2").click();
  await expect(page.getByTestId("camera")).toBeVisible();
  await context.setOffline(true); // the trip screen is open; the network goes away (highway dead zone)
  await page.getByTestId("file").setInputFiles(POD_IMAGE);
  await page.getByTestId("send").click();
  await expect(page.getByTestId("status-card")).toHaveAttribute("data-state", "waiting");
  const before = (await queue(page)).filter((r) => r.tripRef === "TRP-E2E-OFF2");
  expect(before).toHaveLength(1);
  expect(before[0]).toMatchObject({ status: "PENDING", hasOriginal: true });

  // "Close" the app while offline, then come back with the network restored but uploads still blocked.
  await page.close();
  await context.route("**/api/v1/trips/*/pods", (r) => r.abort("internetdisconnected"));
  await context.setOffline(false);
  const again = await context.newPage();
  await again.goto("/driver/queue");
  await expect(again.getByTestId("queue-item").first()).toBeVisible();
  const kept = (await queue(again)).find((r) => r.id === before[0].id)!;
  expect(kept.hasOriginal).toBe(true); // still on the phone after the restart, same idempotency key
  await context.unroute("**/api/v1/trips/*/pods");
  await again.getByRole("button", { name: /Try again|फिर कोशिश|पुन्हा/ }).first().click();
  await expect.poll(async () => (await queue(again)).find((r) => r.id === kept.id)?.status, { timeout: 45_000 }).toBe("UPLOADED");
  expect(await podsFor(again, "TRP-E2E-OFF2")).toHaveLength(1);
});

test("upload whose response is lost is retried with the same key and creates exactly one POD", async ({ context, page }) => {
  await asDriver(page);
  let dropped = 0;
  await context.route("**/api/v1/trips/*/pods", async (route) => {
    if (dropped === 0) { dropped++; await route.fetch(); return route.abort("connectionreset"); } // server stored it, phone never heard
    return route.continue();
  });
  await capture(page, "TRP-E2E-DUP");
  await expect.poll(() => dropped).toBe(1);
  await page.goto("/driver/queue");
  await page.getByRole("button", { name: /Try again|फिर कोशिश|पुन्हा/ }).first().click();
  await expect.poll(async () => (await queue(page)).find((r) => r.tripRef === "TRP-E2E-DUP")?.status, { timeout: 45_000 }).toBe("UPLOADED");
  expect(await podsFor(page, "TRP-E2E-DUP")).toHaveLength(1);
});

test("a server timeout keeps the capture queued and it uploads on the next attempt", async ({ context, page }) => {
  await asDriver(page);
  let n = 0;
  await context.route("**/api/v1/trips/*/pods", (route) => (n++ === 0 ? route.abort("timedout") : route.continue()));
  await capture(page, "TRP-E2E-TMO");
  await expect.poll(async () => (await queue(page)).find((r) => r.tripRef === "TRP-E2E-TMO")?.status).toMatch(/PENDING|RETRY_REQUIRED/);
  await page.goto("/driver/queue");
  await page.getByRole("button", { name: /Try again|फिर कोशिश|पुन्हा/ }).first().click();
  await expect.poll(async () => (await queue(page)).find((r) => r.tripRef === "TRP-E2E-TMO")?.status, { timeout: 45_000 }).toBe("UPLOADED");
  expect(await podsFor(page, "TRP-E2E-TMO")).toHaveLength(1);
});

test("signing out with an unsent photo warns, keeps it, and it sends after signing back in", async ({ context, page }) => {
  await asDriver(page);
  await context.route("**/api/v1/trips/*/pods", (r) => r.abort("internetdisconnected"));
  await capture(page, "TRP-E2E-OUT");
  await page.getByTestId("logout").click();
  await expect(page.getByTestId("unsent-dialog")).toBeVisible();
  await page.getByTestId("unsent-dialog").getByRole("button").nth(1).click(); // log out anyway
  await page.waitForURL(/login/);
  expect((await queue(page)).filter((r) => r.tripRef === "TRP-E2E-OUT" && r.status !== "UPLOADED")).toHaveLength(1);
  await context.unroute("**/api/v1/trips/*/pods");
  await asDriver(page);
  await page.goto("/driver/queue");
  await page.getByRole("button", { name: /Try again|फिर कोशिश|पुन्हा/ }).first().click().catch(() => { /* may already be syncing */ });
  await expect.poll(async () => (await queue(page)).find((r) => r.tripRef === "TRP-E2E-OUT")?.status, { timeout: 45_000 }).toBe("UPLOADED");
});

test("anonymous request context cannot reach staff data with a client or driver link", async () => {
  const anon = await request.newContext();
  expect((await anon.get(`${API}/client-view/not-a-real-token`)).status()).toBe(404);
  expect((await anon.get(`${API}/client-links`)).status()).toBe(401);
  await anon.dispose();
});
