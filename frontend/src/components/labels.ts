import en from "../i18n/en.json";
import type { MessageKey, Translate } from "../i18n/context";

/** Translate a dynamic value (status, role, indicator id …) with a prefix; fall back to the id. */
export function label(t: Translate, prefix: string, id: string | null | undefined): string {
  if (id === null || id === undefined) return "—";
  const key = `${prefix}.${id}`;
  return key in en ? t(key as MessageKey) : id;
}

/** Format a number for display (locale-aware, at most two decimals). */
export function num(value: number | null | undefined, lang: string): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString(lang === "el" ? "el-GR" : "en-GB", { maximumFractionDigits: 2 });
}

/** Whether an indicator is a probability (unit `probability`): shown on a fixed 0–1 scale. */
export function isProbability(indicator: { unit: string } | null | undefined): boolean {
  return indicator?.unit === "probability";
}

/**
 * A central value with its interval, for example `0.42 (0.31–0.55)` or `12 min (10–14)`.
 * Deterministic values say so instead of showing an empty interval; never a bare number.
 */
export function intervalText(
  t: Translate,
  lang: string,
  value: number | null | undefined,
  low: number | null | undefined,
  high: number | null | undefined,
  unit = "",
): string {
  if (value === null || value === undefined) return t("result.not_available");
  const suffix = unit && unit !== "1" && unit !== "probability" ? ` ${unit}` : "";
  if (low === high && low === value) {
    return `${num(value, lang)}${suffix} (${t("result.deterministic")})`;
  }
  return `${num(value, lang)}${suffix} (${num(low, lang)}–${num(high, lang)})`;
}

/**
 * Name of a run's interval from its quantile levels (ADR 0017): `[0.05, 0.95]` → "90 % interval",
 * asymmetric levels → "10–95 % quantile interval", missing levels → a generic name.
 */
export function intervalLabel(
  t: Translate,
  lang: string,
  levels: readonly number[] | null | undefined,
): string {
  const [low, high] = levels ?? [];
  if (levels?.length !== 2 || low === undefined || high === undefined) {
    return t("result.interval_unknown");
  }
  if (Math.abs(low + high - 1) < 1e-9) {
    return t("result.interval_central", { p: num((high - low) * 100, lang) });
  }
  return t("result.interval_quantiles", { low: num(low * 100, lang), high: num(high * 100, lang) });
}
