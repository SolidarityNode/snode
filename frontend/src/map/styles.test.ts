import { describe, expect, it } from "vitest";

import { intervalLabel, intervalText } from "../components/labels";
import en from "../i18n/en.json";
import { format, type MessageKey } from "../i18n/context";
import {
  PROBABILITY_BREAKS,
  SEQUENTIAL,
  UNCERTAINTY,
  intervalWidth,
  scaleColour,
  valueScale,
  widthScale,
} from "./styles";

const t = (key: MessageKey, vars?: Record<string, string | number>) => format(en[key], vars);

describe("colour scales", () => {
  it("uses a fixed 0–1 scale for probabilities, whatever the values", () => {
    const scale = valueScale([0.41, 0.43], true);
    expect(scale.probability).toBe(true);
    expect(scale.breaks).toEqual(PROBABILITY_BREAKS);
    expect(scaleColour(scale, 0.05)).toBe(SEQUENTIAL[0]);
    expect(scaleColour(scale, 0.42)).toBe(SEQUENTIAL[2]);
    expect(scaleColour(scale, 0.95)).toBe(SEQUENTIAL[4]);
  });

  it("builds one scale from the values of both runs", () => {
    const a = [1, 2];
    const b = [9, 10];
    const shared = valueScale([...a, ...b], false);
    // Equal values get equal colours on either map, and the range covers both runs.
    expect(scaleColour(shared, 2)).toBe(SEQUENTIAL[0]);
    expect(scaleColour(shared, 10)).toBe(SEQUENTIAL[4]);
    expect(shared.breaks.at(-1)).toBeGreaterThan(2);
  });

  it("colours interval widths with their own palette", () => {
    expect(intervalWidth(0.31, 0.55)).toBeCloseTo(0.24);
    expect(intervalWidth(null, 1)).toBeNull();
    const scale = widthScale([0, 0.1, 0.4]);
    expect(UNCERTAINTY).not.toContain(scaleColour(valueScale([0, 1], false), 0.5));
    expect(scaleColour(scale, 0.4)).toBe(UNCERTAINTY[4]);
  });
});

describe("intervalText", () => {
  it("shows the central value with its interval", () => {
    expect(intervalText(t, "en", 0.42, 0.31, 0.55)).toBe("0.42 (0.31–0.55)");
    expect(intervalText(t, "en", 12.5, 10, 14, "min")).toBe("12.5 min (10–14)");
    expect(intervalText(t, "en", 0.42, 0.31, 0.55, "probability")).toBe("0.42 (0.31–0.55)");
  });

  it("says when a value is deterministic or missing", () => {
    expect(intervalText(t, "en", 3, 3, 3, "count")).toBe("3 count (deterministic, no uncertainty)");
    expect(intervalText(t, "en", null, null, null)).toBe("not available");
  });
});

describe("intervalLabel", () => {
  it("names the interval from the run's quantile levels", () => {
    expect(intervalLabel(t, "en", [0.05, 0.95])).toBe("90 % interval");
    expect(intervalLabel(t, "en", [0.25, 0.75])).toBe("50 % interval");
    expect(intervalLabel(t, "en", [0.1, 0.95])).toBe("10–95 % quantile interval");
    expect(intervalLabel(t, "en", null)).toBe("interval (levels not recorded)");
  });
});
