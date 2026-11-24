import { expect, test } from "@playwright/test";

// Demo account seeded by `make seed` in development (docs/uat/README.md).
const USER = { name: "demo-analyst", password: "demo-analyst-pass" };

test("log in, close edge E02, run and see a changed travel time", async ({ page }) => {
  const scenario = `E2E close E02 ${String(Date.now())}`;

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Log in" })).toBeVisible();
  await page.getByLabel("Username").fill(USER.name);
  await page.getByLabel("Password").fill(USER.password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Study area" })).toBeVisible();

  await page.getByRole("link", { name: "Scenarios" }).click();
  await page.getByRole("link", { name: "New scenario" }).click();
  await page.getByRole("textbox", { name: "Name", exact: true }).fill(scenario);
  await page.getByText("Facilities and edges (text list)").click();
  await page.getByRole("button", { name: "Close edge E02" }).click();
  await page.getByLabel("Rationing case (OQ-24)").selectOption("uniform");
  await expect(page.getByTestId("validation-ok")).toBeVisible();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Saved as version 1.")).toBeVisible();

  await page.getByRole("button", { name: "Run this version" }).click();
  await expect(page.getByTestId("diagnostic-banner")).toBeVisible();
  await expect(page.getByTestId("run-status")).toHaveText("succeeded", { timeout: 90_000 });

  // Walking time to home care for unit A3: 30 min before, 66 min with E02 closed.
  await page
    .getByRole("combobox", { name: "Service" })
    .selectOption({ label: "Home care (synthetic)" });
  await page.getByRole("combobox", { name: "Indicator" }).selectOption("travel_time_walk_min");
  const a3 = page.getByTestId("results-table").locator('tr[data-unit="A3"]');
  await expect(a3).toContainText("66");
  await expect(a3.getByTestId("changed")).toBeVisible();
  await expect(a3.locator("td").nth(1)).toHaveText("30");
});
