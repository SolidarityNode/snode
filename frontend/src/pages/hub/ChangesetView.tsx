import { useState } from "react";
import { Link } from "react-router";

import { unwrap } from "../../api/client";
import { hubApi, hubUrl, type Changeset, type Check } from "../../api/hub";
import { useSession } from "../../app/session";
import { ErrorMessage } from "../../components/ErrorMessage";
import { label } from "../../components/labels";
import { useT } from "../../i18n/context";
import { ChecksList } from "./ChecksList";
import { text } from "./shared";

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "string" ? value : JSON.stringify(value);
}

/** The value of a changed field, for example `services.S-SD.throughput` or `location`. */
function fieldValue(state: Record<string, unknown> | null | undefined, field: string): string {
  if (!state) return "—";
  if (field === "location") return show(state._xy);
  const parts = field.replace(/ \((added|removed)\)$/, "").split(".");
  let value: unknown = state;
  for (const part of parts) {
    value =
      value && typeof value === "object" ? (value as Record<string, unknown>)[part] : undefined;
  }
  return show(value);
}

/**
 * A changeset: its validation report and the preview of changes (added, updated with a
 * field-level diff, closed), with approve and reject for administrators.
 */
export function ChangesetView({
  changeset,
  onChange,
}: {
  changeset: Changeset;
  onChange: (cs: Changeset) => void;
}) {
  const { t } = useT();
  const { user } = useSession();
  const [comment, setComment] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const summary = changeset.summary ?? { add: 0, update: 0, close: 0 };
  const entries = (changeset.report.entries ?? []) as Check[];
  const errors = changeset.errors ?? 0;
  const pending = changeset.status === "pending";
  const isAdmin = user?.role === "admin";
  const closing = summary.close ?? 0;

  async function decide(kind: "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      const path = { params: { path: { changeset_id: changeset.id } } };
      const next =
        kind === "approve"
          ? await unwrap(
              hubApi.POST("/hub/changesets/{changeset_id}/approve", {
                ...path,
                body: {
                  comment,
                  confirm_close: changeset.complete_list ? Number(confirm) : null,
                },
              }),
            )
          : await unwrap(
              hubApi.POST("/hub/changesets/{changeset_id}/reject", { ...path, body: { comment } }),
            );
      onChange(next);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="panel"
      aria-labelledby={`cs-${String(changeset.id)}`}
      data-testid="changeset"
    >
      <h3 id={`cs-${String(changeset.id)}`}>
        {t("hub.changeset.title", {
          id: changeset.id,
          municipality: changeset.municipality_id,
        })}
      </h3>
      <p data-testid="changeset-status">
        {label(t, "hub.changeset_status", changeset.status)} ·{" "}
        {label(t, "hub.changeset_kind", changeset.kind)} · {changeset.file_name ?? ""} ·{" "}
        {t("hub.changeset.by", { user: changeset.created_by_name ?? "—" })}
        {changeset.is_correction && <> · {t("hub.changeset.correction")}</>}
      </p>
      <p data-testid="changeset-summary">
        {t("hub.changeset.summary", {
          add: summary.add ?? 0,
          update: summary.update ?? 0,
          close: closing,
          errors,
        })}
      </p>

      <h4>{t("hub.report.title")}</h4>
      <p>
        <a href={hubUrl(`/hub/changesets/${String(changeset.id)}/report`, { format: "csv" })}>
          {t("hub.report.csv")}
        </a>{" "}
        ·{" "}
        <a href={hubUrl(`/hub/changesets/${String(changeset.id)}/report`, { format: "xlsx" })}>
          {t("hub.report.xlsx")}
        </a>
      </p>
      <ChecksList checks={entries} testId="validation-report" />

      <h4>{t("hub.preview.title")}</h4>
      {changeset.items.length === 0 ? (
        <p>{t("hub.preview.nothing")}</p>
      ) : (
        <table data-testid="changeset-preview">
          <caption className="sr-only">{t("hub.preview.title")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("hub.preview.action")}</th>
              <th scope="col">{t("hub.facility")}</th>
              <th scope="col">{t("hub.preview.rows")}</th>
              <th scope="col">{t("hub.preview.changes")}</th>
            </tr>
          </thead>
          <tbody>
            {changeset.items.map((i) => (
              <tr key={i.item_no} data-action={i.action}>
                <td>{label(t, "hub.action", i.action)}</td>
                <th scope="row">
                  {i.facility_id ? (
                    <Link to={`/facilities/${i.facility_id}`}>{i.facility_id}</Link>
                  ) : (
                    t("hub.preview.new_id")
                  )}{" "}
                  · {i.label}
                </th>
                <td>{i.rows.join(", ") || "—"}</td>
                <td>
                  {i.action === "update" ? (
                    <ul className="diff">
                      {i.fields.map((f) => (
                        <li key={f}>
                          <code>{f}</code>: {fieldValue(i.before, f)} → {fieldValue(i.after, f)}
                        </li>
                      ))}
                    </ul>
                  ) : i.action === "close" ? (
                    t("hub.preview.closed_note")
                  ) : (
                    t("hub.preview.added_note", {
                      quality: label(t, "quality", text(i.after?.quality)),
                      unit: text(i.after?.unit_id) || "—",
                    })
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <ErrorMessage error={error} />
      {pending && isAdmin && (
        <div className="subform">
          {changeset.complete_list && (
            <label>
              {t("hub.changeset.confirm_close", {
                count: closing,
                municipality: changeset.municipality_id,
              })}{" "}
              <input
                inputMode="numeric"
                value={confirm}
                onChange={(e) => {
                  setConfirm(e.target.value);
                }}
              />
            </label>
          )}
          <label>
            {t("hub.changeset.comment")}{" "}
            <input
              value={comment}
              onChange={(e) => {
                setComment(e.target.value);
              }}
            />
          </label>
          <p className="actions">
            <button
              type="button"
              disabled={busy || errors > 0}
              onClick={() => void decide("approve")}
            >
              {t("hub.changeset.approve")}
            </button>
            <button type="button" disabled={busy} onClick={() => void decide("reject")}>
              {t("hub.changeset.reject")}
            </button>
          </p>
          {errors > 0 && <p className="warning">{t("hub.changeset.fix_errors")}</p>}
        </div>
      )}
      {pending && !isAdmin && <p className="muted">{t("hub.changeset.waits_for_admin")}</p>}
      {!pending && changeset.decided_by_name && (
        <p>
          {t("hub.changeset.decided", {
            status: label(t, "hub.changeset_status", changeset.status),
            user: changeset.decided_by_name,
          })}
          {changeset.decision_comment ? ` · ${changeset.decision_comment}` : ""}
        </p>
      )}
    </section>
  );
}
