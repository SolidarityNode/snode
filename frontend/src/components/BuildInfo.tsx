import { useEffect, useState } from "react";

import { FRONTEND_COMMIT, getVersion, type Version } from "../api/client";
import { useT } from "../i18n/context";

/**
 * Footer line telling a tester exactly which build is under test: backend version, git
 * commit and APP_ENV from `/version`, plus the commit the frontend was built from.
 */
export function BuildInfo() {
  const { t } = useT();
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
    ? t("footer.backend", {
        version: version.version,
        commit: version.git_commit,
        env: version.app_env,
      })
    : t("footer.backend_unavailable");
  return (
    <span data-testid="build-info">
      {backend} · {t("footer.frontend", { commit: FRONTEND_COMMIT })}
    </span>
  );
}
