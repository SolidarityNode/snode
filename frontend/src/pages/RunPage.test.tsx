import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CATALOG, MapRecorder, UNITS, indicator, run } from "../test/results";
import { renderWithSession, stubApi } from "../test/utils";
import { RunPage } from "./RunPage";

const recorder = vi.hoisted(() => ({ current: null as MapRecorder | null }));

vi.mock("../map/MapView", () => ({
  MapView: ({ label, layers }: { label: string; layers: never[] }) => {
    recorder.current?.record(label, layers);
    return <div data-testid="map" aria-label={label} />;
  },
}));

const MAP = "Results map of the selected indicator per core unit";
const RUN = run("r1", [indicator("risk", "probability")]);

function result(unit: string, value: number, low: number, high: number) {
  return {
    unit_id: unit,
    unit_name: `Unit ${unit}`,
    group_id: "G1",
    service_id: "S1",
    time_label: "static",
    indicator: "risk",
    mean: value,
    median: value,
    low,
    high,
    baseline: null,
    edge_effect_warning: false,
  };
}

describe("RunPage results map", () => {
  beforeEach(() => {
    recorder.current = new MapRecorder();
    stubApi({
      "GET /runs/r1": () => RUN,
      "GET /runs": () => [RUN],
      "GET /data-versions/1/layers/spatial_units": () => UNITS,
      "GET /data-versions/1/catalog": () => CATALOG,
      "GET /runs/r1/results": () => [result("U1", 0.42, 0.31, 0.55), result("U2", 0.7, 0.2, 0.9)],
      "GET /runs/r1/tables/unit_changes": () => [],
    });
  });

  it("shows intervals, a probability legend, and toggles uncertainty and data quality", async () => {
    renderWithSession(<RunPage />, { path: "/runs/r1", route: "/runs/:runId" });
    expect(await screen.findByText("0.42 (0.31–0.55)")).toBeInTheDocument();
    expect(screen.getByTestId("value-legend")).toHaveTextContent(
      "risk: median probability (fixed scale 0–1)",
    );
    const maps = recorder.current;
    if (!maps) throw new Error("no recorder");
    expect(screen.getByRole("columnheader", { name: "Median (90 % interval)" })).toBeVisible();
    expect(screen.getByText(/Colours show the median; the 90 % interval/)).toBeVisible();
    expect(
      maps.layers(MAP)[0]?.tooltip?.({
        type: "Feature",
        id: "U1",
        properties: {},
        geometry: { type: "Point", coordinates: [0, 0] },
      }),
    ).toBe("Unit U1, median (90 % interval): 0.42 (0.31–0.55)");

    // Defaults: no uncertainty map, no quality layer; the table still marks quality in words.
    expect(screen.queryByTestId("uncertainty-map")).not.toBeInTheDocument();
    expect(maps.layers(MAP).map((l) => l.id)).toEqual(["results"]);
    expect(screen.getByTestId("quality-hidden")).toHaveTextContent("1 of these units");
    expect(screen.getByText("data quality: estimated")).toBeInTheDocument();
    expect(screen.getByTestId("value-legend")).not.toHaveTextContent("hatched");

    await userEvent.click(screen.getByLabelText(/Uncertainty/));
    expect(screen.getByTestId("uncertainty-map")).toBeInTheDocument();
    expect(screen.getByTestId("uncertainty-legend")).toHaveTextContent(
      "width of the 90 % interval",
    );
    expect(maps.layers("Map of the interval width per core unit").map((l) => l.id)).toEqual([
      "widths",
    ]);

    await userEvent.click(screen.getByLabelText(/Data quality/));
    expect(maps.layers(MAP).map((l) => l.id)).toEqual(["results", "quality"]);
    expect(screen.queryByTestId("quality-hidden")).not.toBeInTheDocument();
    expect(screen.getByTestId("value-legend")).toHaveTextContent("Quality: estimated (hatched)");
  });
});

describe("RunPage samples size", () => {
  it("warns when the estimated samples file is above the limit", async () => {
    const big = { ...RUN, samples_estimate_bytes: 750_000_000, samples_limit_bytes: 500_000_000 };
    stubApi({
      "GET /runs/r1": () => big,
      "GET /runs": () => [big],
      "GET /data-versions/1/layers/spatial_units": () => UNITS,
      "GET /data-versions/1/catalog": () => CATALOG,
      "GET /runs/r1/results": () => [],
      "GET /runs/r1/tables/unit_changes": () => [],
    });
    renderWithSession(<RunPage />, { path: "/runs/r1", route: "/runs/:runId" });
    expect(await screen.findByTestId("samples-warning")).toHaveTextContent(
      "about 750 MB of samples (estimate before compression), above the warning limit of 500 MB",
    );
  });
});

