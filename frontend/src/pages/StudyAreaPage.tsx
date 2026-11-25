import type { Feature, FeatureCollection } from "geojson";
import { useEffect, useMemo, useState } from "react";

import { getLayer } from "../api/client";
import { useSession } from "../app/session";
import { ErrorMessage } from "../components/ErrorMessage";
import { Legend } from "../components/Legend";
import { label } from "../components/labels";
import { useT } from "../i18n/context";
import { MapView, type MapLayer } from "../map/MapView";
import { COLOURS, edgeStyle, facilityPoint, qualityOverlay, unitStyle } from "../map/styles";

const LAYERS = ["municipalities", "spatial_units", "network_edges", "facilities"] as const;
type LayerName = (typeof LAYERS)[number];

const HIDDEN = new Set(["population", "services", "edge_effect_details", "processing_note"]);
/** Display order of attributes; others follow alphabetically. */
const ORDER = [
  "unit_id",
  "facility_id",
  "edge_id",
  "node_id",
  "municipality_id",
  "name",
  "facility_type",
  "role",
  "quality",
  "valid_from",
  "valid_to",
  "closed",
];
const INPUTS = ["places", "staff", "throughput"];

function rank(key: string): number {
  const i = ORDER.indexOf(key);
  return i === -1 ? ORDER.length : i;
}

