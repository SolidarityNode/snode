import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against the running stack (`make test-e2e` starts and seeds it).
export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:8080",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
