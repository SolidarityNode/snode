import type { Feature, FeatureCollection } from "geojson";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { api, getCatalog, getLayer, unwrap, type Schemas } from "../api/client";
import { useSession } from "../app/session";
import { DiagnosticBanner } from "../components/DiagnosticBanner";
import { ErrorMessage } from "../components/ErrorMessage";
import { IntervalValue } from "../components/IntervalValue";
import { Legend } from "../components/Legend";
import { MapOptions, type MapOptionsValue } from "../components/MapOptions";
import { ResultSelectors } from "../components/ResultSelectors";
import { ScaleLegend } from "../components/ScaleLegend";
import { defaultSelection, type Selection } from "../components/selection";
import { intervalLabel, intervalText, isProbability, label, num } from "../components/labels";
import { useT } from "../i18n/context";
import { MapView, type MapLayer } from "../map/MapView";
import {
  COLOURS,
  DIVERGING,
  divergingColour,
  intervalWidth,
  qualityOverlay,
  resultStyle,
  scaleColour,
  valueScale,
  widthScale,
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
  const [options, setOptions] = useState<MapOptionsValue>({ uncertainty: false, quality: false });

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

  const indicator = data?.run_a.indicators.find((i) => i.id === selection?.indicator);
  const unit = indicator?.unit ?? "";
  // Interval names per run; the shared one only when both runs use the same quantile levels.
  const { interval, intervalA, intervalB, statistic } = useMemo(() => {
    const levelsA = data?.run_a.interval_quantiles;
    const levelsB = data?.run_b.interval_quantiles;
    const same = JSON.stringify(levelsA) === JSON.stringify(levelsB);
    const shared = intervalLabel(t, lang, same ? levelsA : null);
    return {
      interval: shared,
      intervalA: intervalLabel(t, lang, levelsA),
      intervalB: intervalLabel(t, lang, levelsB),
      statistic: t("result.statistic", { interval: shared }),
    };
  }, [data, lang, t]);
  const probability = isProbability(indicator);
  // One scale for both maps, built from the values of A and B together (and one legend).
  const scale = useMemo(
    () =>
      valueScale(
        rows.flatMap((r) => [r.a.median, r.b.median]).filter((v): v is number => v !== null),
        probability,
      ),
    [rows, probability],
  );
  const wScale = useMemo(
    () =>
      widthScale(
        rows
          .flatMap((r) => [intervalWidth(r.a.low, r.a.high), intervalWidth(r.b.low, r.b.high)])
          .filter((w): w is number => w !== null),
      ),
    [rows],
  );
  const maxAbs = Math.max(0, ...rows.map((r) => Math.abs(r.difference_of_medians ?? 0)));

  const layers = useMemo(() => {
    if (!units) return { a: [], b: [], diff: [] };
    const byUnit = new Map(rows.map((r) => [r.unit_id, r]));
    const quality: MapLayer[] = options.quality
      ? [{ id: "quality", data: units, style: qualityOverlay, interactive: false }]
      : [];
    const make = (id: string, fill: (r: Row) => string, tip: (r: Row) => string): MapLayer[] => [
      {
        id,
        data: units,
        style: (f: Feature) => {
          const r = byUnit.get(String(f.id));
          return resultStyle(!!r, r?.edge_effect_warning === true, r ? fill(r) : "");
        },
        tooltip: (f: Feature) => {
          const r = byUnit.get(String(f.id));
          return r ? `${r.unit_name}, ${tip(r)}` : `${String(f.id)}: ${t("results.not_reported")}`;
        },
      },
      ...quality,
    ];
    const side = (pick: (r: Row) => Row["a"]) => ({
      fill: (r: Row) =>
        options.uncertainty
          ? scaleColour(wScale, intervalWidth(pick(r).low, pick(r).high))
          : scaleColour(scale, pick(r).median),
      tip: (r: Row) =>
        `${statistic}: ${intervalText(t, lang, pick(r).median, pick(r).low, pick(r).high, unit)}`,
    });
    const a = side((r) => r.a);
    const b = side((r) => r.b);
    return {
      a: make("a", a.fill, a.tip),
      b: make("b", b.fill, b.tip),
      diff: make(
        "diff",
        (r) =>
          r.difference_of_medians === null ? "" : divergingColour(r.difference_of_medians, maxAbs),
        (r) => `${t("compare.col_diff")}: ${num(r.difference_of_medians, lang)}`,
      ),
    };
  }, [units, rows, scale, wScale, maxAbs, options, unit, statistic, lang, t]);

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

  const indicatorName = label(t, "indicator", selection.indicator);
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
      <MapOptions value={options} onChange={setOptions} />
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
      <ScaleLegend
        testId="shared-legend"
        title={
          options.uncertainty
            ? t("compare.legend_shared_width", { indicator: indicatorName, unit, interval })
            : probability
              ? t("compare.legend_shared_probability", { indicator: indicatorName })
              : t("compare.legend_shared", { indicator: indicatorName, unit })
        }
        scale={options.uncertainty ? wScale : scale}
        quality={options.quality}
      />
      {!options.uncertainty && (
        <p className="muted">{t("legend.central_value_note", { interval })}</p>
      )}
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
            <th scope="col">{t("compare.col_a", { interval: intervalA })}</th>
            <th scope="col">{t("compare.col_b", { interval: intervalB })}</th>
            <th scope="col">{t("compare.col_diff")}</th>
            <th scope="col">{t("results.warnings")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.unit_id}>
              <th scope="row">{r.unit_name}</th>
              <td>
                <IntervalValue
                  value={r.a.median}
                  low={r.a.low}
                  high={r.a.high}
                  unit={unit}
                  interval={intervalA}
                />
              </td>
              <td>
                <IntervalValue
                  value={r.b.median}
                  low={r.b.low}
                  high={r.b.high}
                  unit={unit}
                  interval={intervalB}
                />
              </td>
              <td>{num(r.difference_of_medians, lang)}</td>
              <td>{r.edge_effect_warning ? `⚠ ${t("results.edge_effect")}` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">{t("compare.difference_note")}</p>
    </section>
  );
}
