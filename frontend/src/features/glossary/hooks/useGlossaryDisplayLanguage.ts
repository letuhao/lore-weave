import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { loadPrefFromServer, syncPrefsToServer } from '@/lib/syncPrefs';

const PREF_KEY = 'glossary_display_lang_by_book';

export function useGlossaryDisplayLanguage(
  bookId: string,
  bookOriginalLanguage?: string,
) {
  const { accessToken } = useAuth();
  const defaultLang = bookOriginalLanguage ?? '';
  const [displayLanguage, setDisplayLanguageState] = useState(defaultLang);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!accessToken) {
      setDisplayLanguageState(defaultLang);
      setLoaded(true);
      return;
    }
    let cancelled = false;
    void loadPrefFromServer<Record<string, string>>(PREF_KEY, accessToken).then((map) => {
      if (cancelled) return;
      const saved = map?.[bookId];
      setDisplayLanguageState(saved ?? defaultLang);
      setLoaded(true);
    });
    return () => {
      cancelled = true;
    };
  }, [accessToken, bookId, defaultLang]);

  const setDisplayLanguage = useCallback(
    (lang: string) => {
      setDisplayLanguageState(lang);
      if (!accessToken) return;
      void loadPrefFromServer<Record<string, string>>(PREF_KEY, accessToken).then((map) => {
        const next = { ...(map ?? {}), [bookId]: lang };
        syncPrefsToServer(PREF_KEY, next, accessToken);
      });
    },
    [accessToken, bookId],
  );

  const apiDisplayLanguage =
    displayLanguage && bookOriginalLanguage && displayLanguage !== bookOriginalLanguage
      ? displayLanguage
      : undefined;

  return { displayLanguage, setDisplayLanguage, apiDisplayLanguage, loaded };
}
