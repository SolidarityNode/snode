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

describe("ScenarioEditorPage placeholders", () => {
  it("keeps network and population changes it cannot edit yet, and says they are recorded only", async () => {
    const network = {
      edge_changes: [
        { edge_id: "E01", mode: "walk", quantity: "travel_time", change: "relative", amount: -20 },
      ],
      new_edges: [],
    };
    const population = [{ unit_id: "A1", group_id: "G-OLD", change: "absolute", amount: 10 }];
    const { calls } = stubApi({
      "GET /scenarios/s1": () => ({
        id: "s1",
        can_edit: true,
        visibility: "private",
        is_baseline: false,
        latest_version: 1,
        problems: [],
        name: "Placeholders",
        description: "",
        owner: "analyst",
        owner_id: 1,
        created_at: "2026-11-25T00:00:00Z",
        latest_run: null,
        latest_run_other_data: null,
        data_version: { id: 1, package_id: "demo-study-area-a", version: "1.0.0" },
        current: {
          version: 1,
          name: "Placeholders",
          description: "",
          created_at: "2026-11-25T00:00:00Z",
          created_by: "analyst",
          data_version: { id: 1, package_id: "demo-study-area-a", version: "1.0.0" },
          body: { schema_version: "1.0", network_changes: network, population_changes: population },
        },
      }),
      "GET /data-versions/1/layers/network_edges": () => EDGES,
      "GET /data-versions/1/layers/.*": () => EMPTY,
      "GET /data-versions/1/catalog": () => ({ groups: [], services: [] }),
      "POST /scenarios/validate": () => ({ valid: true, errors: [], problems: [] }),
    });
    renderWithSession(<ScenarioEditorPage />, {
      path: "/scenarios/s1",
      route: "/scenarios/:scenarioId",
      session: { activeDataVersion: DV },
    });
    expect(await screen.findByTestId("recorded-only")).toHaveTextContent(
      "2 network or population change(s): recorded only",
    );
    await userEvent.type(screen.getByRole("textbox", { name: "Name" }), " v2");
    await waitFor(() => {
      const sent = calls.filter((c) => c.path === "/scenarios/validate").at(-1)?.body as {
        body: { network_changes: unknown; population_changes: unknown };
      };
      expect(sent.body.network_changes).toEqual(network);
      expect(sent.body.population_changes).toEqual(population);
    });
  });
});

describe("ScenarioEditorPage visibility and data version", () => {
  it("says who sees a private scenario and when it was made on other data", async () => {
    const scenario = {
      id: "s2",
      can_edit: true,
      visibility: "private",
      is_baseline: false,
      latest_version: 1,
      problems: [],
      name: "Old data",
      description: "",
      owner: "analyst",
      owner_id: 1,
      created_at: "2026-11-25T00:00:00Z",
      updated_at: "2026-11-25T00:00:00Z",
      latest_run: null,
      latest_run_other_data: {
        id: "r-old",
        status: "succeeded",
        progress: 100,
        data_version_id: 1,
        package_version: "1.0.0",
        created_at: "2026-11-25T00:00:00Z",
      },
      data_version: { id: 1, package_id: "demo-study-area-a", version: "1.0.0", active: false },
      versions: [1],
      current: {
        scenario_id: "s2",
        version: 1,
        name: "Old data",
        description: "",
        schema_version: "1.0",
        created_at: "2026-11-25T00:00:00Z",
        created_by: "analyst",
        data_version: { id: 1, package_id: "demo-study-area-a", version: "1.0.0", active: false },
        body: { schema_version: "1.0" },
      },
    };
    stubApi({
      "GET /scenarios/s2": () => scenario,
      "GET /data-versions/2/layers/.*": () => EMPTY,
      "GET /data-versions/2/catalog": () => ({ groups: [], services: [] }),
      "POST /scenarios/validate": () => ({ valid: true, errors: [], problems: [] }),
    });
    renderWithSession(<ScenarioEditorPage />, {
      path: "/scenarios/s2",
      route: "/scenarios/:scenarioId",
      session: { activeDataVersion: { ...DV, id: 2, version: "1.1.0" } },
    });
    expect(await screen.findByTestId("data-differs")).toHaveTextContent(
      "Created against data 1.0.0; active data is 1.1.0.",
    );
    expect(screen.getByTestId("visibility-hint")).toHaveTextContent(
      "Private: visible to you and to administrators.",
    );
    expect(screen.getByRole("link", { name: /Latest run on data 1.0.0/ })).toHaveAttribute(
      "href",
      "/runs/r-old",
    );
  });
});
