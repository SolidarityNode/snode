import { useState } from "react";
import { Link } from "react-router";

import { unwrap } from "../../api/client";
import { hubApi } from "../../api/hub";
import { useSession } from "../../app/session";
import { ErrorMessage } from "../../components/ErrorMessage";
import { label } from "../../components/labels";
import { useT } from "../../i18n/context";
import { type Filter, useCoverage } from "./shared";

export function FilterSelect({
  value,
  onChange,
}: {
  value: Filter;
  onChange: (f: Filter) => void;
}) {
  const { t } = useT();
  return (
    <label>
      {t("hub.filter.label")}{" "}
      <select
        value={value}
        onChange={(e) => {
          onChange(e.target.value as Filter);
        }}
      >
        <option value="all">{t("hub.filter.all")}</option>
        <option value="onboarded">{t("hub.filter.onboarded")}</option>
        <option value="not_onboarded">{t("hub.filter.not_onboarded")}</option>
      </select>
    </label>
  );
}

/** Onboarding list: every municipality known to the hub with its onboarding status. */
export function HubOnboardingPage() {
  const { t } = useT();
  const { user } = useSession();
  const [filter, setFilter] = useState<Filter>("all");
  const { rows, error, reload } = useCoverage(filter);
  const [started, setStarted] = useState<string | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);

  async function start(municipality: string) {
    setActionError(null);
    try {
      await unwrap(
        hubApi.POST("/hub/onboarding/{municipality_id}/base", {
          params: { path: { municipality_id: municipality } },
        }),
      );
      setStarted(municipality);
      reload();
    } catch (e) {
      setActionError(e);
    }
  }

  return (
    <section aria-labelledby="onboarding-title">
      <h2 id="onboarding-title">{t("hub.onboarding.title")}</h2>
      <p className="muted">{t("hub.onboarding.intro")}</p>
      <FilterSelect value={filter} onChange={setFilter} />
      <ErrorMessage error={error ?? actionError} />
      {started && (
        <p role="status">
          {t("hub.onboarding.started", { municipality: started })}{" "}
          <Link to={`/onboarding/${started}`}>{t("hub.onboarding.follow")}</Link>
        </p>
      )}
      <table data-testid="onboarding-list">
        <caption>{t("hub.onboarding.caption")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("hub.municipality")}</th>
            <th scope="col">{t("hub.name")}</th>
            <th scope="col">{t("hub.onboarding.status")}</th>
            <th scope="col">{t("admin.action")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.municipality_id} data-municipality={r.municipality_id}>
              <th scope="row">
                <Link to={`/onboarding/${r.municipality_id}`}>{r.municipality_id}</Link>
              </th>
              <td>{r.name}</td>
              <td>
                <span className={`badge badge--onboarding-${r.status}`}>
                  {label(t, "hub.status", r.status)}
                </span>
              </td>
              <td>
                {user?.role === "admin" && r.status === "not_started" && (
                  <button type="button" onClick={() => void start(r.municipality_id)}>
                    {t("hub.onboarding.start", { municipality: r.municipality_id })}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
