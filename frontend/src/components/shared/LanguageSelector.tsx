import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { LANGUAGE_REGISTRY } from '@/lib/languages';
import { useAuth } from '@/auth';
import { persistUiLanguage } from '@/lib/uiLanguage';

// UI-locale switcher: one button per registry language flagged `uiLocale`.
const UI_LOCALE_ENTRIES = LANGUAGE_REGISTRY.filter((l) => l.uiLocale);

export function LanguageSelector({ className }: { className?: string }) {
  const { i18n } = useTranslation();
  const { accessToken } = useAuth();
  const current = i18n.language;

  return (
    <div className={cn('flex flex-wrap gap-2', className)}>
      {UI_LOCALE_ENTRIES.map((lang) => (
        <button
          key={lang.code}
          onClick={() => {
            void i18n.changeLanguage(lang.code);
            // The device copy (i18next localStorage cache) is fast but wiped by
            // a cleared browser — the account preference survives it.
            persistUiLanguage(accessToken);
          }}
          className={cn(
            'rounded-md border px-4 py-2 text-sm font-medium transition-colors',
            current === lang.code || current.startsWith(lang.code)
              ? 'border-primary bg-primary/15 text-primary'
              : 'border-border text-foreground hover:bg-secondary',
          )}
        >
          {lang.endonym}
        </button>
      ))}
    </div>
  );
}
