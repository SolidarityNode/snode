import type { Feature, FeatureCollection } from "geojson";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { api, getCatalog, getLayer, unwrap, type Schemas } from "../api/client";
import { useSession } from "../app/session";
import { DiagnosticBanner } from "../components/DiagnosticBanner";
import { ErrorMessage } from "../components/ErrorMessage";
import { IntervalValue } from "../components/IntervalValue";
import { Legend } from "../components/Legend";
import { ResultSelectors } from "../components/ResultSelectors";
import { defaultSelection, type Selection } from "../components/selection";
import { label, num } from "../components/labels";
import { useT } from "../i18n/context";
import { MapView, type MapLayer } from "../map/MapView";
import {
  COLOURS,
  DIVERGING,
  SEQUENTIAL,
  classBreaks,
  divergingColour,
  sequentialColour,
} from "../map/styles";

type Row = Schemas["CompareRow"];

export function ComparePage() {
  const { t, lang } = useT();
  const { runId = "" } = useParams();
  const [search] = useSearchParams();
  const other = search.get("with");
  const { config } = useSession();
  const [data, setData] = useState<Schemas["CompareOut"] | null>(null);
  const [units, setUnits] = useState<FeatureCollection | null>(null);
  const [catalog, setCatalog] = useState<Schemas["CatalogOut"] | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    unwrap(
      api.GET("/runs/{run_id}/compare", {
        params: { path: { run_id: runId }, query: other ? { with: other } : {} },
      }),
    )
      .then(async (c) => {
        const [u, cat] = await Promise.all([
          getLayer(c.run_a.data_version_id, "spatial_units"),
          getCatalog(c.run_a.data_version_id),
        ]);
        setData(c);
        setUnits(u);
        setCatalog(cat);
        setSelection(defaultSelection(cat, c.run_a.indicators));
      })
      .catch(setError);
  }, [runId, other]);

  const rows = useMemo<Row[]>(
    () =>
      data && selection
        ? data.rows.filter(
            (r) =>
              r.group_id === selection.group &&
              r.service_id === selection.service &&
              r.indicator === selection.indicator,
          )
        : [],
    [data, selection],
  );

  const values = rows.flatMap((r) => [r.a.value, r.b.value]).filter((v): v is number => v !== null);
  const breaks = classBreaks(values, SEQUENTIAL.length);
  const maxAbs = Math.max(0, ...rows.map((r) => Math.abs(r.difference ?? 0)));

  const layers = useMemo(() => {
    if (!units) return { a: [], b: [], diff: [] };
    const byUnit = new Map(rows.map((r) => [r.unit_id, r]));
    const make = (
      id: string,
      fill: (r: Row) => string | null,
      tip: (r: Row) => string,
    ): MapLayer[] => [
      {
        id,
        data: units,
        style: (f: Feature) => {
          const r = byUnit.get(String(f.id));
          const colour = r ? fill(r) : null;
          return {
            color: r?.edge_effect_warning ? COLOURS.orange : COLOURS.dark,
            weight: r?.edge_effect_warning ? 4 : 1,
            fillColor: colour ?? "#d9d9d9",
            fillOpacity: 0.8,
            dashArray: r ? "" : "6 4",
          };
        },
        tooltip: (f: Feature) => {
          const r = byUnit.get(String(f.id));
          return r ? `${String(f.id)}: ${tip(r)}` : `${String(f.id)}: ${t("results.not_reported")}`;
        },
      },
    ];
    return {
      a: make(
        "a",
        (r) => (r.a.value === null ? null : sequentialColour(r.a.value, breaks)),
        (r) => num(r.a.value, lang),
      ),
      b: make(
        "b",
        (r) => (r.b.value === null ? null : sequentialColour(r.b.value, breaks)),
        (r) => num(r.b.value, lang),
      ),
      diff: make(
        "diff",
        (r) => (r.difference === null ? null : divergingColour(r.difference, maxAbs)),
        (r) => num(r.difference, lang),
      ),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- breaks/maxAbs derive from rows
  }, [units, rows, lang, t]);

  if (!data || !catalog || !selection) {
    return (
      <section>
        <h2>{t("compare.title")}</h2>
        <ErrorMessage error={error} />
        {!error && <p role="status">{t("common.loading")}</p>}
        <Link to={`/runs/${runId}`}>{t("compare.back")}</Link>
      </section>
    );
  }

  const unit = data.run_a.indicators.find((i) => i.id === selection.indicator)?.unit ?? "";
  const basemap = config?.basemap ?? "blank";

  return (
    <section aria-labelledby="compare-title">
      <h2 id="compare-title">{t("compare.title")}</h2>
      {(data.run_a.diagnostic || data.run_b.diagnostic) && <DiagnosticBanner />}
      <p className={data.cross_data_version ? "banner banner--warning" : ""} role="note">
        {data.cross_data_version ? t("compare.cross", { label: data.label }) : data.label}
      </p>
      <p>
        {t("compare.a", { name: data.run_a.scenario_name, version: data.run_a.package_version })} ·{" "}
        {t("compare.b", { name: data.run_b.scenario_name, version: data.run_b.package_version })} ·{" "}
        <Link to={`/runs/${data.run_a.id}`}>{t("compare.back")}</Link>
      </p>
      <ResultSelectors
        catalog={catalog}
        indicators={data.run_a.indicators}
        value={selection}
        onChange={setSelection}
      />
      <div className="compare-grid">
        <div>
          <h3>{t("compare.map_a", { name: data.run_a.scenario_name })}</h3>
          <MapView
            label={t("compare.map_a", { name: data.run_a.scenario_name })}
            layers={layers.a}
            basemap={basemap}
            height={300}
          />
        </div>
        <div>
          <h3>{t("compare.map_b", { name: data.run_b.scenario_name })}</h3>
          <MapView
            label={t("compare.map_b", { name: data.run_b.scenario_name })}
            layers={layers.b}
            basemap={basemap}
            height={300}
          />
        </div>
        <div>
          <h3>{t("compare.map_diff")}</h3>
          <MapView
            label={t("compare.map_diff")}
            layers={layers.diff}
            basemap={basemap}
            height={300}
          />
        </div>
      </div>
      <Legend
        title={t("compare.legend_diff", { unit })}
        items={[
          {
            colour: DIVERGING[0] ?? "#f7f7f7",
            label: t("compare.lower", { value: num(-maxAbs, lang) }),
          },
          { colour: DIVERGING[3] ?? "#f7f7f7", label: t("compare.no_difference") },
          {
            colour: DIVERGING[6] ?? "#f7f7f7",
            label: t("compare.higher", { value: num(maxAbs, lang) }),
          },
          { colour: "#ffffff", outline: COLOURS.orange, label: t("legend.edge_effect") },
        ]}
      />
      <table data-testid="compare-table">
        <caption>
          {t("results.table_caption", {
            indicator: label(t, "indicator", selection.indicator),
            group: selection.group,
            service: selection.service,
          })}
        </caption>
        <thead>
          <tr>
            <th scope="col">{t("results.unit")}</th>
            <th scope="col">{t("compare.col_a")}</th>
            <th scope="col">{t("compare.col_b")}</th>
            <th scope="col">{t("compare.col_diff")}</th>
            <th scope="col">{t("results.warnings")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.unit_id}>
              <th scope="row">{r.unit_name}</th>
              <td>
                <IntervalValue value={r.a.value} low={r.a.low} high={r.a.high} unit={unit} />
              </td>
              <td>
                <IntervalValue value={r.b.value} low={r.b.low} high={r.b.high} unit={unit} />
              </td>
              <td>{num(r.difference, lang)}</td>
              <td>{r.edge_effect_warning ? `⚠ ${t("results.edge_effect")}` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">{t("compare.difference_note")}</p>
    </section>
  );
}
