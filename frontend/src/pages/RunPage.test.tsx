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
