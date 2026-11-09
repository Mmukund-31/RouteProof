import { expect, request, test } from "@playwright/test";
import fs from "node:fs";
import { API, apiToken, asBilling, asDriver, captureAndSend, login, POD_IMAGE } from "./helpers";

test.describe.configure({ mode: "serial" });

test("end-to-end: driver capture → AI → review → correction → billing → CSV → audit", async ({ browser }) => {
  // 1-4 Driver logs in, opens trip, captures, uploads
  const dctx = await browser.newContext({ permissions: ["geolocation"], geolocation: { latitude: 19.87, longitude: 75.34 } });
  const driver = await dctx.newPage();
  await asDriver(driver);
  await expect(driver).toHaveURL(/\/driver$/);
  const kb = await captureAndSend(driver, "TRP-E2E-S");
  expect(kb).toBeLessThan(300);
  // 5-7 AI processes; shortage routes to review; the driver sees "office is checking" (amber), never a false success
  await expect(driver.getByTestId("status-card")).toHaveAttribute("data-state", "review", { timeout: 45_000 });

  // 7-10 Billing executive reviews, corrects, approves
  const bctx = await browser.newContext();
  const bill = await bctx.newPage();
  await asBilling(bill);
  await expect(bill).toHaveURL(/\/dashboard/);
  await bill.goto("/reviews");
  const row = bill.getByRole("row", { name: /TRP-E2E-S/ });
  await expect(row).toContainText("Shortage remark");
  await row.getByRole("link", { name: "Review" }).click();
  await expect(bill.getByText("Original document")).toBeVisible();
  await expect(bill.getByTestId("row-delivered_quantity")).toContainText("94");
  await expect(bill.getByText("do not authenticate", { exact: false }).or(bill.getByText("does not authenticate", { exact: false }))).toBeVisible();
  await bill.getByLabel("Correct Remarks (verbatim)").fill("Short by 6 cartons - accepted by consignee, credit note raised");
  await bill.getByLabel("Reason / note").fill("Consignee confirmed shortage is settled via credit note");
  // Shortage is a business exception: approving it requires a recorded rationale.
  await bill.getByLabel(/Why is this exception accepted/).fill("Client accepted the 6-carton shortage by email");
  await bill.getByRole("button", { name: "Approve", exact: true }).click();
  await bill.getByRole("dialog").getByRole("button", { name: "Approve" }).click();
  await expect(bill.getByText("Verified").first()).toBeVisible();
  await expect(bill.getByTestId("approved-exception")).toContainText("Client accepted the 6-carton shortage");
  await expect(bill.getByTestId("row-remarks")).toContainText("Corrected");
  await expect(bill.getByTestId("row-remarks")).toContainText("Short by 6 cartons");

  // 10-11 Billing queue + CSV export
  await bill.goto("/billing");
  const qrow = bill.getByRole("row", { name: /TRP-E2E-S/ });
  await expect(qrow).toBeVisible();
  await qrow.getByRole("checkbox").check();
  await bill.getByRole("button", { name: "Export CSV" }).click();
  const [download] = await Promise.all([bill.waitForEvent("download"), bill.getByRole("dialog").getByRole("button", { name: /Export & download/ }).click()]);
  const csv = fs.readFileSync((await download.path())!, "utf8");
  expect(csv).toContain("trip_reference,lr_number,eway_bill_number");
  expect(csv).toContain("TRP-E2E-S");
  expect(csv).toContain("LR-E2E-S");
  expect(csv).toContain("pod_exceptions");
  expect(csv).toMatch(/SHORTAGE/);
  // exported trips can't be exported twice without an explicit re-export
  await bill.getByRole("tab", { name: "Ready to export" }).click();
  await bill.getByLabel("Search").fill("TRP-E2E-S");
  const again = bill.getByRole("row", { name: /TRP-E2E-S/ });
  await again.getByRole("checkbox").check();
  await bill.getByRole("button", { name: "Re-export CSV" }).click();
  await expect(bill.getByRole("dialog").getByText(/already exported/)).toBeVisible();
  await bill.keyboard.press("Escape");

  // 12 Audit history
  await bill.goto("/audit");
  await bill.getByLabel("Action").fill("pod.fields_corrected");
  await expect(bill.getByRole("cell", { name: "pod.fields_corrected" }).first()).toBeVisible();
  await bill.getByLabel("Action").fill("trip.exported");
  await expect(bill.getByRole("cell", { name: "trip.exported" }).first()).toBeVisible();

  // Driver now sees success on the trip? (trip is verified by human)
  await driver.reload();
  await expect(driver.getByTestId("status-card")).toHaveAttribute("data-state", "verified", { timeout: 30_000 });
  await dctx.close(); await bctx.close();
});

test("clean POD is verified by automated checks and reaches billing queue with no human step", async ({ page }) => {
  await asDriver(page);
  await captureAndSend(page, "TRP-E2E-A");
  await expect(page.getByTestId("status-card")).toHaveAttribute("data-state", "verified", { timeout: 45_000 });
  const token = await apiToken(page, "billing@routeproof.demo");
  const q = await page.request.get(`${API}/billing/queue?q=TRP-E2E-A`, { headers: { Authorization: `Bearer ${token}` } });
  expect((await q.json()).total).toBe(1);
});

