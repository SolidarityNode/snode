import { useT } from "../i18n/context";
import { num } from "./labels";

interface Props {
  value: number | null | undefined;
  low: number | null | undefined;
  high: number | null | undefined;
  unit?: string;
}

/** A value with its interval; deterministic values say so explicitly (never a bare number). */
export function IntervalValue({ value, low, high, unit }: Props) {
  const { t, lang } = useT();
  if (value === null || value === undefined) {
    return <span className="muted">{t("result.not_available")}</span>;
  }
  const suffix = unit && unit !== "1" ? ` ${unit}` : "";
  if (low === high && low === value) {
    return (
      <span>
        {num(value, lang)}
        {suffix} <span className="muted">({t("result.deterministic")})</span>
      </span>
    );
  }
  return (
    <span>
      {num(value, lang)}
      {suffix}{" "}
      <span className="muted">
        [{num(low, lang)} – {num(high, lang)}] {t("result.interval_90")}
      </span>
    </span>
  );
}