export function StudyAreaPage() {
  const { t } = useT();
  const { activeDataVersion: dv, config } = useSession();
  const [layers, setLayers] = useState<Partial<Record<LayerName, FeatureCollection>>>({});
  const [selected, setSelected] = useState<{ layer: LayerName; feature: Feature } | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!dv) return;
    Promise.all(LAYERS.map((l) => getLayer(dv.id, l)))
      .then((all) => {
        setLayers(Object.fromEntries(LAYERS.map((l, i) => [l, all[i]])));
      })
      .catch(setError);
  }, [dv]);

  const mapLayers = useMemo<MapLayer[]>(() => {
    const out: MapLayer[] = [];
    const select = (layer: LayerName) => (feature: Feature) => {
      setSelected({ layer, feature });
    };
    const name = (f: Feature) => String(f.id ?? "");
    if (layers.spatial_units) {
      out.push({
        id: "units",
        data: layers.spatial_units,
        style: unitStyle,
        tooltip: name,
        onSelect: select("spatial_units"),
      });
      out.push({
        id: "quality",
        data: layers.spatial_units,
        style: qualityOverlay,
        interactive: false,
      });
    }
    if (layers.network_edges) {
      out.push({
        id: "edges",
        data: layers.network_edges,
        style: (f) => edgeStyle(f),
        tooltip: name,
        onSelect: select("network_edges"),
      });
    }
    if (layers.facilities) {
      out.push({
        id: "facilities",
        data: layers.facilities,
        point: (f) => facilityPoint(f),
        tooltip: name,
        onSelect: select("facilities"),
      });
    }
    return out;
  }, [layers]);

  if (!dv) {
    return (
      <section>
        <h2>{t("study.title")}</h2>
        <p role="status">{t("study.no_data")}</p>
      </section>
    );
  }

  const municipalities = [
    ...((dv.study_area.core_municipalities as string[] | undefined) ?? []).map((m) => [m, "core"]),
    ...((dv.study_area.buffer_municipalities as string[] | undefined) ?? []).map((m) => [
      m,
      "buffer",
    ]),
  ];
  const layerNames = ["boundaries", "population", "network", "facilities", "transit"];

  return (
    <section aria-labelledby="study-title">
      <h2 id="study-title">{t("study.title")}</h2>
      <p>
        {t("study.package", { package: dv.package_id, version: dv.version, created: dv.created })}
        {dv.synthetic && <strong> {t("study.synthetic")}</strong>}
      </p>
      {dv.edge_effect_units.length > 0 && (
        <p className="banner banner--warning" role="note">
          {t("study.edge_effect", { units: dv.edge_effect_units.join(", ") })}
        </p>
      )}
      <ErrorMessage error={error} />
      <div className="map-grid">
        <MapView
          label={t("study.map_label")}
          layers={mapLayers}
          basemap={config?.basemap ?? "blank"}
        />
        <aside aria-live="polite" className="panel">
          <h3>{t("study.selected")}</h3>
          {selected ? (
            <FeatureAttributes layer={selected.layer} feature={selected.feature} />
          ) : (
            <p>{t("study.select_hint")}</p>
          )}
        </aside>
      </div>
      <Legend
        title={t("legend.title")}
        items={[
          { colour: "#cfe3f1", label: t("legend.core_unit") },
          {
            colour: "#d9d9d9",
            outline: COLOURS.grey,
            dashed: true,
            label: t("legend.buffer_unit"),
          },
          { pattern: "hatch", label: t("legend.estimated") },
          { pattern: "dots", label: t("legend.open_data") },
          { colour: "#cfe3f1", outline: COLOURS.orange, label: t("legend.edge_effect") },
          { colour: COLOURS.blue, label: t("legend.facility_verified") },
          {
            colour: "#ffffff",
            outline: COLOURS.grey,
            dashed: true,
            label: t("legend.facility_closed"),
          },
        ]}
      />
      <h3>{t("study.coverage_title")}</h3>
      <table>
        <caption className="sr-only">{t("study.coverage_title")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("study.municipality")}</th>
            <th scope="col">{t("study.role")}</th>
            {layerNames.map((l) => (
              <th scope="col" key={l}>
                {label(t, "layer", l)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {municipalities.map(([m, role]) => (
            <tr key={m}>
              <th scope="row">{m}</th>
              <td>{label(t, "role", role)}</td>
              {layerNames.map((l) => {
                const c = dv.coverage.find((x) => x.municipality_id === m && x.layer === l);
                return (
                  <td key={l} className={`coverage coverage--${c?.status ?? "missing"}`}>
                    {label(t, "coverage", c?.status ?? "missing")}
                    {c && <span className="muted"> ({c.layer_version})</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <h3>{t("study.features_title")}</h3>
      {(["spatial_units", "facilities", "network_edges"] as const).map((l) => (
        <details key={l}>
          <summary>
            {label(t, "layer", l)} ({layers[l]?.features.length ?? 0})
          </summary>
          <ul className="feature-list">
            {layers[l]?.features.map((f) => (
              <li key={String(f.id)}>
                <button
                  type="button"
                  onClick={() => {
                    setSelected({ layer: l, feature: f });
                  }}
                >
                  {String(f.id)} · {(f.properties as { name?: string } | null)?.name ?? ""}
                </button>
              </li>
            ))}
          </ul>
        </details>
      ))}
      <h3>{t("study.changelog")}</h3>
      <ul>
        {dv.changelog.map((c) => (
          <li key={String(c.version)}>
            <strong>{String(c.version)}</strong> ({String(c.date)}): {String(c.changes)}
          </li>
        ))}
      </ul>
      <p className="muted">
        {t("study.processing_notes", { notes: dv.processing_notes.join(", ") })}
      </p>
      {dv.layer_licences && dv.layer_licences.length > 0 && (
        <table data-testid="layer-licences">
          <caption>{t("study.licences_title")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("study.layer")}</th>
              <th scope="col">{t("study.licence")}</th>
              <th scope="col">{t("study.attribution")}</th>
            </tr>
          </thead>
          <tbody>
            {dv.layer_licences.map((l) => (
              <tr key={l.layer}>
                <th scope="row">{label(t, "layer", l.layer)}</th>
                <td>{l.licence}</td>
                <td>{l.attribution}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function show(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return value.toString();
  return JSON.stringify(value);
}

function FeatureAttributes({ layer, feature }: { layer: LayerName; feature: Feature }) {
  const { t } = useT();
  const props = (feature.properties ?? {}) as Record<string, unknown>;
  const details = props.edge_effect_details as string[] | undefined;
  return (
    <div data-testid="feature-attributes">
      <p>
        <strong>{label(t, "layer", layer)}</strong> {String(feature.id)}
      </p>
      {props.edge_effect_warning === true && (
        <p className="banner banner--warning">{details?.join(" ")}</p>
      )}
      <dl>
        {Object.entries(props)
          .filter(([k]) => !HIDDEN.has(k) && !k.startsWith("edge_effect"))
          .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
          .map(([k, v]) => (
            <div key={k} className="dl-row">
              <dt>{label(t, "attr", k)}</dt>
              <dd>
                {v === null
                  ? "—"
                  : k === "role" || k === "quality"
                    ? label(t, k, show(v))
                    : show(v)}
              </dd>
            </div>
          ))}
        {props.services !== undefined && (
          <div className="dl-row">
            <dt>{label(t, "attr", "services")}</dt>
            <dd>
              {Object.entries(props.services as Record<string, Record<string, number | null>>)
                .map(
                  ([s, c]) =>
                    `${s}: ${INPUTS.map((k) => [k, c[k] ?? null] as const)
                      .map(([k, v]) => `${label(t, "attr", k)} ${v === null ? "—" : String(v)}`)
                      .join(", ")}`,
                )
                .join("; ")}
            </dd>
          </div>
        )}
        {props.population !== undefined && (
          <div className="dl-row">
            <dt>{label(t, "attr", "population")}</dt>
            <dd>
              {Object.entries(props.population as Record<string, number>)
                .map(([g, n]) => `${g}: ${String(n)}`)
                .join(", ")}
            </dd>
          </div>
        )}
      </dl>
    </div>
  );
}
