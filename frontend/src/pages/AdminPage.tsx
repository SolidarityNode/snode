import { useCallback, useEffect, useState, type SyntheticEvent } from "react";
import { Link } from "react-router";

import { API_BASE, ApiError, api, unwrap, type Schemas } from "../api/client";
import { useSession } from "../app/session";
import { ErrorMessage } from "../components/ErrorMessage";
import { label } from "../components/labels";
import { useT } from "../i18n/context";
import { serverText } from "../i18n/server";

type Role = Schemas["UserOut"]["role"];

export function AdminPage() {
  const { t } = useT();
  return (
    <section aria-labelledby="admin-title">
      <h2 id="admin-title">{t("admin.title")}</h2>
      <Packages />
      <Storage />
      <Users />
    </section>
  );
}

function Storage() {
  const { t, lang } = useT();
  const [storage, setStorage] = useState<Schemas["StorageOut"] | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    unwrap(api.GET("/storage")).then(setStorage).catch(setError);
  }, []);
  const mb = (bytes: number | null | undefined) =>
    bytes === null || bytes === undefined
      ? "—"
      : (bytes / 1e6).toLocaleString(lang === "el" ? "el-GR" : "en-GB", {
          maximumFractionDigits: 1,
        });
  return (
    <section aria-labelledby="storage-title">
      <h3 id="storage-title">{t("admin.storage")}</h3>
      <ErrorMessage error={error} />
      {storage && (
        <p data-testid="storage">
          {t("admin.storage_usage", {
            files: storage.samples_files,
            runs: storage.runs_with_samples,
            used: mb(storage.samples_bytes),
            free: mb(storage.free_bytes),
          })}
        </p>
      )}
      <p className="muted">{t("admin.storage_note")}</p>
    </section>
  );
}

