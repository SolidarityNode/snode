import { useEffect, useState, type SyntheticEvent } from "react";
import { useParams, useSearchParams } from "react-router";

import { unwrap } from "../../api/client";
import { hubApi, type Changeset, type HubSchemas } from "../../api/hub";
import { useSession } from "../../app/session";
import { ErrorMessage } from "../../components/ErrorMessage";
import { label } from "../../components/labels";
import { useT } from "../../i18n/context";
import { ChangesetView } from "./ChangesetView";
import { text } from "./shared";

type Facility = HubSchemas["FacilityOut"];
type History = HubSchemas["HistoryEntryOut"];

const FIELDS = [
  "name",
  "facility_type",
  "operating_hours",
  "public_phone",
  "public_email",
  "notes",
] as const;
const QUALITIES = ["open_data", "estimated", "verified_by_municipality"] as const;
const SERVICE_FIELDS = ["service_id", "places", "staff", "throughput", "throughput_unit"] as const;

/**
 * A facility's history (every approved change with author, date, source) and the manual edit
 * form. The form creates a pending changeset, like an import; `/facilities/new` adds one.
 */
export function HubFacilityPage() {
  const { facilityId = "new" } = useParams();
  const [params] = useSearchParams();
  const { t, lang } = useT();
  const { user } = useSession();
  const isNew = facilityId === "new";
  const [facility, setFacility] = useState<Facility | null>(null);
  const [history, setHistory] = useState<History[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [service, setService] = useState<Record<string, string>>({});
  const [close, setClose] = useState(false);
  const [comment, setComment] = useState("");
  const [result, setResult] = useState<Changeset | null>(null);
  const [error, setError] = useState<unknown>(null);
  const canEdit = user?.role === "admin" || user?.role === "analyst";
  const when = (iso: string | null | undefined) =>
    iso ? new Date(iso).toLocaleString(lang === "el" ? "el-GR" : "en-GB") : "—";

  useEffect(() => {
    if (isNew) return;
    unwrap(hubApi.GET("/hub/facilities", { params: { query: {} } }))
      .then((all) => {
        const found = all.find((f) => f.facility_id === facilityId) ?? null;
        setFacility(found);
        if (found) {
          setValues(
            Object.fromEntries(
              [...FIELDS, "quality"].map((k) => [
                k,
                k === "quality" ? found.quality : text(found.properties[k]),
              ]),
            ),
          );
        }
      })
      .catch(setError);
    unwrap(
      hubApi.GET("/hub/facilities/{facility_id}/history", {
        params: { path: { facility_id: facilityId } },
      }),
    )
      .then(setHistory)
      .catch(setError);
  }, [facilityId, isNew]);

  const municipality = facility?.municipality_id ?? params.get("municipality") ?? "";

  async function submit(e: SyntheticEvent) {
    e.preventDefault();
    setError(null);
    try {
      const services =
        isNew || service.service_id
          ? [
              {
                service_id: service.service_id ?? "",
                places: service.places ? Number(service.places) : null,
                staff: service.staff ? Number(service.staff) : null,
                throughput: service.throughput ? Number(service.throughput) : null,
                throughput_unit: service.throughput_unit ?? null,
              },
            ]
          : [];
      setResult(
        await unwrap(
          hubApi.POST("/hub/facilities/edits", {
            body: {
              municipality_id: municipality,
              facility_id: isNew ? null : facilityId,
              close,
              comment,
              values,
              services,
            },
          }),
        ),
      );
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section aria-labelledby="facility-title">
      <h2 id="facility-title">
        {isNew
          ? t("hub.facility.new_title", { municipality })
          : t("hub.facility.title", { id: facilityId })}
      </h2>
      {facility && (
        <p>
          {text(facility.properties.name)} · {facility.municipality_id} ·{" "}
          {label(t, "quality", facility.quality)} ·{" "}
          {facility.valid_to
            ? t("hub.facilities.closed_on", { date: facility.valid_to })
            : t("hub.facilities.open_since", { date: facility.valid_from })}
        </p>
      )}
      <ErrorMessage error={error} />

      {!isNew && (
        <>
          <h3>{t("hub.facility.history")}</h3>
          <ol data-testid="facility-history">
            {history.map((h) => (
              <li key={h.changeset_id}>
                {t("hub.facility.history_line", {
                  action: label(t, "hub.action", h.action),
                  changeset: h.changeset_id,
                  user: h.created_by_name ?? "—",
                  approver: h.decided_by_name ?? "—",
                  when: when(h.decided_at),
                  source: h.source,
                })}
                {h.fields.length > 0 && (
                  <>
                    {" "}
                    · <code>{h.fields.join(", ")}</code>
                  </>
                )}
                {h.comment ? ` · ${h.comment}` : ""}
              </li>
            ))}
          </ol>
        </>
      )}

      {canEdit && municipality && (
        <form className="subform" onSubmit={(e) => void submit(e)} aria-labelledby="edit-title">
          <h3 id="edit-title">{isNew ? t("hub.facility.add") : t("hub.facility.edit")}</h3>
          <p className="muted">{t("hub.facility.edit_note")}</p>
          {FIELDS.map((k) => (
            <label key={k}>
              {label(t, "hub.field", k)}{" "}
              <input
                value={values[k] ?? ""}
                required={isNew && (k === "name" || k === "facility_type")}
                onChange={(e) => {
                  setValues({ ...values, [k]: e.target.value });
                }}
              />
            </label>
          ))}
          <label>
            {t("hub.quality")}{" "}
            <select
              value={values.quality ?? ""}
              required={isNew}
              onChange={(e) => {
                setValues({ ...values, quality: e.target.value });
              }}
            >
              <option value="">—</option>
              {QUALITIES.map((q) => (
                <option key={q} value={q}>
                  {label(t, "quality", q)}
                </option>
              ))}
            </select>
          </label>
          {isNew &&
            (["x", "y"] as const).map((k) => (
              <label key={k}>
                {label(t, "hub.field", k)}{" "}
                <input
                  inputMode="decimal"
                  required
                  value={values[k] ?? ""}
                  onChange={(e) => {
                    setValues({ ...values, [k]: e.target.value });
                  }}
                />
              </label>
            ))}
          <fieldset>
            <legend>{isNew ? t("hub.facility.service") : t("hub.facility.service_change")}</legend>
            {SERVICE_FIELDS.map((k) => (
              <label key={k}>
                {label(t, "hub.field", k)}{" "}
                <input
                  value={service[k] ?? ""}
                  required={isNew && k === "service_id"}
                  onChange={(e) => {
                    setService({ ...service, [k]: e.target.value });
                  }}
                />
              </label>
            ))}
          </fieldset>
          {!isNew && (
            <label>
              <input
                type="checkbox"
                checked={close}
                onChange={(e) => {
                  setClose(e.target.checked);
                }}
              />{" "}
              {t("hub.facility.close")}
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
          <button type="submit">{t("hub.facility.propose")}</button>
        </form>
      )}
      {result && <ChangesetView changeset={result} onChange={setResult} />}
    </section>
  );
}
