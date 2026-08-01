// @loreweave/i18n — translation bootstrap for `frontend-game`.
//
// Deliberately NOT a copy of `frontend/src/i18n/index.ts`. Two differences
// matter, and both are decisions rather than omissions:
//
//   1. NO side effects at import. The novel app inits i18next as a module
//      side-effect; here `initI18n()` is explicit so tests can load this module
//      without a DOM, and so bootstrap order stays visible in main.tsx.
//   2. A 4-locale CLUSTER, not 18. The game seeds en / ja / vi / zh-TW
//      (packages/i18n/README.md). A user whose novel-app language sits outside
//      that set is NOT broken: `fallbackLng: 'en'` degrades gracefully.
//
// SHARED CONTRACT — `lw_language`. The novel app persists the chosen language
// under that localStorage key, and localStorage is per-origin. Served from ONE
// origin (gateway path-routing, /app + /game), picking Vietnamese in either app
// carries into the other with no coupling between the codebases — the same
// mechanism that shares the session via `lw_auth`. Change this key and the two
// apps silently disagree about language.

import i18next, { type i18n as I18nInstance, type Resource } from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

/** The game's language cluster. Narrower than the novel app's 18 on purpose. */
export const GAME_LOCALES = ['en', 'ja', 'vi', 'zh-TW'] as const;
export type GameLocale = (typeof GAME_LOCALES)[number];

export const DEFAULT_LOCALE: GameLocale = 'en';

/** Shared with the novel-workflow `frontend/`. See the contract note above. */
export const LANGUAGE_STORAGE_KEY = 'lw_language';

/** Human labels for a language switcher, each in its own script. */
export const LOCALE_LABELS: Record<GameLocale, string> = {
  en: 'English',
  ja: '日本語',
  vi: 'Tiếng Việt',
  'zh-TW': '繁體中文',
};

/**
 * Load every `locales/<lang>/<ns>.json` through a Vite glob rather than a
 * hand-written import list. Adding a namespace file (or a whole locale) needs
 * ZERO edits here — which is the point: the alternative rots the moment
 * somebody adds `combat.json` for three languages and forgets the fourth.
 *
 * Files starting with `_` are skipped (translation reports, not resources).
 */
export function loadResources(): Resource {
  const modules = import.meta.glob('../locales/*/*.json', { eager: true }) as Record<
    string,
    { default: Record<string, unknown> }
  >;

  const resources: Record<string, Record<string, unknown>> = {};
  for (const [path, mod] of Object.entries(modules)) {
    const m = /\/locales\/([^/]+)\/([^/]+)\.json$/.exec(path);
    const lang = m?.[1];
    const ns = m?.[2];
    if (!lang || !ns || ns.startsWith('_')) continue;
    (resources[lang] ??= {})[ns] = mod.default;
  }
  return resources as Resource;
}

let initialised = false;

/**
 * Bootstrap i18next for the game client. Idempotent — React StrictMode
 * double-invokes in dev, and a second `init()` would drop loaded resources.
 */
export function initI18n(): I18nInstance {
  if (initialised) return i18next;
  initialised = true;

  void i18next
    .use(LanguageDetector)
    .use(initReactI18next)
    .init({
      resources: loadResources(),
      supportedLngs: [...GAME_LOCALES],
      // en-US → en, zh-TW stays zh-TW. Without this a browser reporting
      // `vi-VN` misses the `vi` bundle entirely and falls back to English.
      nonExplicitSupportedLngs: true,
      defaultNS: 'common',
      fallbackLng: DEFAULT_LOCALE,
      interpolation: { escapeValue: false }, // React already escapes
      detection: {
        order: ['localStorage', 'navigator'],
        caches: ['localStorage'],
        lookupLocalStorage: LANGUAGE_STORAGE_KEY,
      },
    });

  applyDocumentLang(i18next.language || DEFAULT_LOCALE);
  i18next.on('languageChanged', applyDocumentLang);
  return i18next;
}

/**
 * Keep `<html lang>` in step with the active language — it drives screen-reader
 * pronunciation and CJK font selection.
 *
 * No `dir` handling here: the novel app needs RTL because it ships `ar`; the
 * game cluster is en/ja/vi/zh-TW, all LTR. Add it the day an RTL locale joins
 * GAME_LOCALES.
 */
function applyDocumentLang(lng: string): void {
  if (typeof document === 'undefined') return;
  document.documentElement.lang = lng;
}

export { i18next };