function Users() {
  const { t } = useT();
  const { user: me } = useSession();
  const [users, setUsers] = useState<Schemas["UserOut"][]>([]);
  const [error, setError] = useState<unknown>(null);
  const [form, setForm] = useState({ username: "", password: "", role: "viewer" as Role });
  const load = useCallback(() => {
    unwrap(api.GET("/users")).then(setUsers).catch(setError);
  }, []);
  useEffect(load, [load]);

  async function change(id: number, patch: Schemas["UserPatch"]) {
    setError(null);
    try {
      await unwrap(
        api.PATCH("/users/{user_id}", { params: { path: { user_id: id } }, body: patch }),
      );
      load();
    } catch (e) {
      setError(e);
    }
  }

  async function create(e: SyntheticEvent) {
    e.preventDefault();
    setError(null);
    try {
      await unwrap(api.POST("/users", { body: form }));
      setForm({ username: "", password: "", role: "viewer" });
      load();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section aria-labelledby="users-title">
      <h3 id="users-title">{t("admin.users")}</h3>
      <ErrorMessage error={error} />
      <table>
        <caption className="sr-only">{t("admin.users")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("admin.username")}</th>
            <th scope="col">{t("admin.role")}</th>
            <th scope="col">{t("admin.active")}</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <th scope="row">{u.username}</th>
              <td>
                <select
                  aria-label={t("admin.role_of", { user: u.username })}
                  value={u.role}
                  disabled={u.id === me?.id}
                  onChange={(e) => void change(u.id, { role: e.target.value as Role })}
                >
                  {(["admin", "analyst", "viewer"] as const).map((r) => (
                    <option key={r} value={r}>
                      {label(t, "role", r)}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <input
                  type="checkbox"
                  aria-label={t("admin.active_of", { user: u.username })}
                  checked={u.active}
                  disabled={u.id === me?.id}
                  onChange={(e) => void change(u.id, { active: e.target.checked })}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form onSubmit={(e) => void create(e)} className="subform">
        <h4>{t("admin.new_user")}</h4>
        <label>
          {t("admin.username")}
          <input
            value={form.username}
            required
            pattern="[A-Za-z0-9_.\-]{3,64}"
            onChange={(e) => {
              setForm({ ...form, username: e.target.value });
            }}
          />
        </label>
        <label>
          {t("admin.password")}
          <input
            type="password"
            autoComplete="new-password"
            minLength={12}
            required
            value={form.password}
            onChange={(e) => {
              setForm({ ...form, password: e.target.value });
            }}
          />
        </label>
        <label>
          {t("admin.role")}
          <select
            value={form.role}
            onChange={(e) => {
              setForm({ ...form, role: e.target.value as Role });
            }}
          >
            {(["viewer", "analyst", "admin"] as const).map((r) => (
              <option key={r} value={r}>
                {label(t, "role", r)}
              </option>
            ))}
          </select>
        </label>
        <button type="submit">{t("admin.create_user")}</button>
      </form>
    </section>
  );
}

function Packages() {
  const { t } = useT();
  const { refreshDataVersion } = useSession();
  const [versions, setVersions] = useState<Schemas["DataVersionOut"][]>([]);
  const [available, setAvailable] = useState<Schemas["AvailablePackage"][]>([]);
  const [preview, setPreview] = useState<Schemas["PreviewOut"] | null>(null);
  const [outcome, setOutcome] = useState<Schemas["ImportOut"] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [toActivate, setToActivate] = useState<Schemas["DataVersionOut"] | null>(null);
  const [activated, setActivated] = useState<string | null>(null);

  const load = useCallback(() => {
    unwrap(api.GET("/data-versions")).then(setVersions).catch(setError);
    unwrap(api.GET("/packages/available")).then(setAvailable).catch(setError);
  }, []);
  useEffect(load, [load]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  function previewAvailable(name: string) {
    void run(async () => {
      setOutcome(null);
      setPreview(await unwrap(api.POST("/packages/preview", { body: { name } })));
    });
  }

  function upload(file: File) {
    void run(async () => {
      setOutcome(null);
      const response = await fetch(`${API_BASE}/packages/upload`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/zip" },
        body: file,
      });
      const body = (await response.json()) as Schemas["PreviewOut"] | { detail?: string };
      if (!response.ok) {
        throw new ApiError(response.status, String((body as { detail?: string }).detail));
      }
      setPreview(body as Schemas["PreviewOut"]);
    });
  }

  function confirmImport() {
    if (!preview) return;
    setActivated(null);
    void run(async () => {
      const body =
        preview.staging_id !== null && preview.staging_id !== undefined
          ? { staging_id: preview.staging_id }
          : { name: preview.source };
      setOutcome(await unwrap(api.POST("/packages/import", { body })));
      setPreview(null);
      load();
      await refreshDataVersion();
    });
  }

  function activate(dv: Schemas["DataVersionOut"]) {
    void run(async () => {
      setPreview(null);
      setOutcome(
        await unwrap(
          api.POST("/data-versions/{data_version_id}/activate", {
            params: { path: { data_version_id: dv.id } },
          }),
        ),
      );
      setActivated(dv.version);
      setToActivate(null);
      load();
      await refreshDataVersion();
    });
  }

  const active = versions.find((v) => v.active);
  return (
    <section aria-labelledby="packages-title">
      <h3 id="packages-title">{t("admin.packages")}</h3>
      <p data-testid="active-version">
        {active
          ? t("admin.active_version", { package: active.package_id, version: active.version })
          : t("study.no_data")}
      </p>
      <table>
        <caption>{t("admin.imported_versions")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("admin.version")}</th>
            <th scope="col">{t("admin.imported_at")}</th>
            <th scope="col">{t("admin.status")}</th>
            <th scope="col">{t("admin.action")}</th>
          </tr>
        </thead>
        <tbody>
          {versions.map((v) => (
            <tr key={v.id}>
              <th scope="row">
                {v.package_id} {v.version}
              </th>
              <td>{v.imported_at}</td>
              <td>{v.active ? t("admin.is_active") : t("admin.kept")}</td>
              <td>
                {!v.active && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      setOutcome(null);
                      setToActivate(v);
                    }}
                  >
                    {t("admin.activate", { version: v.version })}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {toActivate && (
        <div role="alertdialog" className="panel" aria-labelledby="activate-question">
          <p id="activate-question">
            {t("admin.activate_confirm", {
              package: toActivate.package_id,
              version: toActivate.version,
            })}
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              activate(toActivate);
            }}
          >
            {t("admin.activate_yes")}
          </button>{" "}
          <button
            type="button"
            onClick={() => {
              setToActivate(null);
            }}
          >
            {t("admin.cancel")}
          </button>
        </div>
      )}

      <h4>{t("admin.available")}</h4>
      <ul>
        {available.map((p) => (
          <li key={p.name}>
            {p.package_id} {p.version} ({p.created}){" "}
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                previewAvailable(p.name);
              }}
            >
              {t("admin.preview", { name: p.name })}
            </button>
          </li>
        ))}
      </ul>
      <label>
        {t("admin.upload")}{" "}
        <input
          type="file"
          accept=".zip,.tar,.tar.gz,.tgz"
          disabled={busy}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) upload(file);
          }}
        />
      </label>
      <ErrorMessage error={error} />
      {preview && (
        <PreviewView
          preview={preview}
          busy={busy}
          onConfirm={confirmImport}
          onCancel={() => {
            setPreview(null);
          }}
        />
      )}
      {outcome && (
        <div role="status" className="panel" data-testid="import-outcome">
          <p>
            {activated
              ? t("admin.activated", { version: activated })
              : outcome.noop
                ? t("admin.noop")
                : t("admin.imported", { id: outcome.data_version_id })}
          </p>
          {outcome.baseline_run_id && (
            <p>
              <Link to={`/runs/${outcome.baseline_run_id}`}>{t("admin.baseline_run")}</Link>
            </p>
          )}
          {outcome.revalidation.length > 0 && (
            <>
              <p>{t("admin.revalidation")}</p>
              <ul>
                {outcome.revalidation.map((r) => (
                  <li key={r.scenario_id}>
                    <Link to={`/scenarios/${r.scenario_id}`}>{r.name}</Link>:{" "}
                    {r.problems.map((x) => serverText(t, x)).join("; ")}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  );
}

function PreviewView({
  preview,
  busy,
  onConfirm,
  onCancel,
}: {
  preview: Schemas["PreviewOut"];
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useT();
  const blocked = preview.problems.length > 0;
  return (
    <section className="panel" aria-labelledby="preview-title" data-testid="package-preview">
      <h4 id="preview-title">
        {t("admin.preview_title", { package: preview.package_id, version: preview.version })}
      </h4>
      <p>
        {label(t, "preview_status", preview.status)} ·{" "}
        {preview.active
          ? t("admin.against", { version: preview.active.version ?? "" })
          : t("admin.first_import")}{" "}
        · {t("admin.schema", { version: preview.schema_version })}
      </p>
      <table>
        <caption>{t("admin.changes_per_layer")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("admin.layer")}</th>
            <th scope="col">{t("admin.added")}</th>
            <th scope="col">{t("admin.changed")}</th>
            <th scope="col">{t("admin.closed")}</th>
            <th scope="col">{t("admin.unchanged")}</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(preview.layers).map(([layer, d]) => (
            <tr key={layer}>
              <th scope="row">{label(t, "layer", layer)}</th>
              <td>{d.added.join(", ") || "—"}</td>
              <td>{d.changed.map((c) => `${c.id} (${c.fields.join(", ")})`).join("; ") || "—"}</td>
              <td>{d.closed.join(", ") || "—"}</td>
              <td>{d.unchanged}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {preview.coverage_changes.length > 0 && (
        <>
          <p>{t("admin.coverage_changes")}</p>
          <ul>
            {preview.coverage_changes.map((c) => (
              <li key={`${c.municipality_id}-${c.layer}`}>
                {c.municipality_id} / {label(t, "layer", c.layer)}:{" "}
                {label(t, "coverage", c.before ?? "missing")} → {label(t, "coverage", c.after)}
              </li>
            ))}
          </ul>
        </>
      )}
      <h5>{t("admin.changelog")}</h5>
      <ul>
        {preview.changelog.map((c) => (
          <li key={String(c.version)}>
            {String(c.version)}: {String(c.changes)}
          </li>
        ))}
      </ul>
      {(preview.warnings.length > 0 || preview.problems.length > 0) && (
        <p className="muted" data-testid="package-check-note">
          {t("admin.package_check_english")}
        </p>
      )}
      {preview.warnings.map((w) => (
        <p key={w} className="warning" role="note">
          {w}
        </p>
      ))}
      {preview.problems.map((p) => (
        <p key={p} className="error" role="alert">
          {p}
        </p>
      ))}
      <p className="actions">
        <button type="button" onClick={onConfirm} disabled={busy || blocked}>
          {preview.status === "same_version" ? t("admin.confirm_noop") : t("admin.confirm_import")}
        </button>
        <button type="button" onClick={onCancel}>
          {t("admin.cancel")}
        </button>
      </p>
    </section>
  );
}