describe("RunPage recorded-only interventions", () => {
  it("lists placeholders and an edge the scenario adds and then closes", async () => {
    const lines = [
      "new edge E-NEW N-A1-N-A5 (walk 10 min) (recorded only)",
      "new edge E-NEW is closed by the same scenario: added, then closed, so no net effect (OQ-30)",
    ];
    const withPlaceholders = { ...RUN, diagnostics: { recorded_only: lines } };
    stubApi({
      "GET /runs/r1": () => withPlaceholders,
      "GET /runs": () => [withPlaceholders],
      "GET /data-versions/1/layers/spatial_units": () => UNITS,
      "GET /data-versions/1/catalog": () => CATALOG,
      "GET /runs/r1/results": () => [],
      "GET /runs/r1/tables/unit_changes": () => [],
    });
    renderWithSession(<RunPage />, { path: "/runs/r1", route: "/runs/:runId" });
    expect(await screen.findByRole("heading", { name: /Recorded, no effect yet/ })).toBeVisible();
    const items = screen.getByTestId("recorded-only").querySelectorAll("li");
    expect([...items].map((li) => li.textContent)).toEqual([
      "new edge E-NEW N-A1-N-A5 (walking 10 min) (recorded only)",
      lines[1],
    ]);
  });

  it("translates the recorded lines and changes per unit into Greek", async () => {
    localStorage.setItem("sn-lang", "el");
    const lines = [
      "edge E01 walk travel_time -20 % (recorded only)",
      "unit A1 group G-OLD population +50 persons (recorded only)",
    ];
    const withPlaceholders = { ...RUN, diagnostics: { recorded_only: lines } };
    stubApi({
      "GET /runs/r1": () => withPlaceholders,
      "GET /runs": () => [withPlaceholders],
      "GET /data-versions/1/layers/spatial_units": () => UNITS,
      "GET /data-versions/1/catalog": () => CATALOG,
      "GET /runs/r1/results": () => [],
      "GET /runs/r1/tables/unit_changes": () => [
        { unit_id: "A2", details: ["F3: S-HC staff 4 -> 5", "edge E02 closed"] },
      ],
    });
    try {
      renderWithSession(<RunPage />, { path: "/runs/r1", route: "/runs/:runId" });
      const list = await screen.findByTestId("recorded-only");
      expect([...list.querySelectorAll("li")].map((li) => li.textContent)).toEqual([
        "τμήμα E01, πεζή: χρόνος διαδρομής -20 % (καταγράφεται μόνο)",
        "μονάδα A1, ομάδα G-OLD: πληθυσμός +50 άτομα (καταγράφεται μόνο)",
      ]);
      expect(screen.getByTestId("unit-changes")).toHaveTextContent(
        "A2: F3: S-HC προσωπικό 4 → 5; κλειστό τμήμα E02",
      );
    } finally {
      localStorage.removeItem("sn-lang");
    }
  });
});

describe("RunPage details", () => {
  it("says when nothing changed and which modes the hand-check skipped", async () => {
    const checked = {
      ...RUN,
      diagnostics: {
        hand_check: {
          baseline: { available: true, checked: 48, passed: 48 },
          scenario: { available: true, checked: 24, passed: 24, by_mode: { walk: 0, car: 24 } },
        },
      },
    };
    stubApi({
      "GET /runs/r1": () => checked,
      "GET /runs": () => [checked],
      "GET /data-versions/1/layers/spatial_units": () => UNITS,
      "GET /data-versions/1/catalog": () => CATALOG,
      "GET /runs/r1/results": () => [],
      "GET /runs/r1/tables/unit_changes": () => [{ unit_id: "U1", details: [] }],
    });
    renderWithSession(<RunPage />, { path: "/runs/r1", route: "/runs/:runId" });
    expect(await screen.findByTestId("no-changes")).toHaveTextContent("No changes");
    expect(screen.getByTestId("hand-check")).toHaveTextContent(
      "With the scenario: 24 of 24 match (car).",
    );
    expect(screen.getByTestId("hand-check-unchecked")).toHaveTextContent(
      "Not checked with the scenario: walking.",
    );
    expect(screen.getByTestId("results-table")).toHaveTextContent("Group 1");
    expect(screen.getByTestId("results-table")).toHaveTextContent("Service 1");
  });

  it("shows a translated page with a way back when the run does not exist", async () => {
    localStorage.setItem("sn-lang", "el");
    stubApi({
      "GET /runs/missing": () =>
        new Response(JSON.stringify({ detail: "run not found" }), { status: 404 }),
    });
    try {
      renderWithSession(<RunPage />, { path: "/runs/missing", route: "/runs/:runId" });
      expect(await screen.findByTestId("run-not-found")).toHaveTextContent(
        "Η εκτέλεση δεν βρέθηκε",
      );
      expect(screen.getByRole("link", { name: "Πίσω στα Σενάρια" })).toHaveAttribute(
        "href",
        "/scenarios",
      );
      expect(screen.queryByText("run not found")).toBeNull();
    } finally {
      localStorage.removeItem("sn-lang");
    }
  });
});

describe("RunPage provenance warnings", () => {
  it("warns about dirty code and refused reuse, and marks a drawn seed", async () => {
    const run = {
      ...RUN,
      code_version: "0123456789ab-dirty",
      code_version_dirty: true,
      reuse_refused: "run x: samples file of run x is missing",
      seed: 424242,
      seed_source: "drawn",
      environment: { python: "3.12.16", numpy: "2.3.0", platform: "Linux" },
    };
    stubApi({
      "GET /runs/r1": () => run,
      "GET /runs": () => [run],
      "GET /data-versions/1/layers/spatial_units": () => UNITS,
      "GET /data-versions/1/catalog": () => CATALOG,
      "GET /runs/r1/results": () => [],
      "GET /runs/r1/tables/unit_changes": () => [],
    });
    renderWithSession(<RunPage />, { path: "/runs/r1", route: "/runs/:runId" });
    expect(await screen.findByTestId("dirty-code")).toHaveTextContent(
      "uncommitted changes or of unknown version (0123456789ab-dirty)",
    );
    expect(screen.getByTestId("reuse-refused")).toHaveTextContent("failed the integrity check");
    expect(screen.getByText("424242 (drawn, none was given)")).toBeInTheDocument();
    expect(screen.getByText("python 3.12.16 · numpy 2.3.0 · platform Linux")).toBeInTheDocument();
  });
});
