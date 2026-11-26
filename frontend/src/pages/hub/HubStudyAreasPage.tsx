import { useCallback, useEffect, useState, type SyntheticEvent } from "react";

import { unwrap } from "../../api/client";
import { hubApi, hubUrl, type StudyArea } from "../../api/hub";
import { useSession } from "../../app/session";
import { ErrorMessage } from "../../components/ErrorMessage";
import { JobProgress } from "../../components/JobProgress";
import { label } from "../../components/labels";
import { useT } from "../../i18n/context";
import { serverText } from "../../i18n/server";
import { useCoverage } from "./shared";

/** Study areas, publishing packages and the list of areas with an update available. */
export function HubStudyAreasPage() {
  const { t } = useT();
  const { user } = useSession();
  const isAdmin = user?.role === "admin";
  const [areas, setAreas] = useState<StudyArea[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [jobs, setJobs] = useState<Record<string, string>>({});
  const [comments, setComments] = useState<Record<string, string>>({});
  const load = useCallback(() => {
    unwrap(hubApi.GET("/hub/study-areas")).then(setAreas).catch(setError);
  }, []);
  useEffect(load, [load]);

  async function publish(area: StudyArea) {
    setError(null);
    try {
      const started = await unwrap(
        hubApi.POST("/hub/study-areas/{study_area_id}/publish", {
          params: { path: { study_area_id: area.id } },
          body: { comment: comments[area.id] ?? "" },
        }),
      );
      setJobs({ ...jobs, [area.id]: started.job_id });
    } catch (e) {
      setError(e);
    }
  }

  const updates = areas.filter((a) => a.update_available);
  return (
    <section aria-labelledby="areas-title">
      <h2 id="areas-title">{t("hub.areas.title")}</h2>
      <p className="muted">{t("hub.areas.intro")}</p>
      <ErrorMessage error={error} />

      <section aria-labelledby="propagation-title" data-testid="propagation-list">
        <h3 id="propagation-title">{t("hub.propagation.title")}</h3>
        {updates.length === 0 ? (
          <p>{t("hub.propagation.none")}</p>
        ) : (
          <ul>
            {updates.map((a) => (
              <li key={a.id} data-area={a.id}>
                <strong>
                  {t("hub.propagation.item", {
                    id: a.id,
                    last: a.last_version ?? "—",
                    next: a.pending.next_version,
                  })}
                </strong>
                <br />
                {t("hub.propagation.draft")}{" "}
                {a.pending.changelog
                  .split("; ")
                  .map((line) => serverText(t, line))
                  .join("; ")}
              </li>
            ))}
          </ul>
        )}
      </section>

      {areas.map((a) => (
        <section key={a.id} className="panel" aria-labelledby={`area-${a.id}`} data-area={a.id}>
          <h3 id={`area-${a.id}`}>
            {a.name} ({a.id})
          </h3>
          <p>
            {t("hub.areas.core", { list: a.core_municipalities.join(", ") })} ·{" "}
            {t("hub.areas.buffer", {
              list: a.buffer_municipalities.join(", ") || "—",
              rule: label(t, "hub.buffer_rule", a.buffer_rule),
            })}
          </p>
          <p data-testid="area-state">
            {a.last_version
              ? t("hub.areas.last", { version: a.last_version })
              : t("hub.areas.never")}{" "}
            ·{" "}
            {a.update_available ? (
              <span className="badge badge--update">{t("hub.areas.update_available")}</span>
            ) : a.last_version ? (
              t("hub.areas.up_to_date")
            ) : null}
          </p>
          {(a.pending.changed || !a.last_version) && (
            <p>
              {t("hub.areas.next", {
                version: a.pending.next_version,
                bump: label(t, "hub.bump", a.pending.bump),
              })}
            </p>
          )}
          {isAdmin && (a.pending.changed || !a.last_version) && !jobs[a.id] && (
            <div className="subform">
              <label>
                {t("hub.areas.comment")}{" "}
                <input
                  value={comments[a.id] ?? ""}
                  onChange={(e) => {
                    setComments({ ...comments, [a.id]: e.target.value });
                  }}
                />
              </label>
              <button type="button" onClick={() => void publish(a)}>
                {t("hub.areas.publish", { version: a.pending.next_version })}
              </button>
            </div>
          )}
          {jobs[a.id] && (
            <JobProgress
              jobId={jobs[a.id] ?? ""}
              onFinished={() => {
                setJobs((j) => Object.fromEntries(Object.entries(j).filter(([k]) => k !== a.id)));
                load();
              }}
            />
          )}
          <table data-testid="package-list">
            <caption>{t("hub.areas.packages")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("admin.version")}</th>
                <th scope="col">{t("admin.status")}</th>
                <th scope="col">{t("hub.areas.published")}</th>
                <th scope="col">SHA-256</th>
                <th scope="col">{t("admin.action")}</th>
              </tr>
            </thead>
            <tbody>
              {a.packages.map((p) => (
                <tr key={p.id}>
                  <th scope="row">{p.version}</th>
                  <td>
                    {label(t, "hub.package_status", p.status)}
                    {p.error && <span className="error"> {serverText(t, p.error)}</span>}
                  </td>
                  <td>{p.published_at ? new Date(p.published_at).toLocaleString() : "—"}</td>
                  <td>{p.archive_sha256 ? <code>{p.archive_sha256.slice(0, 12)}…</code> : "—"}</td>
                  <td>
                    {p.status === "published" && (
                      <a href={hubUrl(`/hub/study-areas/${a.id}/packages/${p.version}/download`)}>
                        {t("hub.areas.download", { version: p.version })}
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
      {isAdmin && <NewStudyArea onCreated={load} />}
    </section>
  );
}

function NewStudyArea({ onCreated }: { onCreated: () => void }) {
  const { t } = useT();
  const { rows } = useCoverage("onboarded");
  const [form, setForm] = useState({
    id: "",
    name: "",
    core: [] as string[],
    rule: "",
    distance: "",
  });
  const [error, setError] = useState<unknown>(null);

  async function create(e: SyntheticEvent) {
    e.preventDefault();
    setError(null);
    try {
      await unwrap(
        hubApi.POST("/hub/study-areas", {
          body: {
            id: form.id,
            name: form.name,
            core_municipalities: form.core,
            buffer_rule:
              form.rule === ""
                ? null
                : (form.rule as "whole_neighbouring_municipalities" | "distance"),
            buffer_distance_m: form.distance ? Number(form.distance) : null,
          },
        }),
      );
      setForm({ id: "", name: "", core: [], rule: "", distance: "" });
      onCreated();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <form className="subform" onSubmit={(e) => void create(e)} aria-labelledby="new-area-title">
      <h3 id="new-area-title">{t("hub.areas.new")}</h3>
      <label>
        {t("hub.areas.id")}{" "}
        <input
          required
          pattern="[a-z0-9][a-z0-9\-]{1,62}"
          value={form.id}
          onChange={(e) => {
            setForm({ ...form, id: e.target.value });
          }}
        />
      </label>
      <label>
        {t("hub.name")}{" "}
        <input
          required
          value={form.name}
          onChange={(e) => {
            setForm({ ...form, name: e.target.value });
          }}
        />
      </label>
      <label>
        {t("hub.areas.core_label")}{" "}
        <select
          multiple
          required
          value={form.core}
          onChange={(e) => {
            setForm({ ...form, core: Array.from(e.target.selectedOptions, (o) => o.value) });
          }}
        >
          {rows.map((r) => (
            <option key={r.municipality_id} value={r.municipality_id}>
              {r.municipality_id} · {r.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("hub.areas.rule")}{" "}
        <select
          value={form.rule}
          onChange={(e) => {
            setForm({ ...form, rule: e.target.value });
          }}
        >
          <option value="">{t("hub.areas.rule_default")}</option>
          <option value="whole_neighbouring_municipalities">
            {label(t, "hub.buffer_rule", "whole_neighbouring_municipalities")}
          </option>
          <option value="distance">{label(t, "hub.buffer_rule", "distance")}</option>
        </select>
      </label>
      {form.rule === "distance" && (
        <label>
          {t("hub.areas.distance")}{" "}
          <input
            inputMode="decimal"
            value={form.distance}
            onChange={(e) => {
              setForm({ ...form, distance: e.target.value });
            }}
          />
        </label>
      )}
      <p className="muted">{t("hub.areas.oq28")}</p>
      <ErrorMessage error={error} />
      <button type="submit">{t("hub.areas.create")}</button>
    </form>
  );
}
