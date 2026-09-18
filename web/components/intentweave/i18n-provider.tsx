"use client";

import { createContext, useContext, useMemo, useState } from "react";
import { dictionaries, type Dictionary, type Locale } from "@/lib/i18n/dictionaries";

const LANGUAGE_KEY = "intentweave.locale";

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: Dictionary;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => {
    if (typeof window === "undefined") {
      return "en";
    }

    const stored = window.localStorage.getItem(LANGUAGE_KEY);
    return stored === "en" || stored === "zh-TW" ? stored : "en";
  });

  function setLocale(nextLocale: Locale) {
    setLocaleState(nextLocale);
    window.localStorage.setItem(LANGUAGE_KEY, nextLocale);
    window.dispatchEvent(new Event("intentweave-language-change"));
  }

  const value = useMemo(
    () => ({
      locale,
      setLocale,
      t: dictionaries[locale],
    }),
    [locale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);

  if (!context) {
    throw new Error("useI18n must be used within I18nProvider");
  }

  return context;
}
