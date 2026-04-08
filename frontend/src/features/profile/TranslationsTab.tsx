import { useTranslation } from 'react-i18next';
import type { TranslatorStats } from './api';

type Props = { translator: TranslatorStats | null };

export function TranslationsTab({ translator }: Props) {
  const { t } = useTranslation('profile');

  if (!translator || translator.total_chapters_done === 0) {
    return (
      <div className="py-8 text-center text-sm text-[var(--muted-fg)]">
        {t('noTranslations')}
      </div>
    );
  }

  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden bg-[var(--card)]">
      <div className="grid grid-cols-3 gap-px bg-[var(--border)]">
        <div className="bg-[var(--card)] p-4 text-center">
          <div className="text-2xl font-bold font-mono">{translator.total_chapters_done}</div>
          <div className="text-[10px] text-[var(--muted-fg)] mt-1">{t('stats.chaptersTranslated')}</div>
        </div>
        <div className="bg-[var(--card)] p-4 text-center">
          <div className="text-2xl font-bold font-mono">{translator.total_translations}</div>
          <div className="text-[10px] text-[var(--muted-fg)] mt-1">{t('stats.totalTranslations')}</div>
        </div>
        <div className="bg-[var(--card)] p-4 text-center">
          <div className="text-2xl font-bold font-mono">{translator.languages.length}</div>
          <div className="text-[10px] text-[var(--muted-fg)] mt-1">{t('stats.languages')}</div>
        </div>
      </div>

      {/* Recent activity */}
      <div className="p-4 border-t border-[var(--border)]">
        <h4 className="text-xs font-semibold mb-3">{t('recentActivity')}</h4>
        <div className="flex gap-6 text-sm">
          <div>
            <span className="text-[var(--muted-fg)]">{t('last7d')}:</span>{' '}
            <strong>{translator.translations_7d}</strong> {t('chapters')}
          </div>
          <div>
            <span className="text-[var(--muted-fg)]">{t('last30d')}:</span>{' '}
            <strong>{translator.translations_30d}</strong> {t('chapters')}
          </div>
        </div>
      </div>

      {/* Languages */}
      {translator.languages.length > 0 && (
        <div className="p-4 border-t border-[var(--border)]">
          <h4 className="text-xs font-semibold mb-2">{t('translationLanguages')}</h4>
          <div className="flex gap-2 flex-wrap">
            {translator.languages.map((lang) => (
              <span
                key={lang}
                className="px-2 py-0.5 rounded text-xs font-mono bg-[var(--secondary)] text-[var(--muted-fg)]"
              >
                {lang}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