test("AI provider timeout keeps the POD and routes to manual review", async ({ page }) => {
  await asDriver(page);
  await captureAndSend(page, "TRP-E2E-X");
  await expect(page.getByTestId("status-card")).toHaveAttribute("data-state", "review", { timeout: 45_000 });
  const token = await apiToken(page, "billing@routeproof.demo");
  const r = await (await page.request.get(`${API}/reviews?q=TRP-E2E-X`, { headers: { Authorization: `Bearer ${token}` } })).json();
  expect(r.items[0].review_reasons).toContain("AI_ERROR");
  expect(r.items[0].extraction.processing_error).toContain("timeout");
});

test("missing stamp → retake requested; after two retakes the third goes to manual review", async ({ page }) => {
  await asDriver(page);
  const token = await apiToken(page, "driver4@routeproof.demo");
  const attempts = async () => {
    const r = await (await page.request.get(`${API}/driver/uploads`, { headers: { Authorization: `Bearer ${token}` } })).json();
    return (r.items as { attempt_number: number; verification_status: string; trip: { trip_reference: string } }[])
      .filter((p) => p.trip.trip_reference === "TRP-E2E-R").sort((a, b) => a.attempt_number - b.attempt_number);
  };
  for (let i = 0; i < 3; i++) {
    await captureAndSend(page, "TRP-E2E-R");
    // wait until the server has this attempt AND finished deciding (not UPLOADED / AI_PROCESSING)
    await expect.poll(async () => {
      const a = await attempts();
      return a.length === i + 1 && !["UPLOADED", "AI_PROCESSING"].includes(a[i].verification_status);
    }, { timeout: 45_000, intervals: [1000] }).toBe(true);
  }
  expect((await attempts()).map((p) => p.verification_status)).toEqual(["RETAKE_REQUESTED", "RETAKE_REQUESTED", "NEEDS_REVIEW"]);
  // the driver UI reflects it: third attempt is "office is checking" (amber), with no further retake prompt
  await page.reload();
  await expect(page.getByTestId("status-card")).toHaveAttribute("data-state", "review");
});

test("authorization: a driver cannot open the executive workspace or call billing APIs", async ({ page }) => {
  await asDriver(page);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/unauthorized/);
  const token = await apiToken(page, "driver4@routeproof.demo");
  for (const p of ["/trips", "/billing/queue", "/dashboard/metrics", "/audit-logs"]) {
    expect((await page.request.get(`${API}${p}`, { headers: { Authorization: `Bearer ${token}` } })).status()).toBe(403);
  }
  // page.request shares the browser's HttpOnly session cookie; use a clean context for the "no credentials" check.
  const anon = await request.newContext();
  expect((await anon.get(`${API}/trips`)).status()).toBe(401);
  await anon.dispose();
  // The browser session is an HttpOnly cookie: page JavaScript cannot see it, and no token sits in localStorage.
  const visible = await page.evaluate(() => ({ cookie: document.cookie, storage: JSON.stringify(localStorage) }));
  expect(visible.cookie).not.toContain("rp_session");
  expect(visible.storage).not.toContain("eyJ");
  // A cookie-authenticated write without the CSRF header is refused.
  expect((await page.request.post(`${API}/auth/logout`)).status()).toBe(403);
});

test("dashboard shows database-backed numbers and the demo-data label", async ({ page }) => {
  await asBilling(page);
  await expect(page.getByText("seeded demo data")).toBeVisible();
  await expect(page.getByText("Demo data", { exact: true })).toBeVisible(); // top bar, on every page
  await expect(page.getByRole("heading", { name: "Operations dashboard" })).toBeVisible();
  const token = await apiToken(page, "billing@routeproof.demo");
  const m = await (await page.request.get(`${API}/dashboard/metrics`, { headers: { Authorization: `Bearer ${token}` } })).json();
  await expect(page.getByText("Total trips").locator("..")).toContainText(String(m.total_trips));
  // seeded client scenarios are present
  await page.goto("/trips");
  for (const ref of ["TRP-66120", "TRP-66134", "TRP-66141"]) {
    await page.getByLabel("Search trips").fill(ref);
    await expect(page.getByRole("row", { name: new RegExp(ref) })).toBeVisible();
  }
});

test("hired-driver upload link is single-trip and works without an account", async ({ browser, page }) => {
  await asBilling(page);
  await page.goto("/trips");
  await page.getByLabel("Search trips").fill("TRP-E2E-A2");
  await page.getByRole("link", { name: "TRP-E2E-A2" }).click();
  await page.getByRole("button", { name: /Hired-driver upload link/ }).click();
  await page.getByLabel(/Driver mobile number/).fill("9000011111");
  await page.getByRole("button", { name: "Create link" }).click();
  await expect(page.getByText("no SMS was actually sent", { exact: false })).toBeVisible();
  const url = await page.getByLabel(/One-time link/).inputValue();
  const ctx = await browser.newContext({ permissions: ["geolocation"], geolocation: { latitude: 19.8, longitude: 75.3 } });
  const anon = await ctx.newPage();
  await anon.goto(url.replace("localhost:3100", "localhost:3100"));
  await expect(anon.getByTestId("lr")).toHaveText("LR-E2E-A2");
  await anon.getByTestId("file").setInputFiles(POD_IMAGE);
  await anon.getByTestId("send").click();
  await expect(anon.getByTestId("status-card")).toHaveAttribute("data-state", /verified|processing|queued|uploaded/, { timeout: 45_000 });
  await expect(anon.getByTestId("status-card")).toHaveAttribute("data-state", "verified", { timeout: 45_000 });
  await ctx.close();
});

test("mobile layouts render for driver without horizontal scroll", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 360, height: 740 } });
  const page = await ctx.newPage();
  await login(page, "driver4@routeproof.demo");
  await expect(page.getByRole("heading", { name: /My trips|मेरी/ })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
  await ctx.close();
});
