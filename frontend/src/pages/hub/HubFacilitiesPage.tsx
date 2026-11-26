import { useCallback, useEffect, useState, type SyntheticEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { unwrap } from "../../api/client";
import { hubApi, hubUrl, uploadFile, type Changeset, type HubSchemas } from "../../api/hub";
import { useSession } from "../../app/session";
import { ErrorMessage } from "../../components/ErrorMessage";
import { label } from "../../components/labels";
import { useT } from "../../i18n/context";
import { ChangesetView } from "./ChangesetView";
import { text, useCoverage } from "./shared";

type Facility = HubSchemas["FacilityOut"];

/** Facility import (upload, report, preview, approve), facility list and changesets. */
export function HubFacilitiesPage() {
  const { t } = useT();
  const { user } = useSession();
  const [params, setParams] = useSearchParams();
  const { rows } = useCoverage("onboarded");
  const municipality = params.get("municipality") ?? "";
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [changesets, setChangesets] = useState<HubSchemas["ChangesetSummaryOut"][]>([]);
  const [result, setResult] = useState<Changeset | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    source: "",
    comment: "",
    licence: "CC-BY-4.0",
    attribution: "",
    complete_list: false,
    is_correction: false,
  });
  const [file, setFile] = useState<File | null>(null);
  const canUpload = user?.role === "admin" || user?.role === "analyst";

  const load = useCallback(() => {
    if (!municipality) return;
    unwrap(hubApi.GET("/hub/facilities", { params: { query: { municipality } } }))
      .then(setFacilities)
      .catch(setError);
    unwrap(hubApi.GET("/hub/changesets", { params: { query: { municipality } } }))
      .then(setChangesets)
      .catch(setError);
  }, [municipality]);
  useEffect(load, [load]);

  async function upload(e: SyntheticEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const cs = await uploadFile<Changeset>(
        "/hub/facility-imports",
        {
          municipality,
          file_name: file.name,
          source: form.source,
          comment: form.comment,
          licence: form.licence,
          attribution: form.attribution,
          complete_list: String(form.complete_list),
          is_correction: String(form.is_correction),
        },
        file,
      );
      setResult(cs);
      load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="facilities-title">
      <h2 id="facilities-title">{t("hub.facilities.title")}</h2>
      <label>
        {t("hub.municipality")}{" "}
        <select
          value={municipality}
          onChange={(e) => {
            setResult(null);
            setParams(e.target.value ? { municipality: e.target.value } : {});
          }}
        >
          <option value="">{t("hub.facilities.choose")}</option>
          {rows.map((r) => (
            <option key={r.municipality_id} value={r.municipality_id}>
              {r.municipality_id} · {r.name}
            </option>
          ))}
        </select>
      </label>

      <h3>{t("hub.template.title")}</h3>
      <p>
        {t("hub.template.intro")}{" "}
        <a href={hubUrl("/hub/facilities/template", { format: "xlsx" })}>XLSX</a> ·{" "}
        <a href={hubUrl("/hub/facilities/template", { format: "csv" })}>CSV</a> ·{" "}
        <a href={hubUrl("/hub/facilities/template", { format: "gpkg" })}>GeoPackage</a>
      </p>
      <p className="muted">{t("hub.template.personal")}</p>

      {municipality && (
        <>
          <p>
            {t("hub.facilities.export")}{" "}
            <a href={hubUrl("/hub/facilities/export", { municipality, format: "xlsx" })}>XLSX</a> ·{" "}
            <a href={hubUrl("/hub/facilities/export", { municipality, format: "csv" })}>CSV</a>
          </p>
          {canUpload && (
            <form
              className="subform"
              onSubmit={(e) => void upload(e)}
              aria-labelledby="upload-title"
            >
              <h3 id="upload-title">{t("hub.import.title", { municipality })}</h3>
              <label>
                {t("hub.import.file")}{" "}
                <input
                  type="file"
                  accept=".csv,.xlsx,.gpkg"
                  required
                  onChange={(e) => {
                    setFile(e.target.files?.[0] ?? null);
                  }}
                />
              </label>
              <label>
                {t("hub.import.source")}{" "}
                <input
                  required
                  value={form.source}
                  onChange={(e) => {
                    setForm({ ...form, source: e.target.value });
                  }}
                />
              </label>
              <label>
                {t("hub.import.licence")}{" "}
                <input
                  value={form.licence}
                  onChange={(e) => {
                    setForm({ ...form, licence: e.target.value });
                  }}
                />
              </label>
              <label>
                {t("hub.import.attribution")}{" "}
                <input
                  value={form.attribution}
                  onChange={(e) => {
                    setForm({ ...form, attribution: e.target.value });
                  }}
                />
              </label>
              <label>
                {t("hub.import.comment")}{" "}
                <input
                  value={form.comment}
                  onChange={(e) => {
                    setForm({ ...form, comment: e.target.value });
                  }}
                />
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={form.is_correction}
                  onChange={(e) => {
                    setForm({ ...form, is_correction: e.target.checked });
                  }}
                />{" "}
                {t("hub.import.correction")}
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={form.complete_list}
                  onChange={(e) => {
                    setForm({ ...form, complete_list: e.target.checked });
                  }}
                />{" "}
                {t("hub.import.complete_list", { municipality })}
              </label>
              <button type="submit" disabled={busy || !file}>
                {t("hub.import.check")}
              </button>
            </form>
          )}
          <ErrorMessage error={error} />
          {result && (
            <ChangesetView
              changeset={result}
              onChange={(cs) => {
                setResult(cs);
                load();
              }}
            />
          )}

          <h3>{t("hub.facilities.list")}</h3>
          <table data-testid="facility-list">
            <caption className="sr-only">{t("hub.facilities.list")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("hub.facility")}</th>
                <th scope="col">{t("hub.name")}</th>
                <th scope="col">{t("attr.facility_type")}</th>
                <th scope="col">{t("hub.quality")}</th>
                <th scope="col">{t("hub.facilities.valid")}</th>
              </tr>
            </thead>
            <tbody>
              {facilities.map((f) => (
                <tr key={f.facility_id} data-facility={f.facility_id}>
                  <th scope="row">
                    <Link to={`/facilities/${f.facility_id}`}>{f.facility_id}</Link>
                  </th>
                  <td>{text(f.properties.name)}</td>
                  <td>{text(f.properties.facility_type)}</td>
                  <td className={`quality quality--${f.quality}`}>
                    {label(t, "quality", f.quality)}
                  </td>
                  <td>
                    {f.valid_to
                      ? t("hub.facilities.closed_on", { date: f.valid_to })
                      : t("hub.facilities.open_since", { date: f.valid_from })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {canUpload && (
            <p>
              <Link to={`/facilities/new?municipality=${municipality}`}>
                {t("hub.facilities.new")}
              </Link>
            </p>
          )}

          <h3>{t("hub.changesets.title")}</h3>
          <ul data-testid="changeset-list">
            {changesets.map((c) => (
              <li key={c.id}>
                <Link to={`/changesets/${String(c.id)}`}>
                  {t("hub.changeset.title", { id: c.id, municipality: c.municipality_id })}
                </Link>{" "}
                · {label(t, "hub.changeset_status", c.status)} · {c.file_name ?? ""} ·{" "}
                {c.created_by_name ?? ""}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

/** One changeset on its own page. */
export function HubChangesetPage() {
  const { changesetId = "" } = useParams();
  const { t } = useT();
  const [cs, setCs] = useState<Changeset | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    unwrap(
      hubApi.GET("/hub/changesets/{changeset_id}", {
        params: { path: { changeset_id: Number(changesetId) } },
      }),
    )
      .then(setCs)
      .catch(setError);
  }, [changesetId]);
  return (
    <section>
      <ErrorMessage error={error} />
      {cs ? (
        <ChangesetView changeset={cs} onChange={setCs} />
      ) : (
        !error && <p>{t("common.loading")}</p>
      )}
    </section>
  );
}
