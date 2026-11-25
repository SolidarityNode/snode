import { useT } from "../i18n/context";
import { intervalText } from "./labels";

interface Props {
  value: number | null | undefined;
  low: number | null | undefined;
  high: number | null | undefined;
  unit?: string;
  /** Name of the interval, for example "90 % interval" (from `intervalLabel`). */
  interval?: string;
}

/**
 * A median with its interval, for example "0.42 (0.31–0.55)"; never a bare number. The statistic
 * is named in the column heading and in the tooltip ("median (90 % interval)").
 */
export function IntervalValue({ value, low, high, unit = "", interval }: Props) {
  const { t, lang } = useT();
  const text = intervalText(t, lang, value, low, high, unit);
  if (value === null || value === undefined) {
    return <span className="muted">{text}</span>;
  }
  return (
    <span
      data-testid="interval"
      title={t("result.statistic", { interval: interval ?? t("result.interval_unknown") })}
    >
      {text}
    </span>
  );
}
