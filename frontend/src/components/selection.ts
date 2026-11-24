import type { Schemas } from "../api/client";

export interface Selection {
  group: string;
  service: string;
  indicator: string;
}

export function defaultSelection(
  catalog: Schemas["CatalogOut"],
  indicators: Schemas["IndicatorOut"][],
): Selection {
  return {
    group: catalog.groups[0]?.group_id ?? "",
    service: catalog.services[0]?.service_id ?? "",
    indicator:
      indicators.find((i) => i.id === "travel_time_walk_min")?.id ?? indicators[0]?.id ?? "",
  };
}
