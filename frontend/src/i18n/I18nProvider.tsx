import { useCallback, useMemo, useState, type ReactNode } from "react";

import { I18nContext, format, type Lang, type MessageKey } from "./context";
import el from "./el.json";
import en from "./en.json";

const catalogs: Record<Lang, Record<MessageKey, string>> = { en, el };
const STORAGE_KEY = "sn-lang";

function initialLang(): Lang {
  const stored = typeof localStorage === "undefined" ? null : localStorage.getItem(STORAGE_KEY);
  return stored === "el" ? "el" : "en";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    localStorage.setItem(STORAGE_KEY, next);
    document.documentElement.lang = next;
  }, []);
  const value = useMemo(
    () => ({
      lang,
      setLang,
      t: (key: MessageKey, vars?: Record<string, string | number>) =>
        format(catalogs[lang][key], vars),
    }),
    [lang, setLang],
  );
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
