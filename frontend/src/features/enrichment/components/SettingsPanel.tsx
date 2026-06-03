import { useTranslation } from 'react-i18next';
import { Settings as SettingsIcon } from 'lucide-react';
import { Skeleton } from '@/components/shared';
import { useEnrichmentContext } from '../context/EnrichmentContext';
import { useBookProfile } from '../hooks/useBookProfile';
import { ProfileForm } from './ProfileForm';

/** The per-book de-bias PROFILE authoring panel (worldview / language / era / voice
 *  + per-kind dimension overrides + AI-suggest). An unset book loads the neutral
 *  default, so the form always has a profile to edit. The form is keyed by bookId
 *  so it re-seeds when switching books (no stale form state). */
export function SettingsPanel() {
  const { t } = useTranslation('enrichment');
  const { bookId } = useEnrichmentContext();
  const { profile, isLoading, isError, save, suggest, saving, suggesting } = useBookProfile(bookId);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <SettingsIcon className="h-4 w-4 text-primary" />
        <div>
          <h3 className="text-sm font-semibold">{t('settings.title')}</h3>
          <p className="text-xs text-muted-foreground">{t('settings.subtitle')}</p>
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : isError || !profile ? (
        <p className="rounded-lg border border-dashed p-6 text-center text-xs text-muted-foreground">
          {t('settings.error')}
        </p>
      ) : (
        <ProfileForm
          key={bookId}
          profile={profile}
          onSave={save}
          onSuggest={suggest}
          saving={saving}
          suggesting={suggesting}
        />
      )}
    </div>
  );
}
