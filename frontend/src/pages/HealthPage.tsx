import { useEffect, useState } from "react";

import { getHealth, getVersion, type Version } from "../api/client";
import { useT } from "../i18n/context";

type State =
  | { kind: "loading" }
  | { kind: "ok"; version: Version | null }
  | { kind: "error"; message: string };

export function HealthPage() {
  const { t } = useT();
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then(async () => {
        const version = await getVersion(controller.signal).catch(() => null);
        setState({ kind: "ok", version });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ kind: "error", message: error instanceof Error ? error.message : "unknown" });
      });
    return () => {
      controller.abort();
    };
  }, []);

  return (
    <section aria-labelledby="health-title">
      <h2 id="health-title">{t("health.title")}</h2>
      {state.kind === "loading" && <p role="status">{t("health.checking")}</p>}
      {state.kind === "ok" && (
        <p role="status" data-testid="health-status">
          {t("health.status")} <strong>ok</strong>
          {state.version &&
            ` ${t("health.versions", { backend: state.version.version, core: state.version.core_version })}`}
        </p>
      )}
      {state.kind === "error" && (
        <p role="alert" data-testid="health-status">
          {t("health.unreachable", { message: state.message })}
        </p>
      )}
    </section>
  );
}
