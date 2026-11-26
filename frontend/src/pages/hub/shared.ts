import { useCallback, useEffect, useState } from "react";

import { unwrap } from "../../api/client";
import { hubApi, type CoverageRow } from "../../api/hub";

export type Filter = "all" | "onboarded" | "not_onboarded";

export const COVERAGE_LAYERS = [
  "boundaries",
  "spatial_units",
  "population",
  "network",
  "facilities",
  "transit",
  "susceptibility",
] as const;

/** A JSON property as display text (objects as JSON, empty as an empty string). */
export function text(value: unknown): string {
  if (value === null || value === undefined) return "";
  return typeof value === "string" ? value : JSON.stringify(value);
}

/** The rows of the coverage matrix, optionally only (not) onboarded municipalities. */
export function useCoverage(filter: Filter) {
  const [rows, setRows] = useState<CoverageRow[]>([]);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(() => {
    const onboarded = filter === "all" ? null : filter === "onboarded";
    unwrap(hubApi.GET("/hub/coverage", { params: { query: { onboarded } } }))
      .then(setRows)
      .catch(setError);
  }, [filter]);
  useEffect(load, [load]);
  return { rows, error, reload: load };
}
