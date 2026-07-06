import i18n, { type Resource } from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import { UI_LOCALES, getLanguageDir } from '@/lib/languages';

/**
 * Auto-load every `locales/<lang>/<ns>.json` via a Vite glob instead of ~124
 * hand-written imports. Any new locale directory or namespace file (e.g. the
 * gemma-generated locales from scripts/i18n_translate.py) is picked up with
 * ZERO edits here. `_FAILED.json` translation-report files are skipped.
 *
 * Partial locales are fine: i18next `fallbackLng: 'en'` fills any missing
 * namespace/key, so a half-generated language degrades gracefully to English.
 */
const modules = import.meta.glob('./locales/*/*.json', { eager: true }) as Record<
  string,
  { default: Record<string, unknown> }
>;

const resources: Record<string, Record<string, unknown>> = {};
for (const [path, mod] of Object.entries(modules)) {
  const m = path.match(/\.\/locales\/([^/]+)\/([^/]+)\.json$/);
  if (!m) continue;
  const [, lang, ns] = m;
  if (ns.startsWith('_')) continue; // skip _FAILED.json (translation reports)
  (resources[lang] ??= {})[ns] = mod.default;
}

/** Apply writing direction (RTL for ar/he) + lang attr on the document root. */
function applyDocumentDir(lng: string): void {
  if (typeof document === 'undefined') return;
  document.documentElement.dir = getLanguageDir(lng);
  document.documentElement.lang = lng;
}

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    // The glob builds a nested lang→ns→tree map; i18next's Resource type wants
    // ResourceKey leaves (string | object), which `unknown` values don't satisfy.
    resources: resources as Resource,
    supportedLngs: [...UI_LOCALES],
    // en-US → en, fr-FR → fr, etc. (region variants fall to their base UI locale).
    nonExplicitSupportedLngs: true,
    defaultNS: 'common',
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'lw_language',
    },
  });

// RTL/bidi: set direction now + on every language switch.
i18n.on('languageChanged', applyDocumentDir);
applyDocumentDir(i18n.language || 'en');

export default i18n;
