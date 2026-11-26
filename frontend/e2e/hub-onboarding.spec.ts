import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, request, test, type APIRequestContext } from "@playwright/test";

// The hub stack of `make test-e2e` (DEPLOYMENT_MODE=hub) with the synthetic sources registered
// (DP-005) and the development demo users.
const HUB = process.env.E2E_HUB_URL ?? "http://127.0.0.1:8180";
const DEMO =
  process.env.E2E_HUB_DEMO ?? join(process.cwd(), "..", "data", "synthetic", "demo", "hub");
const ADMIN = { username: "demo-admin", password: "demo-admin-pass" };
const ANALYST = { username: "demo-analyst", password: "demo-analyst-pass" };
const VIEWER = { username: "e2e-hub-viewer", password: "e2e-hub-viewer-pass" };

// Every hub endpoint with the lowest role allowed (as backend/tests/hub/test_api.py), checked
// here through the frontend proxy (/api), where the platform UAT once found a proxy-only bug.
const PERMISSIONS: [string, string, "viewer" | "analyst" | "admin"][] = [
  ["GET", "/hub/status", "viewer"],
  ["GET", "/hub/sources", "viewer"],
  ["POST", "/hub/sources", "admin"],
  ["GET", "/hub/coverage", "viewer"],
  ["GET", "/hub/onboarding/M-A", "viewer"],
  ["POST", "/hub/onboarding/M-ZZ/base", "admin"],
  ["POST", "/hub/onboarding/M-ZZ/status", "admin"],
  ["GET", "/hub/records/1", "viewer"],
  ["GET", "/hub/jobs/00000000-0000-0000-0000-000000000000", "viewer"],
  ["POST", "/hub/jobs/00000000-0000-0000-0000-000000000000/cancel", "admin"],
  ["GET", "/hub/facilities/template", "viewer"],
  ["GET", "/hub/facilities/export?municipality=M-A", "viewer"],
  ["GET", "/hub/facilities", "viewer"],
  ["GET", "/hub/facilities/HF-999999/history", "viewer"],
  ["POST", "/hub/facility-imports", "analyst"],
  ["POST", "/hub/facilities/edits", "analyst"],
  ["GET", "/hub/changesets", "viewer"],
  ["GET", "/hub/changesets/999999", "viewer"],
  ["GET", "/hub/changesets/999999/report", "viewer"],
  ["POST", "/hub/changesets/999999/approve", "admin"],
  ["POST", "/hub/changesets/999999/reject", "admin"],
  ["GET", "/hub/study-areas", "viewer"],
  ["POST", "/hub/study-areas", "admin"],
  ["POST", "/hub/study-areas/nowhere/publish", "admin"],
  ["GET", "/hub/study-areas/nowhere/packages/9.9.9/download", "viewer"],
];
const ROLES = ["viewer", "analyst", "admin"] as const;

async function signedIn(user: { username: string; password: string }): Promise<APIRequestContext> {
  const context = await request.newContext({ baseURL: `${HUB}/api/` });
  const response = await context.post("auth/login", { data: user });
  expect(response.status(), `${user.username} signs in through the proxy`).toBe(200);
  return context;
}

test("hub permissions per role through the frontend proxy", async () => {
  const admin = await signedIn(ADMIN);
  const created = await admin.post("users", { data: { ...VIEWER, role: "viewer" } });
  expect([201, 200, 409, 422]).toContain(created.status());
  const clients = {
    anonymous: await request.newContext({ baseURL: `${HUB}/api/` }),
    viewer: await signedIn(VIEWER),
    analyst: await signedIn(ANALYST),
    admin,
  };
  for (const [method, path, lowest] of PERMISSIONS) {
    const url = path.slice(1);
    const anonymous = await clients.anonymous.fetch(url, {
      method,
      data: method === "POST" ? {} : undefined,
    });
    expect(anonymous.status(), `anonymous ${method} ${path}`).toBe(401);
    for (const role of ROLES) {
      const response = await clients[role].fetch(url, {
        method,
        data: method === "POST" ? {} : undefined,
      });
      if (ROLES.indexOf(role) < ROLES.indexOf(lowest)) {
        expect(response.status(), `${role} ${method} ${path}`).toBe(403);
      } else {
        expect([401, 403], `${role} ${method} ${path}`).not.toContain(response.status());
      }
    }
  }
});

