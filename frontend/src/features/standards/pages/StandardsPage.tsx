import { Navigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { StandardsShell, STANDARDS_TABS, type StandardsTab } from '../components/StandardsShell';

/**
 * `/standards` — the per-user glossary Standards Library. User-tier standards are
 * per-user (not per-book), so this is a top-level route, not a book sub-screen; they
 * feed the book adopt pick-list (System→User resolution) wherever the user adopts.
 */
export function StandardsPage() {
  const { t } = useTranslation('standards');
  const { tab } = useParams<{ tab: string }>();

  if (!tab || !STANDARDS_TABS.includes(tab as StandardsTab)) {
    return <Navigate to="/standards/genres" replace />;
  }

  return (
    <div className="mx-auto max-w-[900px] px-6 py-6">
      <h1 className="font-serif text-xl font-semibold">{t('title')}</h1>
      <p className="mb-5 mt-1 text-sm text-muted-foreground">{t('subtitle')}</p>
      <StandardsShell tab={tab as StandardsTab} />
    </div>
  );
}
