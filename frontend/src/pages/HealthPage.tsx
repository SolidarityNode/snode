import { useEffect, useState } from "react";

import { getHealth, getVersion, type Version } from "../api/client";

type State =
  | { kind: "loading" }
  | { kind: "ok"; version: Version | null }
  | { kind: "error"; message: string };

export function HealthPage() {
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
      <h2 id="health-title">Backend health</h2>
      {state.kind === "loading" && <p role="status">Checking…</p>}
      {state.kind === "ok" && (
        <p role="status" data-testid="health-status">
          Backend status: <strong>ok</strong>
          {state.version &&
            ` (backend ${state.version.version}, core ${state.version.core_version})`}
        </p>
      )}
      {state.kind === "error" && (
        <p role="alert" data-testid="health-status">
          Backend unreachable: {state.message}
        </p>
      )}
    </section>
  );
}
