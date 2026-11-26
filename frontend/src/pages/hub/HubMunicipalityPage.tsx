import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { unwrap } from "../../api/client";
import { hubApi, jobFinished, type HubSchemas } from "../../api/hub";
import { useSession } from "../../app/session";
import { ErrorMessage } from "../../components/ErrorMessage";
import { JobProgress } from "../../components/JobProgress";
import { label } from "../../components/labels";
import { useT } from "../../i18n/context";
import { serverText } from "../../i18n/server";
import { ChecksList } from "./ChecksList";
import { COVERAGE_LAYERS } from "./shared";

type Detail = HubSchemas["OnboardingDetailOut"];

/** One municipality: status and its history, base-step reports, job progress, actions. */
export function HubMunicipalityPage() {
  const { municipalityId = "" } = useParams();
  const { t, lang } = useT();
  const { user } = useSession();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const isAdmin = user?.role === "admin";
  const when = (iso: string | null | undefined) =>
    iso ? new Date(iso).toLocaleString(lang === "el" ? "el-GR" : "en-GB") : "—";

  const load = useCallback(() => {
    unwrap(
      hubApi.GET("/hub/onboarding/{municipality_id}", {
        params: { path: { municipality_id: municipalityId } },
      }),
    )
      .then(setDetail)
      .catch(setError);
  }, [municipalityId]);
  useEffect(load, [load]);

  async function act(call: () => Promise<unknown>) {
    setError(null);
    try {
      await call();
      load();
    } catch (e) {
      setError(e);
    }
  }

  const runBase = () =>
    act(() =>
      unwrap(
        hubApi.POST("/hub/onboarding/{municipality_id}/base", {
          params: { path: { municipality_id: municipalityId } },
        }),
      ),
    );
  const setStatus = (status: Detail["status"]) =>
    act(() =>
      unwrap(
        hubApi.POST("/hub/onboarding/{municipality_id}/status", {
          params: { path: { municipality_id: municipalityId } },
          body: { status },
        }),
      ),
    );

  if (!detail) {
    return (
      <section>
        <ErrorMessage error={error} />
        {!error && <p role="status">{t("common.loading")}</p>}
      </section>
    );
  }
  const latest = detail.records.find((r) => r.kind === "onboarding_base");
  const running = detail.job && !jobFinished(detail.job);
  return (
    <section aria-labelledby="municipality-title">
      <h2 id="municipality-title">
        {t("hub.municipality.title", { id: detail.municipality_id, name: detail.name })}
      </h2>
      <p data-testid="onboarding-status">
        {t("hub.onboarding.status")}: <strong>{label(t, "hub.status", detail.status)}</strong> ·{" "}
        {t("hub.municipality.facilities", {
          open: detail.facilities_open,
          closed: detail.facilities_closed,
        })}
      </p>
      <ErrorMessage error={error} />
      <p className="actions">
        {isAdmin && !running && (
          <button type="button" onClick={() => void runBase()}>
            {detail.status === "not_started" ? t("hub.base.run") : t("hub.base.rerun")}
          </button>
        )}
        {isAdmin && ["base_ready", "facilities_in_progress"].includes(detail.status) && (
          <button type="button" onClick={() => void setStatus("in_review")}>
            {t("hub.municipality.to_review")}
          </button>
        )}
        {isAdmin && detail.status === "in_review" && (
          <button type="button" onClick={() => void setStatus("facilities_in_progress")}>
            {t("hub.municipality.back_to_work")}
          </button>
        )}
        {detail.status !== "not_started" && (
          <Link className="button" to={`/facilities?municipality=${detail.municipality_id}`}>
            {t("hub.municipality.facilities_link")}
          </Link>
        )}
      </p>
      {detail.job && <JobProgress jobId={detail.job.id} onFinished={load} />}

      <h3>{t("hub.municipality.coverage")}</h3>
      <ul className="coverage-list">
        {COVERAGE_LAYERS.map((l) => {
          const status = detail.layers[l]?.status ?? "missing";
          return (
            <li key={l} className={`coverage coverage--${status}`}>
              {label(t, "layer", l)}: {label(t, "coverage", status)}
            </li>
          );
        })}
      </ul>

      <h3>{t("hub.base.report")}</h3>
      {latest ? (
        <div data-testid="base-report">
          <p>
            {t("hub.record.line", {
              id: latest.id,
              status: label(t, "hub.record_status", latest.status),
              note: latest.processing_note,
              when: when(latest.finished_at),
            })}
          </p>
          {latest.summary && <p>{serverText(t, latest.summary)}</p>}
          <ChecksList checks={latest.checks} />
          <details>
            <summary>{t("hub.record.inputs")}</summary>
            <ul>
              {latest.inputs.map((i) => (
                <li key={String(i.source_id)}>
                  {String(i.layer_type)}: {String(i.name)} {String(i.version)} · SHA-256{" "}
                  <code>{String(i.sha256).slice(0, 12)}…</code> · {String(i.licence)}
                </li>
              ))}
            </ul>
          </details>
        </div>
      ) : (
        <p className="muted">{t("hub.base.none")}</p>
      )}

      <h3>{t("hub.municipality.history")}</h3>
      <table data-testid="status-history">
        <caption className="sr-only">{t("hub.municipality.history")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("hub.history.when")}</th>
            <th scope="col">{t("hub.history.from")}</th>
            <th scope="col">{t("hub.history.to")}</th>
            <th scope="col">{t("hub.history.by")}</th>
            <th scope="col">{t("hub.history.note")}</th>
          </tr>
        </thead>
        <tbody>
          {detail.events.map((e) => (
            <tr key={`${e.at}-${e.to_status}`}>
              <td>{when(e.at)}</td>
              <td>{label(t, "hub.status", e.from_status)}</td>
              <td>{label(t, "hub.status", e.to_status)}</td>
              <td>{e.by ?? t("hub.history.system")}</td>
              <td>{e.note}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>{t("hub.municipality.records")}</h3>
      <ul>
        {detail.records.map((r) => (
          <li key={r.id}>
            {t("hub.record.line", {
              id: r.id,
              status: label(t, "hub.record_status", r.status),
              note: r.processing_note,
              when: when(r.finished_at),
            })}
            {r.summary ? ` · ${serverText(t, r.summary)}` : ""}
          </li>
        ))}
      </ul>
    </section>
  );
}
