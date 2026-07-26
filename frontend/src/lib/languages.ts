/**
 * Canonical Language Registry (SoT) — one list powering:
 *   - the UI-locale switcher   (LanguageSelector → {@link UI_LOCALES})
 *   - the translation-target picker (LanguagePicker → {@link TRANSLATION_TARGETS})
 *   - RTL direction            ({@link getLanguageDir})
 *   - i18n resource loading    (frontend/src/i18n/index.ts loads UI_LOCALES)
 *
 * Replaces the two drifted hardcoded lists (LanguageSelector's `LANGUAGES` and
 * the old `LANGUAGE_NAMES` map). Backend mirrors this in Python; keep the two in
 * parity (see loreweave language registry + its parity test).
 *
 * Axes are independent flags, not the same set:
 *   - `uiLocale`         — the app chrome is translated into this language (needs locale JSON).
 *   - `translationTarget`— novels can be translated INTO this language (LLM handles any; this
 *                          just surfaces it in the target picker).
 *
 * `dir: 'rtl'` drives the app-root `dir` attribute + bidi layout (ar/he).
 */
export type LanguageDir = 'ltr' | 'rtl';

export interface LanguageEntry {
  /** BCP-47 code (the i18n resource key + target_language value). */
  code: string;
  /** English display name. */
  englishName: string;
  /** Native display name (endonym) — what the picker shows. */
  endonym: string;
  /** ISO 15924-ish script family (informational; drives no logic today). */
  script: string;
  dir: LanguageDir;
  uiLocale: boolean;
  translationTarget: boolean;
}

/**
 * The registry. Order here is the display order in both pickers.
 * Core CJK+V first (the platform's rooted audience), then popular LTR, then
 * RTL / complex-script.
 */
export const LANGUAGE_REGISTRY: readonly LanguageEntry[] = [
  // ── Core (CJK + Vietnamese + English) ──
  { code: 'en',    englishName: 'English',              endonym: 'English',            script: 'Latin',      dir: 'ltr', uiLocale: true, translationTarget: true },
  { code: 'vi',    englishName: 'Vietnamese',           endonym: 'Tiếng Việt',         script: 'Latin',      dir: 'ltr', uiLocale: true, translationTarget: true },
  { code: 'ja',    englishName: 'Japanese',             endonym: '日本語',              script: 'Japanese',   dir: 'ltr', uiLocale: true, translationTarget: true },
  { code: 'ko',    englishName: 'Korean',               endonym: '한국어',              script: 'Hangul',     dir: 'ltr', uiLocale: true, translationTarget: true },
  { code: 'zh-CN', englishName: 'Chinese (Simplified)', endonym: '简体中文',            script: 'Hans',       dir: 'ltr', uiLocale: true, translationTarget: true },
  { code: 'zh-TW', englishName: 'Chinese (Traditional)',endonym: '繁體中文',            script: 'Hant',       dir: 'ltr', uiLocale: true, translationTarget: true },
  // ── Popular LTR ──
  { code: 'es',    englishName: 'Spanish',              endonym: 'Español',            script: 'Latin',      dir: 'ltr', uiLocale: true, translationTarget: true },
  { code: 'pt-BR', englishName: 'Portuguese (Brazil)',  endonym: 'Português (Brasil)', script: 'Latin',      dir: 'ltr', uiLocale: true, translationTarget: true },
  { code: 'fr',    englishName: 'French',               endonym: 'Français',           script: 'Latin',      dir: 'ltr', uiLocale: true, translationTarget: true },
  { code: 'de',    englishName: 'German',               endonym: 'Deutsch',            script: 'Latin',      dir: 'ltr', uiLocale: true, translationTarget: true },
  { code: 'ru',    englishName: 'Russian',              endonym: 'Русский',            script: 'Cyrillic',   dir: 'ltr', uiLocale: true, translationTarget: true },
  { code: 'id',    englishName: 'Indonesian',           endonym: 'Bahasa Indonesia',   script: 'Latin',      dir: 'ltr', uiLocale: true, translationTarget: true },
  { code: 'ms',    englishName: 'Malay',                endonym: 'Bahasa Melayu',      script: 'Latin',      dir: 'ltr', uiLocale: true, translationTarget: true },
  { code: 'tr',    englishName: 'Turkish',              endonym: 'Türkçe',             script: 'Latin',      dir: 'ltr', uiLocale: true, translationTarget: true },
  // ── RTL / complex-script ──
  { code: 'ar',    englishName: 'Arabic',               endonym: 'العربية',            script: 'Arabic',     dir: 'rtl', uiLocale: true, translationTarget: true },
  { code: 'hi',    englishName: 'Hindi',                endonym: 'हिन्दी',              script: 'Devanagari', dir: 'ltr', uiLocale: true, translationTarget: true },
  { code: 'bn',    englishName: 'Bengali',              endonym: 'বাংলা',              script: 'Bengali',    dir: 'ltr', uiLocale: true, translationTarget: true },
  { code: 'th',    englishName: 'Thai',                 endonym: 'ภาษาไทย',            script: 'Thai',       dir: 'ltr', uiLocale: true, translationTarget: true },
] as const;

/** Registry indexed by code. */
export const LANGUAGE_BY_CODE: Readonly<Record<string, LanguageEntry>> = Object.fromEntries(
  LANGUAGE_REGISTRY.map((l) => [l.code, l]),
);

/** UI-locale codes, in registry order (drives the i18n loader + the locale switcher). */
export const UI_LOCALES: readonly string[] = LANGUAGE_REGISTRY.filter((l) => l.uiLocale).map((l) => l.code);

/** Translation-target entries, in registry order (drives the target picker). */
export const TRANSLATION_TARGETS: readonly LanguageEntry[] = LANGUAGE_REGISTRY.filter(
  (l) => l.translationTarget,
);

/**
 * Back-compat: code → endonym map. Preserved because LanguagePicker /
 * LanguageDisplay import it. Derived from the registry so it can't drift.
 */
export const LANGUAGE_NAMES: Record<string, string> = Object.fromEntries(
  LANGUAGE_REGISTRY.map((l) => [l.code, l.endonym]),
);

export function getLanguageName(code: string): string {
  return LANGUAGE_BY_CODE[code]?.endonym ?? code;
}

/**
 * Writing direction for a language code. Falls back to the base subtag
 * (`ar-EG` → `ar`) then to `ltr` for unknown codes.
 */
export function getLanguageDir(code: string): LanguageDir {
  if (LANGUAGE_BY_CODE[code]) return LANGUAGE_BY_CODE[code].dir;
  const base = code.split('-')[0];
  return LANGUAGE_BY_CODE[base]?.dir ?? 'ltr';
}
