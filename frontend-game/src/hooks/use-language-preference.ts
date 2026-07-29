// Language as a SERVER-OWNED user preference, with localStorage as cache only.
//
// The bug this exists to fix, found by a live cross-app smoke: the game's first
// cut treated `lw_language` in localStorage as the source of truth. The novel
// app does not — `ThemeProvider.tsx` loads `/v1/me/preferences` on start and
// writes `prefs.ui_language` over that key. So a language picked in the game
// survived exactly until the user opened the novel app, which silently reset it
// from the server. The novel app was RIGHT (CLAUDE.md: "server is the source of
// truth · no localStorage for user data · preferences read from server on
// login, write-through on change"); the game was wrong.
//
// The same reasoning is why this is a per-user setting and not an env/global:
// two users plainly want different values.
//
// Resolution cascade, lowest precedence first:
//   browser/navigator detection  →  localStorage cache  →  SERVER preference
// The server wins, and only after it answers — never blocking first paint.

import { useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { authedJson } from '@loreweave/auth-client';
import { GAME_LOCALES, LANGUAGE_STORAGE_KEY, type GameLocale } from '@loreweave/i18n';
import { useSession } from '@/store/session-context';

const PREF_KEY = 'ui_language';

/** The novel app stores 18 locales; the game renders 4. Anything outside the
 *  cluster is ignored rather than applied, so `ko` from the writing app leaves
 *  the game on its existing language instead of blanking it. */
function inCluster(value: unknown): value is GameLocale {
  return typeof value === 'string' && (GAME_LOCALES as readonly string[]).includes(value);
}

// Pull-once guard at MODULE scope, not per-hook-instance.
//
// Two bugs made this necessary. (1) A `useRef` guard is per component instance,
// so mounting the hook in more than one place would pull the preference more
// than once. (2) It never reset: after a sign-out and a sign-in as a DIFFERENT
// user in the same page session, the guard was still set and user B silently
// inherited user A's language.
let pulledForSession = false;

export function useLanguagePreference(): { setLanguage: (code: GameLocale) => void } {
  const { i18n } = useTranslation();
  const { isAuthenticated } = useSession();

  useEffect(() => {
    // Signing out re-arms the pull for whoever logs in next.
    if (!isAuthenticated) {
      pulledForSession = false;
      return;
    }
    if (pulledForSession) return;
    pulledForSession = true;

    void (async () => {
      try {
        const res = await authedJson<{ prefs?: Record<string, unknown> }>('/v1/me/preferences');
        const serverLang = res.prefs?.[PREF_KEY];
        if (inCluster(serverLang) && serverLang !== i18n.language) {
          await i18n.changeLanguage(serverLang);
        }
      } catch {
        // Offline or the endpoint is unavailable — the cached language stands.
        // A preference read must never block getting into the game.
      }
    })();
  }, [isAuthenticated, i18n]);

  const setLanguage = useCallback(
    (code: GameLocale) => {
      void i18n.changeLanguage(code); // also writes the localStorage cache
      if (!isAuthenticated) return; // anonymous: cache only, nothing to sync
      void authedJson('/v1/me/preferences', {
        method: 'PATCH',
        body: JSON.stringify({ prefs: { [PREF_KEY]: code } }),
      }).catch(() => {
        // Fire-and-forget, matching the novel app's `syncPrefsToServer`. The
        // local change already applied; a failed sync must not undo the UI.
      });
    },
    [i18n, isAuthenticated],
  );

  return { setLanguage };
}

export { LANGUAGE_STORAGE_KEY };
