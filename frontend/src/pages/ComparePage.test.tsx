import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SEQUENTIAL, UNCERTAINTY } from "../map/styles";
import { CATALOG, MapRecorder, UNITS, indicator, run } from "../test/results";
import { renderWithSession, stubApi } from "../test/utils";
import { ComparePage } from "./ComparePage";

const recorder = vi.hoisted(() => ({ current: null as MapRecorder | null }));

vi.mock("../map/MapView", () => ({
  MapView: ({ label, layers }: { label: string; layers: never[] }) => {
    recorder.current?.record(label, layers);
    return <div data-testid="map" aria-label={label} />;
  },
}));

function row(unit: string, a: number, b: number) {
  return {
    unit_id: unit,
    unit_name: `Unit ${unit}`,
    group_id: "G1",
    service_id: "S1",
    indicator: "x",
    a: { value: a, low: a - 0.5, high: a + 0.5 },
    b: { value: b, low: b - 1, high: b + 1 },
    difference: a - b,
    edge_effect_warning: false,
  };
}

function stub(unit: string, crossDataVersion: boolean) {
  const ind = [indicator("x", unit)];
  stubApi({
    "GET /runs/a/compare": () => ({
      run_a: run("a", ind),
      run_b: run(
        "b",
        ind,
        crossDataVersion ? { data_version_id: 2, package_version: "1.1.0" } : {},
      ),
      rows: [row("U1", 2, 2), row("U2", 1, 10)],
      label: crossDataVersion ? "data 1.0.0 vs 1.1.0" : "scenario vs baseline",
      cross_data_version: crossDataVersion,
    }),
    "GET /data-versions/1/layers/spatial_units": () => UNITS,
    "GET /data-versions/1/catalog": () => CATALOG,
  });
}

function show() {
  renderWithSession(<ComparePage />, { path: "/runs/a/compare", route: "/runs/:runId/compare" });
}

describe("ComparePage", () => {
  beforeEach(() => {
    recorder.current = new MapRecorder();
  });

  it.each([false, true])(
    "colours both maps with one shared scale and one legend (cross data version: %s)",
    async (cross) => {
      stub("min", cross);
      show();
      const legends = await screen.findAllByTestId("shared-legend");
      expect(legends).toHaveLength(1);
      expect(legends[0]).toHaveTextContent("one colour scale for A and B");
      const maps = recorder.current;
      if (!maps) throw new Error("no recorder");
      // Equal values: equal colours on A and B. The scale spans both runs (1 … 10), so B's 10 is
      // the darkest class and A's 1 the lightest.
      expect(maps.fill("A: Scenario a", "U1")).toBe(maps.fill("B: Scenario b", "U1"));
      expect(maps.fill("A: Scenario a", "U2")).toBe(SEQUENTIAL[0]);
      expect(maps.fill("B: Scenario b", "U2")).toBe(SEQUENTIAL[4]);
      expect(within(legends[0] as HTMLElement).getByText("> 8.2")).toBeInTheDocument();
      // The table shows every value with its interval.
      expect(screen.getAllByText("10 min (9–11)")).toHaveLength(1);
    },
  );

  it("uses a fixed 0–1 scale labelled as a probability", async () => {
    stub("probability", false);
    show();
    const legend = await screen.findByTestId("shared-legend");
    expect(legend).toHaveTextContent("probability (fixed scale 0–1)");
    expect(within(legend).getByText("≤ 0.2")).toBeInTheDocument();
    expect(within(legend).getByText("> 0.8")).toBeInTheDocument();
  });

  it("switches both maps to the shared interval-width scale", async () => {
    stub("min", false);
    show();
    await screen.findByTestId("shared-legend");
    await userEvent.click(screen.getByLabelText(/Uncertainty/));
    expect(screen.getByTestId("shared-legend")).toHaveTextContent("width of the 90 % interval");
    const maps = recorder.current;
    if (!maps) throw new Error("no recorder");
    // A's intervals are 1 wide, B's 2 wide: lightest and darkest class of one shared scale.
    expect(maps.fill("A: Scenario a", "U1")).toBe(UNCERTAINTY[0]);
    expect(maps.fill("B: Scenario b", "U1")).toBe(UNCERTAINTY[4]);
  });
});
