import { expect, type Page } from "@playwright/test";
import path from "node:path";

export const POD_IMAGE = path.resolve(__dirname, "fixtures/pod.jpg");
export const API = "http://localhost:8100/api/v1";

export async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("Demo@12345");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/\/(driver|dashboard)/);
}

export const asDriver = (page: Page) => login(page, "driver4@routeproof.demo");
export const asBilling = (page: Page) => login(page, "billing@routeproof.demo");

export async function captureAndSend(page: Page, tripRef: string) {
  await page.goto("/driver");
  await page.getByTestId(`trip-${tripRef}`).click();
  await expect(page.getByTestId("camera")).toBeVisible();
  await page.getByTestId("file").setInputFiles(POD_IMAGE);
  await expect(page.getByTestId("send")).toBeVisible();
  const kb = parseInt((await page.getByTestId("size").innerText()).replace(/\D/g, ""), 10);
  expect(kb).toBeLessThan(300);
  await page.getByTestId("send").click();
  return kb;
}

export async function apiToken(page: Page, email: string) {
  const r = await page.request.post(`${API}/auth/login`, { data: { email, password: "Demo@12345" } });
  return (await r.json()).access_token as string;
}
