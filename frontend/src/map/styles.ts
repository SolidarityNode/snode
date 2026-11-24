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

/** Equal-interval class breaks between min and max (display only). */
export function classBreaks(values: number[], classes: number): number[] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return [min];
  return Array.from({ length: classes - 1 }, (_, i) => min + ((i + 1) * (max - min)) / classes);
}

export function sequentialColour(value: number, breaks: number[]): string {
  const index = breaks.filter((b) => value > b).length;
  return SEQUENTIAL[Math.min(index, SEQUENTIAL.length - 1)] ?? COLOURS.grey;
}

export function divergingColour(value: number, maxAbs: number): string {
  if (maxAbs === 0 || value === 0) return DIVERGING[3] ?? "#f7f7f7";
  const step = Math.min(3, Math.ceil((Math.abs(value) / maxAbs) * 3));
  return (value < 0 ? DIVERGING[3 - step] : DIVERGING[3 + step]) ?? "#f7f7f7";
}
