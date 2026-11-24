import { useEffect, useState } from "react";

import { FRONTEND_COMMIT, getVersion, type Version } from "../api/client";

/**
 * Footer line telling a tester exactly which build is under test: backend version, git
 * commit and APP_ENV from `/version`, plus the commit the frontend was built from.
 */
export function BuildInfo() {
  const [version, setVersion] = useState<Version | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getVersion(controller.signal)
      .then(setVersion)
      .catch(() => {
        setVersion(null);
      });
    return () => {
      controller.abort();
    };
  }, []);

  const backend = version
    ? `backend ${version.version} (${version.git_commit}, ${version.app_env})`
    : "backend unavailable";
  return (
    <span data-testid="build-info">
      {backend} · frontend {FRONTEND_COMMIT}
    </span>
  );
}
