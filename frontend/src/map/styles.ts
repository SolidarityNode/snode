import type { Feature } from "geojson";
import type L from "leaflet";

/** Okabe–Ito colours (readable with the common forms of colour blindness). */
export const COLOURS = {
  orange: "#E69F00",
  vermillion: "#D55E00",
  blue: "#0072B2",
  sky: "#56B4E9",
  green: "#009E73",
  grey: "#7a7a7a",
  dark: "#1d2433",
};

/** Viridis, 5 classes, light to dark (sequential, colour-blind safe). */
export const SEQUENTIAL = ["#fde725", "#5ec962", "#21918c", "#3b528b", "#440154"];
/** PuOr, 7 classes (diverging, colour-blind safe): negative orange, positive purple. */
export const DIVERGING = [
  "#b35806",
  "#f1a340",
  "#fee0b6",
  "#f7f7f7",
  "#d8daeb",
  "#998ec3",
  "#542788",
];

type Props = Record<string, unknown>;

function props(f: Feature): Props {
  return f.properties ?? {};
}

export function unitStyle(f: Feature): L.PathOptions {
  const p = props(f);
  const buffer = p.role === "buffer";
  const warned = p.edge_effect_warning === true;
  return {
    color: warned ? COLOURS.orange : buffer ? COLOURS.grey : COLOURS.dark,
    weight: warned ? 4 : buffer ? 1.5 : 2,
    dashArray: buffer ? "6 4" : "",
    fillColor: buffer ? "#d9d9d9" : "#cfe3f1",
    fillOpacity: 0.5,
  };
}

/** Overlay marking quality: hatching for estimated, dots for open data, none for verified. */
export function qualityOverlay(f: Feature): L.PathOptions {
  const q = props(f).quality;
  const pattern = q === "estimated" ? "url(#sn-hatch)" : q === "open_data" ? "url(#sn-dots)" : "";
  return { stroke: false, fillColor: pattern, fillOpacity: pattern ? 0.35 : 0 };
}

export function facilityPoint(f: Feature, highlighted = false): L.CircleMarkerOptions {
  const p = props(f);
  const closed = p.closed === true;
  const verified = p.quality === "verified_by_municipality";
  return {
    radius: highlighted ? 10 : 8,
    color: closed ? COLOURS.grey : highlighted ? COLOURS.vermillion : COLOURS.blue,
    weight: highlighted ? 4 : 2,
    dashArray: closed ? "2 3" : "",
    fillColor: closed ? "#ffffff" : highlighted ? COLOURS.vermillion : COLOURS.blue,
    fillOpacity: verified && !closed ? 0.9 : 0.2,
  };
}

export function edgeStyle(f: Feature, closed = false): L.PathOptions {
  const p = props(f);
  return {
    color: closed ? COLOURS.vermillion : COLOURS.dark,
    weight: closed ? 6 : p.closable === true ? 4 : 2.5,
    dashArray: closed ? "6 6" : "",
    opacity: 0.85,
  };
}

/**
 * Blues, 5 classes, narrow to wide interval (sequential, colour-blind safe). Used only for the
 * uncertainty map, so it never looks like the value scale (viridis) or the data-quality patterns
 * (hatching, dots).
 */
export const UNCERTAINTY = ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"];
/** Fixed class breaks of probability outputs (0–1, five classes of 0.2). */
export const PROBABILITY_BREAKS = [0.2, 0.4, 0.6, 0.8];
/** Fill of units without a reported value. */
export const NOT_REPORTED = "#d9d9d9";

/** A classed colour scale: `breaks.length + 1` classes, coloured from `colours`. */
export interface ColourScale {
  colours: string[];
  breaks: number[];
  /** Fixed 0–1 scale of a probability output (labelled as a probability). */
  probability: boolean;
}

/** Equal-interval class breaks between min and max (display only). */
export function classBreaks(values: number[], classes: number): number[] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return [min];
  return Array.from({ length: classes - 1 }, (_, i) => min + ((i + 1) * (max - min)) / classes);
}

/**
 * Scale of central values. Probability outputs always use the fixed 0–1 scale; other outputs use
 * equal intervals over `values`. Comparison screens pass the values of **both** runs, so both
 * maps share one scale and one legend.
 */
export function valueScale(values: number[], probability: boolean): ColourScale {
  return probability
    ? { colours: SEQUENTIAL, breaks: PROBABILITY_BREAKS, probability: true }
    : { colours: SEQUENTIAL, breaks: classBreaks(values, SEQUENTIAL.length), probability: false };
}

/** Scale of interval widths (`high − low`) for the uncertainty map. */
export function widthScale(widths: number[]): ColourScale {
  return {
    colours: UNCERTAINTY,
    breaks: classBreaks(widths, UNCERTAINTY.length),
    probability: false,
  };
}

/** Width of an interval, or `null` when either end is missing. */
export function intervalWidth(low: number | null, high: number | null): number | null {
  return low === null || high === null ? null : Math.max(0, high - low);
}

export function scaleColour(scale: ColourScale, value: number | null): string {
  if (value === null) return NOT_REPORTED;
  const index = scale.breaks.filter((b) => value > b).length;
  return scale.colours[Math.min(index, scale.colours.length - 1)] ?? COLOURS.grey;
}

/** Number of classes a scale actually uses (one when every value is the same). */
export function scaleClasses(scale: ColourScale): number {
  return Math.min(scale.colours.length, scale.breaks.length + 1);
}

export function divergingColour(value: number, maxAbs: number): string {
  if (maxAbs === 0 || value === 0) return DIVERGING[3] ?? "#f7f7f7";
  const step = Math.min(3, Math.ceil((Math.abs(value) / maxAbs) * 3));
  return (value < 0 ? DIVERGING[3 - step] : DIVERGING[3 + step]) ?? "#f7f7f7";
}

/** Style of a unit on a results map: fill from a scale, orange outline for edge effect. */
export function resultStyle(reported: boolean, warned: boolean, fill: string): L.PathOptions {
  return {
    color: warned ? COLOURS.orange : COLOURS.dark,
    weight: warned ? 4 : 1,
    fillColor: reported ? fill : NOT_REPORTED,
    fillOpacity: 0.8,
    dashArray: reported ? "" : "6 4",
  };
}
