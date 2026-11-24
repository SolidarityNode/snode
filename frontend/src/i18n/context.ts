import { createContext, useContext } from "react";

import en from "./en.json";

export type Lang = "en" | "el";
export type MessageKey = keyof typeof en;
export type Translate = (key: MessageKey, vars?: Record<string, string | number>) => string;

export interface I18n {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: Translate;
}

export function format(template: string, vars?: Record<string, string | number>): string {
  if (!vars) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match,
  );
}

export const I18nContext = createContext<I18n>({
  lang: "en",
  setLang: () => undefined,
  t: (key, vars) => format(en[key], vars),
});

/** Translation hook: every user-facing string goes through `t` (en.json / el.json). */
export function useT(): I18n {
  return useContext(I18nContext);
}
