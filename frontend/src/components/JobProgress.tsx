import { useEffect, useState } from "react";

import { unwrap } from "../api/client";
import { hubApi, jobFinished, type Job } from "../api/hub";
import { useSession } from "../app/session";
import { useT } from "../i18n/context";
import { serverText } from "../i18n/server";
import { label } from "./labels";

/**
 * Progress of a hub job (base step or package assembly), polled every second until it finishes.
 * Administrators can cancel it; a cancelled or failed job stores nothing.
 */
export function JobProgress({
  jobId,
  onFinished,
}: {
  jobId: string;
  onFinished?: (job: Job) => void;
}) {
  const { t } = useT();
  const { user } = useSession();
  const [job, setJob] = useState<Job | null>(null);

  useEffect(() => {
    let timer: number | undefined;
    let stopped = false;
    async function poll() {
      try {
        const next = await unwrap(
          hubApi.GET("/hub/jobs/{job_id}", { params: { path: { job_id: jobId } } }),
        );
        if (stopped) return;
        setJob(next);
        if (jobFinished(next)) {
          onFinished?.(next);
          return;
        }
      } catch {
        /* transient: try again */
      }
      timer = window.setTimeout(() => void poll(), 1000);
    }
    void poll();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [jobId, onFinished]);

  if (!job) return <p role="status">{t("common.loading")}</p>;
  return (
    <div className="panel" data-testid="job-progress">
      <p role="status">
        <span className={`badge badge--${job.status}`} data-testid="job-status">
          {label(t, "status", job.status)}
        </span>{" "}
        {t("hub.job.progress", { percent: Math.round(job.progress) })}
      </p>
      <progress max={100} value={job.progress} aria-label={t("hub.job.progress_label")} />
      {job.error && <p className="error">{serverText(t, job.error)}</p>}
      {!jobFinished(job) && user?.role === "admin" && (
        <button
          type="button"
          onClick={() => {
            void hubApi.POST("/hub/jobs/{job_id}/cancel", { params: { path: { job_id: jobId } } });
          }}
        >
          {t("hub.job.cancel")}
        </button>
      )}
    </div>
  );
}
