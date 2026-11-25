import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithSession, stubApi } from "../test/utils";
import { ScenariosPage } from "./ScenariosPage";

const DV = { id: 2, package_id: "demo-study-area-a", version: "1.1.0", active: true };

function run(id: string, version: string) {
  return {
    id,
    status: "succeeded",
    progress: 100,
    data_version_id: version === "1.1.0" ? 2 : 1,
    package_version: version,
    created_at: "2026-11-25T00:00:00Z",
  };
}

function item(id: string, name: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    name,
    description: "",
    visibility: "shared",
    owner: "demo-analyst",
    owner_id: 2,
    is_baseline: false,
    latest_version: 1,
    data_version: DV,
    updated_at: "2026-11-25T00:00:00Z",
    latest_run: null,
    latest_run_other_data: null,
    problems: [],
    can_edit: false,
    ...extra,
  };
}

const ITEMS = [
  item("s-none", "Never run"),
  item("s-old", "Run on old data", { latest_run_other_data: run("r-old", "1.0.0") }),
  item("s-now", "Run on active data", { latest_run: run("r-now", "1.1.0") }),
  item("s-private", "Someone's draft", { visibility: "private" }),
];

function row(name: string): HTMLElement {
  const header = screen.getByRole("rowheader", { name: new RegExp(name) });
  const tr = header.closest("tr");
  if (!tr) throw new Error(`no row ${name}`);
  return tr;
}

describe("ScenariosPage latest run", () => {
  it("never links to a missing run and tells viewers to ask an analyst", async () => {
    stubApi({ "GET /scenarios": () => ITEMS.slice(0, 3) });
    renderWithSession(<ScenariosPage />, {
      session: { user: { id: 3, username: "uat-viewer", role: "viewer", active: true } },
    });
    await screen.findByText("Never run");
    const none = within(row("Never run")).getByTestId("latest-run");
    expect(none).toHaveTextContent("Not run yet. Ask an analyst to run it.");
    expect(none.tagName).not.toBe("A");
    const old = within(row("Run on old data")).getByRole("link", {
      name: /Latest run on data 1.0.0/,
    });
    expect(old).toHaveAttribute("href", "/runs/r-old");
    expect(
      within(row("Run on active data")).getByRole("link", { name: /succeeded/ }),
    ).toHaveAttribute("href", "/runs/r-now");
  });

  it("does not tell analysts to ask an analyst", async () => {
    stubApi({ "GET /scenarios": () => ITEMS.slice(0, 1) });
    renderWithSession(<ScenariosPage />);
    expect(await screen.findByTestId("latest-run")).toHaveTextContent(/^Not run yet\.$/);
  });

  it("labels other users' private scenarios for administrators", async () => {
    stubApi({ "GET /scenarios": () => ITEMS });
    renderWithSession(<ScenariosPage />, {
      session: { user: { id: 1, username: "demo-admin", role: "admin", active: true } },
    });
    const table = (await screen.findByText(/Private scenarios of other users/)).closest("table");
    if (!table) throw new Error("no table");
    expect(within(table).getByText("private (owner demo-analyst)")).toBeVisible();
    const shared = screen.getByText("Shared scenarios").closest("table");
    expect(shared).not.toHaveTextContent("Someone's draft");
  });
});
