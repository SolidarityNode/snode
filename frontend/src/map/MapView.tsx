import L from "leaflet";
import type { Feature, FeatureCollection } from "geojson";
import { useEffect, useRef } from "react";

import { useT } from "../i18n/context";

export interface MapLayer {
  id: string;
  data: FeatureCollection;
  style?: (feature: Feature) => L.PathOptions;
  point?: (feature: Feature) => L.CircleMarkerOptions;
  tooltip?: (feature: Feature) => string;
  onSelect?: (feature: Feature) => void;
  interactive?: boolean;
}

interface Props {
  label: string;
  layers: MapLayer[];
  basemap: "osm" | "blank";
  height?: number;
}

/**
 * Leaflet map (ADR 0007). Display only: layers come from the API already in EPSG:4326.
 * Keyboard: the map container is focusable (arrow keys pan, +/- zoom). Every page with a map
 * also lists its features as text, so nothing is available on the map only.
 */
export function MapView({ label, layers, basemap, height = 420 }: Props) {
  const { t } = useT();
  const container = useRef<HTMLDivElement | null>(null);
  const map = useRef<L.Map | null>(null);
  const group = useRef<L.FeatureGroup | null>(null);
  const fitted = useRef(false);

  useEffect(() => {
    if (!container.current || map.current) {
      return;
    }
    const m = L.map(container.current, { keyboard: true, zoomSnap: 0.5 });
    m.attributionControl.setPrefix(false);
    if (basemap === "osm") {
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(m);
    } else {
      m.attributionControl.addAttribution(t("map.blank_basemap"));
    }
    m.setView([35, 20], 11);
    group.current = L.featureGroup().addTo(m);
    map.current = m;
    // Leaflet caches the container size; refit when the layout changes it (grids, panels).
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => {
            m.invalidateSize();
            const bounds = group.current?.getBounds();
            if (bounds?.isValid()) m.fitBounds(bounds, { padding: [12, 12] });
          });
    observer?.observe(container.current);
    return () => {
      observer?.disconnect();
      m.remove();
      map.current = null;
      group.current = null;
      fitted.current = false;
    };
  }, [basemap, t]);

  useEffect(() => {
    const g = group.current;
    const m = map.current;
    if (!g || !m) {
      return;
    }
    g.clearLayers();
    for (const layer of layers) {
      const geo = L.geoJSON(layer.data, {
        interactive: layer.interactive ?? true,
        ...(layer.style ? { style: (f) => (f ? (layer.style?.(f as Feature) ?? {}) : {}) } : {}),
        pointToLayer: (f: Feature, latlng) => L.circleMarker(latlng, layer.point?.(f) ?? {}),
        onEachFeature: (f, lyr) => {
          if (layer.tooltip) {
            lyr.bindTooltip(layer.tooltip(f as Feature), { sticky: true });
          }
          if (layer.onSelect) {
            const select = layer.onSelect;
            lyr.on("click", () => {
              select(f as Feature);
            });
          }
        },
      });
      g.addLayer(geo);
    }
    const bounds = g.getBounds();
    if (!fitted.current && bounds.isValid()) {
      m.invalidateSize();
      m.fitBounds(bounds, { padding: [12, 12] });
      fitted.current = true;
    }
  }, [layers]);

  return (
    <div
      ref={container}
      className="map"
      style={{ height }}
      role="region"
      aria-label={label}
      tabIndex={0}
    />
  );
}
