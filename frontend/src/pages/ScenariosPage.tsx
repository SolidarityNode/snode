import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";

import { api, unwrap, type Schemas } from "../api/client";
import { canEdit, useSession } from "../app/session";
import { ErrorMessage } from "../components/ErrorMessage";
import { LatestRun } from "../components/LatestRun";
import { label } from "../components/labels";
import { useT } from "../i18n/context";
import { serverText } from "../i18n/server";

type Item = Schemas["ScenarioListItem"];

export function ScenariosPage() {
  const { t } = useT();
  const { user } = useSession();
  const navigate = useNavigate();
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    unwrap(api.GET("/scenarios")).then(setItems).catch(setError);
  }, []);
  useEffect(load, [load]);

  async function act(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      load();
    } catch (e) {
      setError(e);
    }
  }

  const mine = items?.filter((s) => s.owner_id === user?.id) ?? [];
  const others = items?.filter((s) => s.owner_id !== user?.id) ?? [];
  const shared = others.filter((s) => s.visibility === "shared");
  // Only administrators receive other users' private scenarios (ADR 0015).
  const othersPrivate = others.filter((s) => s.visibility === "private");

  function visibility(s: Item): string {
    return s.visibility === "private" && s.owner_id !== user?.id
      ? t("scenarios.private_owner", { owner: s.owner ?? t("scenarios.system") })
      : label(t, "visibility", s.visibility);
  }

  function table(rows: Item[], caption: string, empty: string) {
    if (rows.length === 0) return <p>{empty}</p>;
    return (
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">{t("scenarios.name")}</th>
            <th scope="col">{t("scenarios.version")}</th>
            <th scope="col">{t("scenarios.data_version")}</th>
            <th scope="col">{t("scenarios.visibility")}</th>
            <th scope="col">{t("scenarios.owner")}</th>
            <th scope="col">{t("scenarios.latest_run")}</th>
            <th scope="col">{t("scenarios.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.id}>
              <th scope="row">
                <Link to={`/scenarios/${s.id}`}>{s.name}</Link>
                {s.problems.length > 0 && (
                  <p className="warning" role="note">
                    {t("scenarios.needs_attention", {
                      problems: s.problems.map((p) => serverText(t, p)).join("; "),
                    })}
                  </p>
                )}
              </th>
              <td>{s.latest_version}</td>
              <td>{s.data_version.version}</td>
              <td>{visibility(s)}</td>
              <td>{s.owner ?? t("scenarios.system")}</td>
              <td>
                <LatestRun item={s} user={user} />
              </td>
              <td className="actions">
                {(s.can_edit || (s.is_baseline && canEdit(user))) && s.problems.length === 0 && (
                  <button
                    type="button"
                    onClick={() =>
                      void act(async () => {
                        const run = await unwrap(
                          api.POST("/runs", { body: { scenario_id: s.id, seed: 1, force: false } }),
                        );
                        void navigate(`/runs/${run.id}`);
                      })
                    }
                  >
                    {t("scenarios.run")}
                  </button>
                )}
                {canEdit(user) && !s.is_baseline && (
                  <button
                    type="button"
                    onClick={() =>
                      void act(() =>
                        unwrap(
                          api.POST("/scenarios/{scenario_id}/duplicate", {
                            params: { path: { scenario_id: s.id } },
                          }),
                        ),
                      )
                    }
                  >
                    {t("scenarios.duplicate")}
                  </button>
                )}
                {s.can_edit && (
                  <button
                    type="button"
                    onClick={() => {
                      if (window.confirm(t("scenarios.confirm_delete", { name: s.name }))) {
                        void act(() =>
                          api.DELETE("/scenarios/{scenario_id}", {
                            params: { path: { scenario_id: s.id } },
                          }),
                        );
                      }
                    }}
                  >
                    {t("scenarios.delete")}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <section aria-labelledby="scenarios-title">
      <h2 id="scenarios-title">{t("scenarios.title")}</h2>
      {canEdit(user) && (
        <p>
          <Link className="button" to="/scenarios/new">
            {t("scenarios.new")}
          </Link>
        </p>
      )}
      <ErrorMessage error={error} />
      {items === null ? (
        <p role="status">{t("common.loading")}</p>
      ) : (
        <>
          {table(mine, t("scenarios.mine"), t("scenarios.none_mine"))}
          {table(shared, t("scenarios.shared"), t("scenarios.none_shared"))}
          {othersPrivate.length > 0 && table(othersPrivate, t("scenarios.others_private"), "")}
        </>
      )}
    </section>
  );
}
