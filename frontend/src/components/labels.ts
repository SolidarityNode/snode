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
