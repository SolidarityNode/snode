import type { Schemas } from "../api/client";
import { useT } from "../i18n/context";
import { label, num } from "./labels";

interface Props {
  run: Pick<Schemas["RunOut"], "status" | "progress" | "error" | "can_cancel">;
  onCancel?: () => void;
  cancelling?: boolean;
}

/** Status, progress bar and cancel button of a run. */
export function RunStatus({ run, onCancel, cancelling = false }: Props) {
  const { t, lang } = useT();
  const active = run.status === "queued" || run.status === "running";
  return (
    <section className="run-status" aria-labelledby="run-status-title">
      <h3 id="run-status-title">{t("run.status_title")}</h3>
      <p>
        <span className={`badge badge--${run.status}`} data-testid="run-status">
          {label(t, "status", run.status)}
        </span>{" "}
        {active && (
          <span aria-live="polite">
            {t("run.progress_value", { value: num(run.progress, lang) })}
          </span>
        )}
      </p>
      {active && (
        <progress
          max={100}
          value={run.progress}
          aria-label={t("run.progress_label")}
          data-testid="run-progress"
        />
      )}
      {run.status === "failed" && run.error && (
        <p role="alert" className="error">
          {t("run.failed_with", { error: run.error })}
        </p>
      )}
      {run.status === "cancelled" && <p role="status">{run.error ?? t("run.cancelled")}</p>}
      {active && run.can_cancel && onCancel && (
        <button type="button" onClick={onCancel} disabled={cancelling}>
          {cancelling ? t("run.cancelling") : t("run.cancel")}
        </button>
      )}
    </section>
  );
}
