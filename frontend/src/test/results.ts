import type { Feature } from "geojson";

import type { MapLayer } from "../map/MapView";

/** Fixtures and a MapView recorder shared by the results and comparison page tests. */

export const UNITS = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      id: "U1",
      properties: { quality: "verified_by_municipality" },
      geometry: null,
    },
    { type: "Feature", id: "U2", properties: { quality: "estimated" }, geometry: null },
  ],
};

export const CATALOG = {
  groups: [{ group_id: "G1", name: "Group 1" }],
  services: [{ service_id: "S1", name: "Service 1" }],
};

export function indicator(id: string, unit: string) {
  return { id, label: id, unit, deterministic: false, group_dependent: true };
}

export function run(id: string, indicators: ReturnType<typeof indicator>[], extra = {}) {
  return {
    id,
    scenario_id: "s1",
    scenario_name: `Scenario ${id}`,
    scenario_version: 1,
    data_version_id: 1,
    package_id: "demo",
    package_version: "1.0.0",
    status: "succeeded",
    progress: 100,
    error: null,
    can_cancel: false,
    code_version: "abc",
    model_id: "diagnostic-v0",
    model_version: "0",
    seed: 1,
    config: {},
    input_hash: "h",
    created_at: "2026-11-25T00:00:00Z",
    created_by: "analyst",
    finished_at: "2026-11-25T00:00:01Z",
    diagnostic: true,
    diagnostics: {},
    edge_effect_units: [],
    indicators,
    is_baseline: false,
    ...extra,
  };
}

/** Records the latest layers given to each MapView, by its accessible label. */
export class MapRecorder {
  maps = new Map<string, MapLayer[]>();

  record(label: string, layers: MapLayer[]) {
    this.maps.set(label, layers);
  }

  layers(label: string): MapLayer[] {
    const layers = this.maps.get(label);
    if (!layers)
      throw new Error(`no map labelled ${label}; have ${[...this.maps.keys()].join(", ")}`);
    return layers;
  }

  /** Fill colour of unit `id` on the first layer of map `label`. */
  fill(label: string, id: string): string | undefined {
    const layer = this.layers(label)[0];
    const feature = { type: "Feature", id, properties: {}, geometry: null } as unknown as Feature;
    return layer?.style?.(feature).fillColor;
  }
}
