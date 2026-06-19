import { useTranslation } from 'react-i18next';
import { RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { useSync } from '../../hooks/useSync';
import { SyncDiffTable } from './SyncDiffTable';

/** 04-sync: on-demand diff/apply of the book's adopted standards vs upstream. */
export function SyncScreen({ bookId }: { bookId: string }) {
  const { t } = useTranslation('glossaryTiering');
  const sync = useSync(bookId);

  const apply = async () => {
    try {
      const applied = await sync.apply();
      toast.success(t('sync.applied_toast', { count: applied }));
    } catch (e) {
      const msg = (e as { status?: number }).status === 403 ? t('toast.forbidden') : (e as Error).message;
      toast.error(msg || t('toast.save_failed'));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-sm font-semibold">{t('sync.title')}</h2>
          <p className="text-xs text-muted-foreground">{t('sync.subtitle')}</p>
        </div>
        <button
          onClick={() => void sync.refetch()}
          className="flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-xs hover:bg-secondary"
          title={t('sync.available')}
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
      </div>

      {sync.isLoading ? (
        <p className="p-4 text-sm text-muted-foreground">{t('sync.loading')}</p>
      ) : sync.updates.length === 0 ? (
        <p className="rounded-lg border border-dashed bg-card p-8 text-center text-sm text-muted-foreground">
          {t('sync.none')}
        </p>
      ) : (
        <>
          {sync.actionable.length > 0 && (
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                {t('sync.available')}: {sync.count}
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => sync.setAll('keep_mine')}
                  className="rounded-md border px-2.5 py-1.5 text-xs hover:bg-secondary"
                >
                  {t('sync.keep_all_mine')}
                </button>
                <button
                  onClick={() => sync.setAll('take_theirs')}
                  className="rounded-md border px-2.5 py-1.5 text-xs hover:bg-secondary"
                >
                  {t('sync.take_all_theirs')}
                </button>
              </div>
            </div>
          )}

          <SyncDiffTable updates={sync.updates} choiceFor={sync.choiceFor} setChoice={sync.setChoice} />

          {sync.actionable.length > 0 && (
            <div className="flex justify-end">
              <button
                onClick={() => void apply()}
                disabled={sync.applying}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {sync.applying ? t('sync.applying') : t('sync.apply')}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
