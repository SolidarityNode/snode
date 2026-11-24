import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithSession, stubApi } from "../test/utils";
import { ScenarioEditorPage } from "./ScenarioEditorPage";

vi.mock("../map/MapView", () => ({ MapView: () => <div data-testid="map" /> }));

const DV = {
  id: 1,
  package_id: "demo-study-area-a",
  version: "1.0.0",
  schema_version: "1.0",
  created: "2026-11-24",
  active: true,
  imported_at: "2026-11-24T00:00:00Z",
  synthetic: true,
  study_area: {},
  changelog: [],
  processing_notes: [],
  sources: [],
  coverage: [],
  edge_effect_units: [],
};

const EMPTY = { type: "FeatureCollection", features: [] };
const EDGES = {
  type: "FeatureCollection",
  features: [
    { type: "Feature", id: "E01", properties: { closable: false }, geometry: null },
    { type: "Feature", id: "E02", properties: { closable: true }, geometry: null },
  ],
};

interface Draft {
  name: string;
  body: { closed_edges: unknown; rationing: unknown };
}

function api(validate: (draft: Draft) => unknown) {
  return stubApi({
    "GET /data-versions/1/layers/network_edges": () => EDGES,
    "GET /data-versions/1/layers/.*": () => EMPTY,
    "GET /data-versions/1/catalog": () => ({ groups: [], services: [] }),
    "POST /scenarios/validate": (_, init) => validate(JSON.parse(init.body ?? "{}") as Draft),
  });
}

describe("ScenarioEditorPage", () => {
  it("validates live and keeps Save disabled while invalid", async () => {
    const { calls } = api((draft) =>
      draft.name
        ? draft.body.closed_edges && !draft.body.rationing
          ? {
              valid: false,
              errors: [
                {
                  loc: ["body", "body"],
                  msg: "a disruption scenario must state its rationing case (OQ-24)",
                },
              ],
              problems: [],
            }
          : { valid: true, errors: [], problems: [] }
        : {
            valid: false,
            errors: [{ loc: ["body", "name"], msg: "String should have at least 1 character" }],
            problems: [],
          },
    );
    renderWithSession(<ScenarioEditorPage />, { session: { activeDataVersion: DV } });
    const save = screen.getByRole("button", { name: "Save" });

    expect(await screen.findByTestId("validation-errors")).toHaveTextContent(
      "name: String should have at least 1 character",
    );
    expect(save).toBeDisabled();

    await userEvent.type(screen.getByRole("textbox", { name: "Name" }), "Close E02");
    await userEvent.click(screen.getByText("Facilities and edges (text list)"));
    await userEvent.click(await screen.findByRole("button", { name: "Close edge E02" }));
    expect(screen.getByTestId("change-list")).toHaveTextContent("Closed edges: E02");
    await waitFor(() => {
      expect(screen.getByTestId("validation-errors")).toHaveTextContent("rationing case (OQ-24)");
    });
    expect(save).toBeDisabled();

    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Rationing case (OQ-24)" }),
      "uniform",
    );
    expect(await screen.findByTestId("validation-ok")).toBeInTheDocument();
    expect(save).toBeEnabled();
    const last = calls.filter((c) => c.path === "/scenarios/validate").at(-1)?.body as Draft;
    expect(last.body.closed_edges).toEqual({ edge_ids: ["E02"], modes: ["walk", "car"] });
    expect(screen.getByRole("button", { name: "Close edge E01" })).toBeDisabled();
  });

  it("shows reference problems returned by the backend", async () => {
    api(() => ({
      valid: false,
      errors: [],
      problems: ["facility F4: closed or missing in data 1.0.0"],
    }));
    renderWithSession(<ScenarioEditorPage />, { session: { activeDataVersion: DV } });
    expect(await screen.findByTestId("validation-errors")).toHaveTextContent(
      "facility F4: closed or missing",
    );
  });
});
