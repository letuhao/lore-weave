import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { loadPrefFromServer, syncPrefsToServer } from '@/lib/syncPrefs';
import { isDisplayingTranslation } from '../lib/resolveDisplayValue';

const PREF_KEY = 'glossary_display_lang_by_book';

export function useGlossaryDisplayLanguage(
  bookId: string,
  bookOriginalLanguage?: string,
) {
  const { accessToken } = useAuth();
  const defaultLang = bookOriginalLanguage ?? '';
  const [displayLanguage, setDisplayLanguageState] = useState(defaultLang);
  const [prefMap, setPrefMap] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    // No auth, or no book (e.g. the global chat page passes '') → nothing to load;
    // skip the server round-trip and resolve to the default immediately.
    if (!accessToken || !bookId) {
      setDisplayLanguageState(defaultLang);
      setPrefMap({});
      setLoaded(true);
      return;
    }
    let cancelled = false;
    void loadPrefFromServer<Record<string, string>>(PREF_KEY, accessToken).then((map) => {
      if (cancelled) return;
      const hydrated = map ?? {};
      setPrefMap(hydrated);
      const saved = hydrated[bookId];
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
      setPrefMap((prev) => {
        const next = { ...prev, [bookId]: lang };
        syncPrefsToServer(PREF_KEY, next, accessToken);
        return next;
      });
    },
    [accessToken, bookId],
  );

  const apiDisplayLanguage = isDisplayingTranslation(displayLanguage, bookOriginalLanguage)
    ? displayLanguage
    : undefined;

  return { displayLanguage, setDisplayLanguage, apiDisplayLanguage, loaded };
}
