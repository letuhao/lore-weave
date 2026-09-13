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
    // 🔴 AN EMPTY TRANSLATION MEANS "MISSING", NOT "RENDER NOTHING".
    //
    // i18next defaults `returnEmptyString` to TRUE, so `""` in a resource is a legitimate
    // VALUE and `t()` returns it -- a `defaultValue` at the call site is never consulted.
    // Measured 2026-09-13: all 48 `composition.structureTemplates.beats.*.purpose` keys are
    // `""` in `en` and fully written in the other 17 locales, while composition-service DOES
    // seed an English purpose for every one of them. `localizedBeat()` passes exactly the
    // right `defaultValue: beat.purpose`, and it was being discarded, so `StructureTemplates
    // Panel`'s `{lb.purpose && …}` drew nothing. **English was the degraded locale** -- a
    // Vietnamese author read what each story beat is for and an English author got a blank,
    // across Save the Cat, Hero's Journey, Story Circle, Kishotenketsu and Web Novel.
    //
    // Blast radius is exactly those 48 keys, and that is CHECKED rather than assumed:
    // `emptyStringDoesNotSuppressContent.test.ts` fails if any other empty value appears in
    // any of the 18 locales, because a new one would silently start rendering its
    // `defaultValue` -- or, with no default, its raw key.
    returnEmptyString: false,
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
