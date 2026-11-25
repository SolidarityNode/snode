import { useT } from "../i18n/context";
import { intervalText } from "./labels";

interface Props {
  value: number | null | undefined;
  low: number | null | undefined;
  high: number | null | undefined;
  unit?: string;
}

/** A value with its interval, for example "0.42 (0.31–0.55)"; never a bare number. */
export function IntervalValue({ value, low, high, unit = "" }: Props) {
  const { t, lang } = useT();
  const text = intervalText(t, lang, value, low, high, unit);
  if (value === null || value === undefined) {
    return <span className="muted">{text}</span>;
  }
  return (
    <span data-testid="interval" title={t("result.interval_90")}>
      {text}
    </span>
  );
}
