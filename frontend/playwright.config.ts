import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const python = process.env.E2E_PYTHON ?? path.resolve(__dirname, "../backend/.venv/Scripts/python.exe");

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:3100", trace: "retain-on-failure", ...devices["Desktop Chrome"], permissions: ["geolocation"], geolocation: { latitude: 19.8762, longitude: 75.3433 } },
  webServer: [
    { command: `"${python}" tests/e2e_server.py`, cwd: "../backend", url: "http://127.0.0.1:8100/health", timeout: 120_000, reuseExistingServer: false },
    { command: "npm run dev -- -p 3100", url: "http://localhost:3100/login", timeout: 120_000, reuseExistingServer: false, env: { NEXT_PUBLIC_API_URL: "http://localhost:8100" } },
  ],
});
