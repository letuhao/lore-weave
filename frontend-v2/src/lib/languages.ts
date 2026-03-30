/**
 * Language code → native name map.
 * Used by LanguageDisplay component everywhere.
 */
export const LANGUAGE_NAMES: Record<string, string> = {
  ja: '日本語',
  en: 'English',
  vi: 'Tiếng Việt',
  'zh-TW': '繁體中文',
  'zh-CN': '简体中文',
  ko: '한국어',
  fr: 'Français',
  de: 'Deutsch',
  es: 'Español',
  pt: 'Português',
  ru: 'Русский',
  th: 'ภาษาไทย',
  ar: 'العربية',
};

export function getLanguageName(code: string): string {
  return LANGUAGE_NAMES[code] ?? code;
}
