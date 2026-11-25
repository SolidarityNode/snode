import { Link } from "react-router";

import type { Schemas } from "../api/client";
import { canEdit } from "../app/session";
import { useT } from "../i18n/context";
import { label, num } from "./labels";

type Summary = Schemas["RunSummary"];

function Status({ run }: { run: Summary }) {
  const { t } = useT();
  return (
    <>
      <span className={`badge badge--${run.status}`}>{label(t, "status", run.status)}</span>
      {run.status === "running" && ` ${num(run.progress, "en")} %`}
    </>
  );
}

/**
 * The latest run of a scenario, linked only when that run exists: on the active data version,
 * else the newest on another data version ("Latest run on data X"), else "Not run yet" (viewers
 * are told to ask an analyst).
 */
export function LatestRun({
  item,
  user,
}: {
  item: Pick<Schemas["ScenarioListItem"], "latest_run" | "latest_run_other_data">;
  user: Schemas["UserOut"] | null;
}) {
  const { t } = useT();
  if (item.latest_run) {
    return (
      <Link to={`/runs/${item.latest_run.id}`} data-testid="latest-run">
        <Status run={item.latest_run} />{" "}
        <span className="muted">({item.latest_run.package_version})</span>
      </Link>
    );
  }
  if (item.latest_run_other_data) {
    return (
      <Link to={`/runs/${item.latest_run_other_data.id}`} data-testid="latest-run">
        {t("scenarios.latest_on_data", { version: item.latest_run_other_data.package_version })}{" "}
        <Status run={item.latest_run_other_data} />
      </Link>
    );
  }
  return (
    <span className="muted" data-testid="latest-run">
      {t("scenarios.not_run_yet")}
      {!canEdit(user) && ` ${t("scenarios.ask_analyst")}`}
    </span>
  );
}
