import type { Feature, FeatureCollection } from "geojson";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { api, exportUrl, getCatalog, getLayer, unwrap, type Schemas } from "../api/client";
import { canEdit, useSession } from "../app/session";
import { DiagnosticBanner } from "../components/DiagnosticBanner";
import { ErrorMessage } from "../components/ErrorMessage";
import { IntervalValue } from "../components/IntervalValue";
import { MapOptions, type MapOptionsValue } from "../components/MapOptions";
import { RunStatus } from "../components/RunStatus";
import { ResultSelectors } from "../components/ResultSelectors";
import { defaultSelection, type Selection } from "../components/selection";
import { ScaleLegend } from "../components/ScaleLegend";
import { intervalLabel, intervalText, isProbability, label, num } from "../components/labels";
import { useT } from "../i18n/context";
import { MapView, type MapLayer } from "../map/MapView";
import {
  intervalWidth,
  qualityOverlay,
  resultStyle,
  scaleColour,
  valueScale,
  widthScale,
} from "../map/styles";

type Run = Schemas["RunOut"];
type Row = Schemas["ResultRow"];

const FINISHED = new Set(["succeeded", "failed", "cancelled"]);

export function RunPage() {
  const { t, lang } = useT();
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const { config, activeDataVersion: dv, user } = useSession();
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [cancelling, setCancelling] = useState(false);
  const [units, setUnits] = useState<FeatureCollection | null>(null);
  const [catalog, setCatalog] = useState<Schemas["CatalogOut"] | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [changes, setChanges] = useState<Record<string, unknown>[]>([]);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [siblings, setSiblings] = useState<Run[]>([]);
  const [options, setOptions] = useState<MapOptionsValue>({ uncertainty: false, quality: false });

  const load = useCallback(() => {
    unwrap(api.GET("/runs/{run_id}", { params: { path: { run_id: runId } } }))
      .then(setRun)
      .catch(setError);
  }, [runId]);

  useEffect(load, [load]);

  const scenarioId = run?.scenario_id;
  const status = run?.status;
  useEffect(() => {
    if (!scenarioId) return;
    unwrap(api.GET("/runs", { params: { query: { scenario_id: scenarioId } } }))
      .then(setSiblings)
      .catch(setError);
  }, [scenarioId, status]);

  // Follow progress until the run reaches a final state.
  useEffect(() => {
    if (!run || FINISHED.has(run.status)) return;
    const timer = window.setTimeout(load, 1000);
    return () => {
      window.clearTimeout(timer);
    };
  }, [run, load]);

  const succeeded = run?.status === "succeeded";
  useEffect(() => {
    if (!run || !succeeded) return;
    Promise.all([
      getLayer(run.data_version_id, "spatial_units"),
      getCatalog(run.data_version_id),
      unwrap(api.GET("/runs/{run_id}/results", { params: { path: { run_id: run.id } } })),
      unwrap(
        api.GET("/runs/{run_id}/tables/{name}", {
          params: { path: { run_id: run.id, name: "unit_changes" } },
        }),
      ),
    ])
      .then(([u, c, r, ch]) => {
        setUnits(u);
        setCatalog(c);
        setRows(r);
        setChanges(ch);
        setSelection((s) => s ?? defaultSelection(c, run.indicators));
      })
      .catch(setError);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once per succeeded run
  }, [run?.id, succeeded]);

  async function cancel() {
    if (!run) return;
    setCancelling(true);
    try {
      setRun(
        await unwrap(api.POST("/runs/{run_id}/cancel", { params: { path: { run_id: run.id } } })),
      );
    } catch (e) {
      setError(e);
    } finally {
      setCancelling(false);
    }
  }

  async function rerun() {
    if (!run) return;
    try {
      const created = await unwrap(
        api.POST("/runs", { body: { scenario_id: run.scenario_id, seed: run.seed, force: false } }),
      );
      void navigate(`/runs/${created.id}`);
    } catch (e) {
      setError(e);
    }
  }

  const visible = useMemo(
    () =>
      selection
        ? rows.filter(
            (r) =>
              r.group_id === selection.group &&
              r.service_id === selection.service &&
              r.indicator === selection.indicator,
          )
        : [],
    [rows, selection],
  );
  const indicator = run?.indicators.find((i) => i.id === selection?.indicator);
  const unitOfMeasure = indicator?.unit ?? "";
  const interval = intervalLabel(t, lang, run?.interval_quantiles);
  const statistic = t("result.statistic", { interval });
  const probability = isProbability(indicator);
  const scale = useMemo(
    () =>
      valueScale(
        visible.map((r) => r.median).filter((v): v is number => v !== null),
        probability,
      ),
    [visible, probability],
  );
  const widths = useMemo(
    () => visible.map((r) => intervalWidth(r.low, r.high)).filter((w): w is number => w !== null),
    [visible],
  );
  const wScale = useMemo(() => widthScale(widths), [widths]);
  const quality = useMemo(
    () =>
      new Map(
        (units?.features ?? []).map((f) => [String(f.id), String(f.properties?.quality ?? "")]),
      ),
    [units],
  );
  const lowQuality = visible.filter((r) =>
    ["estimated", "open_data"].includes(quality.get(r.unit_id) ?? ""),
  ).length;

  const mapLayers = useMemo(() => {
    if (!units) return { values: [] as MapLayer[], widths: [] as MapLayer[] };
    const byUnit = new Map(visible.map((r) => [r.unit_id, r]));
    const tooltip = (f: Feature) => {
      const row = byUnit.get(String(f.id));
      if (!row) return `${String(f.id)}: ${t("results.not_reported")}`;
      const text = intervalText(t, lang, row.median, row.low, row.high, unitOfMeasure);
      const warn = row.edge_effect_warning ? ` ⚠ ${t("results.edge_effect")}` : "";
      return `${row.unit_name}, ${statistic}: ${text}${warn}`;
    };
    const layer = (id: string, fill: (r: Row) => string, tip = tooltip): MapLayer => ({
      id,
      data: units,
      style: (f: Feature) => {
        const row = byUnit.get(String(f.id));
        return resultStyle(!!row, row?.edge_effect_warning === true, row ? fill(row) : "");
      },
      tooltip: tip,
    });
    const qualityLayer: MapLayer[] = options.quality
      ? [{ id: "quality", data: units, style: qualityOverlay, interactive: false }]
      : [];
    return {
      values: [layer("results", (r) => scaleColour(scale, r.median)), ...qualityLayer],
      widths: [
        layer(
          "widths",
          (r) => scaleColour(wScale, intervalWidth(r.low, r.high)),
          (f) => {
            const row = byUnit.get(String(f.id));
            const width = row ? intervalWidth(row.low, row.high) : null;
            return width === null
              ? tooltip(f)
              : `${tooltip(f)} · ${t("results.width", { interval, value: num(width, lang) })}`;
          },
        ),
        ...qualityLayer,
      ],
    };
  }, [units, visible, scale, wScale, options.quality, unitOfMeasure, interval, statistic, lang, t]);

  if (!run) {
    return (
      <section>
        <ErrorMessage error={error} />
        {!error && <p role="status">{t("common.loading")}</p>}
      </section>
    );
  }

  const handCheck = run.diagnostics?.hand_check as
    | Record<"baseline" | "scenario", { available: boolean; checked: number; passed: number }>
    | undefined;

  return (
    <section aria-labelledby="run-title">
      <h2 id="run-title">
        {t("run.title", { name: run.scenario_name, version: run.scenario_version })}
      </h2>
      {run.diagnostic && <DiagnosticBanner />}
      <RunStatus run={run} onCancel={() => void cancel()} cancelling={cancelling} />
      <ErrorMessage error={error} />
      {dv && dv.id !== run.data_version_id && (
        <p className="banner banner--warning" role="note">
          {t("run.old_data", { run: run.package_version, active: dv.version })}{" "}
          {!run.is_baseline && canEdit(user) && (
            <button type="button" onClick={() => void rerun()}>
              {t("run.rerun_on", { version: dv.version })}
            </button>
          )}
        </p>
      )}

      {succeeded && catalog && selection && (
        <>
          <p className="actions">
            <Link className="button" to={`/runs/${run.id}/compare`}>
              {t("run.compare_baseline")}
            </Link>
            <a className="button" href={exportUrl(run.id, "csv")} download>
              {t("run.export_csv")}
            </a>
            <a className="button" href={exportUrl(run.id, "gpkg")} download>
              {t("run.export_gpkg")}
            </a>
          </p>
          <ResultSelectors
            catalog={catalog}
            indicators={run.indicators}
            value={selection}
            onChange={setSelection}
          />
          {run.edge_effect_units.length > 0 && (
            <p className="banner banner--warning" role="note">
              {t("results.edge_effect_units", { units: run.edge_effect_units.join(", ") })}
            </p>
          )}
          <MapOptions value={options} onChange={setOptions} />
          <div className={options.uncertainty ? "compare-grid" : ""}>
            <div>
              <MapView
                label={t("run.map_label")}
                layers={mapLayers.values}
                basemap={config?.basemap ?? "blank"}
              />
              <ScaleLegend
                testId="value-legend"
                title={
                  probability
                    ? t("legend.probability_title", {
                        indicator: label(t, "indicator", selection.indicator),
                      })
                    : t("legend.value_title", {
                        indicator: label(t, "indicator", selection.indicator),
                        unit: unitOfMeasure,
                      })
                }
                scale={scale}
                quality={options.quality}
              />
            </div>
            {options.uncertainty && (
              <div data-testid="uncertainty-map">
                <h3>{t("results.uncertainty_title", { interval })}</h3>
                <MapView
                  label={t("results.uncertainty_map_label")}
                  layers={mapLayers.widths}
                  basemap={config?.basemap ?? "blank"}
                />
                <ScaleLegend
                  testId="uncertainty-legend"
                  title={t("legend.uncertainty_title", {
                    interval,
                    indicator: label(t, "indicator", selection.indicator),
                    unit: unitOfMeasure,
                  })}
                  scale={wScale}
                  quality={options.quality}
                />
                {widths.every((w) => w === 0) && (
                  <p className="muted">{t("results.no_uncertainty")}</p>
                )}
              </div>
            )}
          </div>
          <p className="muted">{t("legend.central_value_note", { interval })}</p>
          {!options.quality && lowQuality > 0 && (
            <p className="muted" data-testid="quality-hidden">
              {t("results.quality_hidden", { count: lowQuality })}
            </p>
          )}
          <table data-testid="results-table">
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
                <th scope="col">{t("results.value", { interval })}</th>
                <th scope="col">{t("results.before")}</th>
                <th scope="col">{t("results.changed")}</th>
                <th scope="col">{t("results.warnings")}</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={r.unit_id} data-unit={r.unit_id}>
                  <th scope="row">{r.unit_name}</th>
                  <td>
                    <IntervalValue
                      value={r.median}
                      low={r.low}
                      high={r.high}
                      unit={unitOfMeasure}
                      interval={interval}
                    />
                  </td>
                  <td>{r.baseline === null ? "—" : num(r.baseline, lang)}</td>
                  <td>
                    {r.baseline !== null && r.baseline !== r.median ? (
                      <strong data-testid="changed">{t("results.yes_changed")}</strong>
                    ) : (
                      t("results.no")
                    )}
                  </td>
                  <td>
                    {[
                      r.edge_effect_warning ? `⚠ ${t("results.edge_effect")}` : "",
                      ["estimated", "open_data"].includes(quality.get(r.unit_id) ?? "")
                        ? t("results.quality_mark", {
                            quality: label(t, "quality", quality.get(r.unit_id)),
                          })
                        : "",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {indicator && !indicator.group_dependent && (
            <p className="muted">{t("results.group_independent")}</p>
          )}
          {handCheck && (
            <p data-testid="hand-check">
              {t("run.hand_check", {
                passed: handCheck.baseline.passed,
                checked: handCheck.baseline.checked,
              })}{" "}
              {handCheck.scenario.available
                ? t("run.hand_check_scenario", {
                    passed: handCheck.scenario.passed,
                    checked: handCheck.scenario.checked,
                  })
                : t("run.hand_check_none")}
            </p>
          )}
          <h3>{t("run.changes_title")}</h3>
          <ul>
            {changes
              .filter((c) => (c.details as string[]).length > 0)
              .map((c) => (
                <li key={String(c.unit_id)}>
                  <strong>{String(c.unit_id)}</strong>: {(c.details as string[]).join("; ")}
                </li>
              ))}
          </ul>
        </>
      )}

      {siblings.length > 1 && (
        <>
          <h3>{t("run.siblings")}</h3>
          <ul data-testid="sibling-runs">
            {siblings
              .filter((s) => s.id !== run.id)
              .map((s) => (
                <li key={s.id}>
                  <Link to={`/runs/${s.id}`}>
                    {t("run.sibling", {
                      version: s.scenario_version,
                      data: s.package_version,
                      status: label(t, "status", s.status),
                      created: s.created_at,
                    })}
                  </Link>{" "}
                  {succeeded && s.status === "succeeded" && (
                    <Link to={`/runs/${run.id}/compare?with=${s.id}`}>{t("run.compare_with")}</Link>
                  )}
                </li>
              ))}
          </ul>
        </>
      )}
      <h3>{t("run.reproducibility")}</h3>
      <dl className="repro">
        {(
          [
            ["scenario", `${run.scenario_name} (v${String(run.scenario_version)})`],
            ["data", `${run.package_id} ${run.package_version}`],
            ["code", run.code_version],
            ["model", `${run.model_id} ${run.model_version}`],
            ["seed", String(run.seed)],
            ["config", JSON.stringify(run.config)],
            ["hash", run.input_hash],
            ["created", `${run.created_at} (${run.created_by ?? t("scenarios.system")})`],
            ["finished", run.finished_at ?? "—"],
          ] as const
        ).map(([k, v]) => (
          <div className="dl-row" key={k}>
            <dt>{label(t, "repro", k)}</dt>
            <dd>
              <code>{v}</code>
            </dd>
          </div>
        ))}
      </dl>
      <p>
        <Link to={`/scenarios/${run.scenario_id}`}>{t("run.open_scenario")}</Link>
      </p>
    </section>
  );
}
