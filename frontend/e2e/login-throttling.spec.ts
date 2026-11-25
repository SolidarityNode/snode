import { expect, test } from "@playwright/test";

// UAT step 4a through the frontend proxy (nginx → backend), as a browser reaches it (ADR 0015).
// Behind rootless Podman nginx cannot see browser addresses; the backend then counts usernames
// only. Where addresses are visible, refused (429) tries are not counted, so the address stays
// far below its limit. Either way one username's failures never block another username.

test("failed sign-ins for one username do not block another (UAT 4a)", async ({
  page,
  request,
}) => {
  const statuses: number[] = [];
  for (let i = 0; i < 6; i++) {
    const response = await request.post("/api/auth/login", {
      // A client-chosen address must be ignored (nginx overwrites it).
      headers: { "X-Real-IP": `198.51.100.${String(i)}`, "X-Forwarded-For": "198.51.100.200" },
      data: { username: "uat-nobody", password: "wrong-password-1" },
    });
    statuses.push(response.status());
  }
  expect(statuses[0]).toBe(401);
  expect(statuses.slice(1)).toEqual([429, 429, 429, 429, 429]); // delayed after the first failure
  const refused = await request.post("/api/auth/login", {
    data: { username: "uat-nobody", password: "wrong-password-1" },
  });
  expect(await refused.json()).toEqual({
    detail: "too many failed sign-in attempts; try again later",
  });

  await page.goto("/");
  await page.getByLabel("Username").fill("demo-analyst");
  await page.getByLabel("Password").fill("demo-analyst-pass");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Study area" })).toBeVisible();
});
