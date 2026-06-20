import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { X, RotateCcw, Trash2 } from 'lucide-react';
import { useStandardsTrash } from '../hooks/useStandardsTrash';

type TrashItem = { id: string; icon: string; name: string; code: string };

/** Recycle bin for soft-deleted user genres & kinds — restore or permanently purge. */
export function TrashDrawer({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation('standards');
  const { genres, kinds, isLoading, restoreGenre, purgeGenre, restoreKind, purgeKind } =
    useStandardsTrash(true);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const genreItems: TrashItem[] = genres.map((g) => ({ id: g.genre_id, icon: g.icon, name: g.name, code: g.code }));
  const kindItems: TrashItem[] = kinds.map((k) => ({ id: k.user_kind_id, icon: k.icon, name: k.name, code: k.code }));

  const section = (
    titleKey: string,
    items: TrashItem[],
    onRestore: (id: string) => void,
    onPurge: (id: string) => void,
    testid: string,
  ) => (
    <section>
      <h3 className="mb-1.5 text-xs font-semibold text-muted-foreground">{t(titleKey)}</h3>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('trash.empty_section')}</p>
      ) : (
        <ul className="space-y-1" data-testid={testid}>
          {items.map((it) => (
            <li key={it.id} className="flex items-center gap-2 rounded-md border px-3 py-1.5">
              <span aria-hidden>{it.icon || '•'}</span>
              <span className="text-[13px] font-medium">{it.name}</span>
              <code className="text-[11px] text-muted-foreground">{it.code}</code>
              <div className="ml-auto flex gap-1">
                <button onClick={() => onRestore(it.id)} className="inline-flex items-center gap-1 rounded border px-2 py-1 text-[11px] font-medium hover:bg-secondary" data-testid={`restore-${it.code}`}>
                  <RotateCcw className="h-3 w-3" />{t('trash.restore')}
                </button>
                <button onClick={() => onPurge(it.id)} className="inline-flex items-center gap-1 rounded border px-2 py-1 text-[11px] font-medium text-destructive hover:bg-destructive/10" data-testid={`purge-${it.code}`}>
                  <Trash2 className="h-3 w-3" />{t('trash.purge')}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />
      <div className="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col border-l bg-background shadow-2xl" data-testid="trash-drawer">
        <div className="flex items-start justify-between border-b bg-card px-5 py-4">
          <h2 className="text-sm font-semibold">{t('trash.title')}</h2>
          <button onClick={onClose} className="rounded-md p-1 hover:bg-secondary" aria-label={t('trash.close')}>
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {isLoading ? (
            <p className="text-sm text-muted-foreground">{t('loading')}</p>
          ) : (
            <>
              {section('trash.genres', genreItems,
                (id) => restoreGenre.mutate(id, { onSuccess: () => toast.success(t('trash.restored')), onError: () => toast.error(t('trash.restoreError')) }),
                (id) => purgeGenre.mutate(id, { onSuccess: () => toast.success(t('trash.purged')), onError: () => toast.error(t('trash.purgeError')) }),
                'trash-genres')}
              {section('trash.kinds', kindItems,
                (id) => restoreKind.mutate(id, { onSuccess: () => toast.success(t('trash.restored')), onError: () => toast.error(t('trash.restoreError')) }),
                (id) => purgeKind.mutate(id, { onSuccess: () => toast.success(t('trash.purged')), onError: () => toast.error(t('trash.purgeError')) }),
                'trash-kinds')}
            </>
          )}
        </div>
      </div>
    </>
  );
}
