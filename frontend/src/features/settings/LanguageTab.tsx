import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { syncPrefsToServer } from '@/lib/syncPrefs';
import { LANGUAGE_REGISTRY } from '@/lib/languages';

/**
 * The GUI-language picker lists EVERY registry UI locale, driven by the single
 * LANGUAGE_REGISTRY (same source as the i18n loader and LanguageSelector).
 * Was a stale hardcoded 4-language list missing ru/es/fr/de/… — a user whose
 * device lost its localStorage could not even re-select their language here
 * ("полностью пропала русская локализация", 2026-10-25).
 */
const GUI_LANGUAGES = LANGUAGE_REGISTRY.filter((l) => l.uiLocale).map((l) => ({
  code: l.code,
  native: l.endonym,
}));

export function LanguageTab() {
  const { t, i18n } = useTranslation('settings');
  const { accessToken } = useAuth();
  const current = i18n.language;

  function handleChange(code: string) {
    i18n.changeLanguage(code);
    localStorage.setItem('lw_language', code);
    syncPrefsToServer('ui_language', code, accessToken);
    toast.success(t('language.toast.changed_to', { lang: GUI_LANGUAGES.find((l) => l.code === code)?.native ?? code }));
  }

  return (
    <div>
      <div className="py-5">
        <h2 className="text-sm font-semibold">{t('language.gui_language')}</h2>
        <p className="mb-4 text-xs text-muted-foreground">
          {t('language.gui_language_desc')}
        </p>
        <div className="flex flex-wrap gap-2">
          {GUI_LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              onClick={() => handleChange(lang.code)}
              className={cn(
                'rounded-md border px-4 py-2 text-[13px] font-medium transition-colors',
                current === lang.code || current.startsWith(lang.code + '-')
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'hover:bg-secondary',
              )}
            >
              {lang.native}
            </button>
          ))}
        </div>
        <p className="mt-3 text-[11px] text-muted-foreground">
          {t('language.currently')} <strong>{GUI_LANGUAGES.find((l) => l.code === current || current.startsWith(l.code + '-'))?.native ?? current}</strong>
        </p>
      </div>
    </div>
  );
}