test("onboard, import facilities, publish, and import the package in a municipal installation", async ({
  page,
  browser,
}) => {
  test.setTimeout(240_000);
  // Hub: sign in, start onboarding of M-A and follow the job.
  await page.goto(`${HUB}/login`);
  await page.getByLabel("Username").fill(ADMIN.username);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Onboarding of municipalities" })).toBeVisible();
  await page.getByRole("button", { name: "Start onboarding of M-A" }).click();
  await page.getByRole("link", { name: "Follow its progress" }).click();
  await expect(page.getByTestId("job-status")).toHaveText("succeeded", { timeout: 90_000 });
  await page.reload();
  await expect(page.getByTestId("onboarding-status")).toContainText("base data ready");
  await expect(page.getByTestId("base-report")).toContainText("population of M-A: 4180");

  // Facilities: upload the file with personal-data columns; they are dropped and reported.
  await page.getByRole("link", { name: "Facilities of this municipality" }).click();
  await page.getByLabel("Source of the data").fill("Synthetic municipal register");
  await page.getByLabel("File").setInputFiles(join(DEMO, "imports", "facilities-M-A-personal.csv"));
  await page.getByRole("button", { name: "Check the file" }).click();
  const report = page.getByTestId("validation-report");
  await expect(report).toContainText(
    "Column contact_person looks like personal data and was dropped",
  );
  await expect(page.getByTestId("changeset-summary")).toContainText(
    "3 added, 0 updated, 0 closed; 0 error(s).",
  );
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByTestId("changeset-status")).toContainText("approved");
  await expect(page.getByTestId("facility-list")).toContainText("HF-000001");

  // Coverage matrix.
  await page.getByRole("link", { name: "Coverage" }).click();
  const a = page.getByTestId("coverage-matrix").locator('tr[data-municipality="M-A"]');
  await expect(a.locator('td[data-layer="facilities"]')).toContainText(
    "verified by the municipality",
  );
  await expect(a.locator('td[data-layer="transit"]')).toContainText("missing");

  // Study area and publishing.
  await page.getByRole("link", { name: "Study areas and packages" }).click();
  await page.getByLabel(/^Id/).fill("study-area-a");
  await page.getByLabel("Name", { exact: true }).fill("Study area A (fictional)");
  await page.getByLabel("Core municipalities").selectOption("M-A");
  await page.getByRole("button", { name: "Create study area" }).click();
  await page.getByRole("button", { name: "Publish 1.0.0" }).click();
  await expect(page.getByRole("link", { name: "Download 1.0.0 (.zip)" })).toBeVisible({
    timeout: 90_000,
  });

  // Download the archive and import it in the municipal installation (Admin screen).
  const download = await page.request.get(
    `${HUB}/api/hub/study-areas/study-area-a/packages/1.0.0/download`,
  );
  expect(download.status()).toBe(200);
  const archive = await download.body();
  expect(archive.subarray(0, 2).toString()).toBe("PK");

  const municipal = await browser.newPage();
  await municipal.goto("/login");
  await municipal.getByLabel("Username").fill(ADMIN.username);
  await municipal.getByLabel("Password").fill(ADMIN.password);
  await municipal.getByRole("button", { name: "Log in" }).click();
  await municipal.getByRole("link", { name: "Admin" }).click();
  await municipal.getByLabel(/Or upload a package archive/).setInputFiles({
    name: "study-area-a-1.0.0.zip",
    mimeType: "application/zip",
    buffer: archive,
  });
  const preview = municipal.getByTestId("package-preview");
  await expect(preview).toContainText("Preview of study-area-a 1.0.0");
  await expect(preview.getByRole("alert")).toHaveCount(0); // no blocking problem
  await municipal.getByRole("button", { name: "Confirm import" }).click();
  await expect(municipal.getByTestId("import-outcome")).toContainText("it is now active");
  await expect(municipal.getByTestId("data-version")).toContainText("study-area-a 1.0.0");
  expect(readFileSync(join(DEMO, "sources", "sources.json"), "utf8")).toContain("DP-005");
});
