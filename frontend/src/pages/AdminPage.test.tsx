import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { renderWithSession, stubApi } from "../test/utils";
import { AdminPage } from "./AdminPage";

function version(id: number, v: string, active: boolean) {
  return {
    id,
    package_id: "demo-study-area-a",
    version: v,
    schema_version: "2.0",
    created: "2026-11-24",
    active,
    imported_at: `2026-11-2${String(id)}T10:00:00Z`,
    synthetic: true,
    study_area: {},
    changelog: [],
    processing_notes: [],
    sources: [],
    layer_licences: [],
    coverage: [],
    edge_effect_units: [],
  };
}

describe("AdminPage rollback", () => {
  it("makes an earlier version active again after confirmation", async () => {
    let versions = [version(1, "1.0.0", false), version(2, "1.1.0", true)];
    const { calls } = stubApi({
      "GET /data-versions": () => versions,
      "GET /packages/available": () => [],
      "GET /users": () => [],
      "POST /data-versions/1/activate": () => {
        versions = [version(1, "1.0.0", true), version(2, "1.1.0", false)];
        return {
          data_version_id: 1,
          noop: false,
          baseline_run_id: "run-1",
          revalidation: [{ scenario_id: "s4", name: "F4 staff +1", problems: ["facility F4"] }],
        };
      },
    });
    renderWithSession(<AdminPage />, {
      session: { user: { id: 1, username: "admin", role: "admin", active: true } },
    });
    const table = await screen.findByRole("table", { name: /Imported versions/ });
    const rows = within(table).getAllByRole("row");
    expect(within(rows[2] as HTMLElement).queryByRole("button")).not.toBeInTheDocument(); // active
    await userEvent.click(await screen.findByRole("button", { name: "Make 1.0.0 active again" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "Make demo-study-area-a 1.0.0 the active data again?",
    );
    expect(calls.some((c) => c.method === "POST")).toBe(false); // nothing before confirming
    await userEvent.click(screen.getByRole("button", { name: "Yes, make it active" }));
    expect(await screen.findByTestId("import-outcome")).toHaveTextContent(
      "Data version 1.0.0 is active again.",
    );
    expect(screen.getByRole("link", { name: "Baseline run for the new data" })).toHaveAttribute(
      "href",
      "/runs/run-1",
    );
    expect(screen.getByText(/F4 staff \+1/)).toBeInTheDocument();
    expect(calls.filter((c) => c.path === "/data-versions/1/activate")).toHaveLength(1);
  });
});
