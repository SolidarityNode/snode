import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against the running stacks (`make test-e2e` starts and seeds them): a
// municipal installation (E2E_BASE_URL) and a hub (E2E_HUB_URL). The hub test imports a package
// into the municipal installation, so it runs after the platform tests (project dependency).
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
  projects: [
    {
      name: "platform",
      testIgnore: /hub-onboarding\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "hub",
      testMatch: /hub-onboarding\.spec\.ts/,
      dependencies: ["platform"],
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
