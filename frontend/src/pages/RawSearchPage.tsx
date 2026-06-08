import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { RawSearchPanel } from '@/features/raw-search/components/RawSearchPanel';

export function RawSearchPage() {
  const { bookId = '' } = useParams();
  const { t } = useTranslation('rawSearch');
  return (
    <div className="mx-auto w-full max-w-3xl p-4 lg:p-8">
      <h1 className="mb-1 text-lg font-semibold">{t('title')}</h1>
      <p className="mb-4 text-sm text-muted-foreground">{t('subtitle')}</p>
      <RawSearchPanel bookId={bookId} />
    </div>
  );
}
