// Language switcher.
//
// The choice is a SERVER-owned user preference (`useLanguagePreference`), not
// just a localStorage write. Caching it locally alone is not enough: the novel
// app rehydrates `lw_language` from `/v1/me/preferences` on start, so a
// local-only choice here gets silently reset the next time the user opens it —
// and would never follow them to a second device.

import { useTranslation } from 'react-i18next';
import { GAME_LOCALES, LOCALE_LABELS, type GameLocale } from '@loreweave/i18n';
import { useLanguagePreference } from '@/hooks/use-language-preference';
import type { JSX } from 'react';

export function LanguageSwitcher({ className = '' }: { className?: string }): JSX.Element {
  const { i18n } = useTranslation();
  const { setLanguage } = useLanguagePreference();

  // `i18n.language` can be a region variant (`vi-VN`) thanks to
  // nonExplicitSupportedLngs; match on the base so the right option stays
  // selected instead of silently falling back to the first entry.
  const current =
    GAME_LOCALES.find((l) => l === i18n.language) ??
    GAME_LOCALES.find((l) => i18n.language?.startsWith(`${l}-`)) ??
    GAME_LOCALES.find((l) => l.split('-')[0] === i18n.language?.split('-')[0]);

  return (
    <select
      aria-label="Language"
      value={current ?? ''}
      onChange={(e) => setLanguage(e.target.value as GameLocale)}
      className={`bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-300 ${className}`}
    >
      {GAME_LOCALES.map((l) => (
        <option key={l} value={l}>
          {LOCALE_LABELS[l]}
        </option>
      ))}
    </select>
  );
}
