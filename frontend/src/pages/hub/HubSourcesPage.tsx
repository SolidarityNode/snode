import { useCallback, useEffect, useState, type SyntheticEvent } from "react";

import { unwrap } from "../../api/client";
import { hubApi, uploadFile, type HubSchemas } from "../../api/hub";
import { useSession } from "../../app/session";
import { ErrorMessage } from "../../components/ErrorMessage";
import { label } from "../../components/labels";
import { useT } from "../../i18n/context";

type Source = HubSchemas["SourceOut"];
const LAYER_TYPES = [
  "boundaries",
  "spatial_units",
  "network",
  "population",
  "groups",
  "services",
  "dem",
  "transit",
  "other",
] as const;
const EMPTY = {
  name: "",
  layer_type: "boundaries",
  version: "",
  coverage: "national",
  licence: "",
  attribution: "",
  processing_note: "",
  quality: "open_data",
};

/** Registered raw sources (versioned files); administrators register new ones. */
export function HubSourcesPage() {
  const { t, lang } = useT();
  const { user } = useSession();
  const [sources, setSources] = useState<Source[]>([]);
  const [form, setForm] = useState<Record<string, string>>(EMPTY);
  const [file, setFile] = useState<File | null>(null);
  const [done, setDone] = useState<Source | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    unwrap(hubApi.GET("/hub/sources")).then(setSources).catch(setError);
  }, []);
  useEffect(load, [load]);
  const mb = (bytes: number) =>
    (bytes / 1e6).toLocaleString(lang === "el" ? "el-GR" : "en-GB", { maximumFractionDigits: 2 });

  async function register(e: SyntheticEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      setDone(await uploadFile<Source>("/hub/sources", { ...form, file_name: file.name }, file));
      setForm(EMPTY);
      load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const field = (key: string, required = true) => (
    <label key={key}>
      {label(t, "hub.source_field", key)}{" "}
      <input
        required={required}
        value={form[key] ?? ""}
        onChange={(e) => {
          setForm({ ...form, [key]: e.target.value });
        }}
      />
    </label>
  );

  return (
    <section aria-labelledby="sources-title">
      <h2 id="sources-title">{t("hub.sources.title")}</h2>
      <p className="muted">{t("hub.sources.intro")}</p>
      <ErrorMessage error={error} />
      <div className="table-scroll">
        <table data-testid="source-list">
          <caption className="sr-only">{t("hub.sources.title")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("hub.source_field.name")}</th>
              <th scope="col">{t("hub.source_field.layer_type")}</th>
              <th scope="col">{t("hub.source_field.version")}</th>
              <th scope="col">{t("hub.source_field.coverage")}</th>
              <th scope="col">{t("hub.source_field.licence")}</th>
              <th scope="col">{t("hub.source_field.processing_note")}</th>
              <th scope="col">{t("hub.quality")}</th>
              <th scope="col">SHA-256</th>
              <th scope="col">{t("hub.sources.size")}</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((s) => (
              <tr key={s.id}>
                <th scope="row">
                  {s.name}
                  {s.synthetic && <> ({t("hub.sources.synthetic")})</>}
                  <br />
                  <span className="muted">{s.attribution}</span>
                </th>
                <td>{label(t, "hub.layer_type", s.layer_type)}</td>
                <td>{s.version}</td>
                <td>{s.coverage}</td>
                <td>{s.licence}</td>
                <td>{s.processing_note}</td>
                <td>{label(t, "quality", s.quality)}</td>
                <td>
                  <code title={s.sha256}>{s.sha256.slice(0, 12)}…</code>
                </td>
                <td>{mb(s.bytes)} MB</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {user?.role === "admin" && (
        <form
          className="subform"
          onSubmit={(e) => void register(e)}
          aria-labelledby="register-title"
        >
          <h3 id="register-title">{t("hub.sources.register")}</h3>
          <p className="muted">{t("hub.sources.register_note")}</p>
          <label>
            {t("hub.import.file")}{" "}
            <input
              type="file"
              required
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
              }}
            />
          </label>
          {field("name")}
          <label>
            {t("hub.source_field.layer_type")}{" "}
            <select
              value={form.layer_type}
              onChange={(e) => {
                setForm({ ...form, layer_type: e.target.value });
              }}
            >
              {LAYER_TYPES.map((l) => (
                <option key={l} value={l}>
                  {label(t, "hub.layer_type", l)}
                </option>
              ))}
            </select>
          </label>
          {field("version")}
          {field("coverage")}
          {field("licence")}
          {field("attribution")}
          {field("processing_note")}
          <label>
            {t("hub.quality")}{" "}
            <select
              value={form.quality}
              onChange={(e) => {
                setForm({ ...form, quality: e.target.value });
              }}
            >
              {(["open_data", "estimated", "verified_by_municipality"] as const).map((q) => (
                <option key={q} value={q}>
                  {label(t, "quality", q)}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={busy || !file}>
            {t("hub.sources.register_button")}
          </button>
        </form>
      )}
      {done && (
        <p role="status">
          {done.created
            ? t("hub.sources.registered", { name: done.name, version: done.version })
            : t("hub.sources.already", { name: done.name, version: done.version })}
        </p>
      )}
    </section>
  );
}
