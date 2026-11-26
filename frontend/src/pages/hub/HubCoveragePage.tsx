import { useState } from "react";
import { Link } from "react-router";

import { ErrorMessage } from "../../components/ErrorMessage";
import { label } from "../../components/labels";
import { useT } from "../../i18n/context";
import { FilterSelect } from "./HubOnboardingPage";
import { COVERAGE_LAYERS, useCoverage } from "./shared";

/** Coverage matrix: municipalities × layers with status, version and last update. */
export function HubCoveragePage() {
  const { t, lang } = useT();
  const [filter, setFilter] = useState<"all" | "onboarded" | "not_onboarded">("all");
  const { rows, error } = useCoverage(filter);
  const date = (iso: string | null | undefined) =>
    iso ? new Date(iso).toLocaleDateString(lang === "el" ? "el-GR" : "en-GB") : "—";
  return (
    <section aria-labelledby="coverage-title">
      <h2 id="coverage-title">{t("hub.coverage.title")}</h2>
      <p className="muted">{t("hub.coverage.intro")}</p>
      <FilterSelect value={filter} onChange={setFilter} />
      <ErrorMessage error={error} />
      <div className="table-scroll">
        <table data-testid="coverage-matrix" className="matrix">
          <caption>{t("hub.coverage.caption")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("hub.municipality")}</th>
              <th scope="col">{t("hub.onboarding.status")}</th>
              {COVERAGE_LAYERS.map((l) => (
                <th scope="col" key={l}>
                  {label(t, "layer", l)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.municipality_id} data-municipality={r.municipality_id}>
                <th scope="row">
                  <Link to={`/onboarding/${r.municipality_id}`}>
                    {r.municipality_id} · {r.name}
                  </Link>
                </th>
                <td>{label(t, "hub.status", r.status)}</td>
                {COVERAGE_LAYERS.map((l) => {
                  const cell = r.layers[l];
                  const status = cell?.status ?? "missing";
                  return (
                    <td key={l} className={`coverage coverage--${status}`} data-layer={l}>
                      <strong>{label(t, "coverage", status)}</strong>
                      {cell && cell.version !== "-" && (
                        <span className="muted">
                          <br />
                          {t("hub.coverage.version", { version: cell.version })}
                          <br />
                          {t("hub.coverage.updated", { date: date(cell.updated_at) })}
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted">{t("hub.coverage.note")}</p>
    </section>
  );
}
