'use client';

import { createContext, useContext, useCallback, useEffect, type ReactNode } from 'react';
import tr from './translations/tr.json';

/**
 * Gökdoğan Intelligence v1.0.0 dağıtımı kullanıcı arayüzünü yalnızca Türkçe sunar.
 * Eski upstream çeviri dosyaları kaynak uyumluluğu için depoda tutulabilir;
 * fakat çalışma zamanında seçilebilir dil yalnızca Türkçedir.
 */
export type Locale = 'tr';

export const LOCALES: ReadonlyArray<{ code: Locale; label: string }> = [
  { code: 'tr', label: 'Türkçe' },
];

const translations: Record<Locale, Record<string, Record<string, string>>> = {
  tr,
};

function resolve(obj: Record<string, unknown>, path: string): string {
  const parts = path.split('.');
  let current: unknown = obj;
  for (const part of parts) {
    if (current && typeof current === 'object' && part in (current as Record<string, unknown>)) {
      current = (current as Record<string, unknown>)[part];
    } else {
      return path;
    }
  }
  return typeof current === 'string' ? current : path;
}

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string) => string;
}

const I18nContext = createContext<I18nContextValue>({
  locale: 'tr',
  setLocale: () => {},
  t: (key: string) => resolve(tr as unknown as Record<string, unknown>, key),
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const locale: Locale = 'tr';

  const handleSetLocale = useCallback((_newLocale: Locale) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('gokdogan_locale', 'tr');
      localStorage.removeItem('sb_locale');
    }
  }, []);

  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.dir = 'ltr';
      document.documentElement.lang = 'tr';
    }
    if (typeof window !== 'undefined') {
      localStorage.setItem('gokdogan_locale', 'tr');
      localStorage.removeItem('sb_locale');
    }
  }, []);

  const t = useCallback((key: string): string => {
    const dict = translations[locale] ?? translations.tr;
    return resolve(dict as unknown as Record<string, unknown>, key);
  }, [locale]);

  return (
    <I18nContext.Provider value={{ locale, setLocale: handleSetLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useTranslation() {
  return useContext(I18nContext);
}

export { I18nContext };
