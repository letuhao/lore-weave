// F2 (DBT-14 / WS-1.4 tail) — the timezone-confirm controller. The distiller buckets each day by the
// user's LOCAL day (DBT-11), reading auth's prefs.timezone (default UTC until set). This lets the user
// CONFIRM their zone so a late-night entry isn't mis-bucketed. Server is SoT (/v1/me/preferences); the
// browser zone is only the SUGGESTED default. CLAUDE.md MVC: logic here, the banner only renders.
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { loadPrefFromServer, savePrefToServer } from '@/lib/syncPrefs';

const TZ_PREF_KEY = 'timezone';

/** The IANA zone the browser reports (the suggested default); 'UTC' if unavailable. */
export function detectBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

export function useTimezone() {
  const { accessToken } = useAuth();
  const detected = detectBrowserTimezone();
  const [saved, setSaved] = useState<string | null>(null); // the server-confirmed zone, if any
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const v = await loadPrefFromServer<string>(TZ_PREF_KEY, accessToken);
      if (!cancelled) {
        setSaved(v ?? null);
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  const confirm = useCallback(
    async (tz: string) => {
      const zone = (tz || '').trim() || detected;
      setSaving(true);
      try {
        const ok = await savePrefToServer(TZ_PREF_KEY, zone, accessToken);
        if (ok) setSaved(zone); // optimistic-after-durable-write (server is SoT)
        return ok;
      } finally {
        setSaving(false);
      }
    },
    [accessToken, detected],
  );

  // Show the confirm affordance only until the user has set a zone (no clutter once confirmed).
  const needsConfirm = !loading && saved == null;
  return { detected, saved, needsConfirm, loading, saving, confirm };
}
