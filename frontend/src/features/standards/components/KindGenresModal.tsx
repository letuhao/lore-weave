import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { X } from 'lucide-react';
import type { Genre } from '@/features/glossary/tieringTypes';
import { useKindGenres } from '../hooks/useKindGenres';

type Props = {
  userKindId: string;
  kindName: string;
  userGenres: Genre[]; // the caller's user-tier genres (the only linkable set)
  onClose: () => void;
};

/** Toggle which of the caller's user genres a user kind links to; replace-set on save. */
export function KindGenresModal({ userKindId, kindName, userGenres, onClose }: Props) {
  const { t } = useTranslation('standards');
  const { linkedGenreIds, isLoading, save } = useKindGenres(userKindId);
  const [selected, setSelected] = useState<Set<string> | null>(null);
  const submitting = save.isPending;
  const close = () => { if (!submitting) onClose(); };

  // Seed the local selection from the server once links load.
  useEffect(() => {
    if (!isLoading && selected === null) setSelected(new Set(linkedGenreIds));
  }, [isLoading, linkedGenreIds, selected]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !submitting) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, submitting]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev ?? []);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const onSave = () => {
    save.mutate([...(selected ?? [])], {
      onSuccess: () => { toast.success(t('toast.linksSaved')); onClose(); },
      onError: () => toast.error(t('toast.linksError')),
    });
  };

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={close} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="flex w-full max-w-sm flex-col rounded-xl border bg-background shadow-2xl" onClick={(e) => e.stopPropagation()} data-testid="kind-genres-modal">
          <div className="flex items-start justify-between border-b bg-card px-5 py-4">
            <h2 className="text-sm font-semibold">{t('links.title', { name: kindName })}</h2>
            <button onClick={close} disabled={submitting} className="rounded-md p-1 hover:bg-secondary disabled:opacity-40" aria-label={t('links.cancel')}>
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="max-h-72 space-y-1.5 overflow-y-auto p-5">
            {isLoading || selected === null ? (
              <p className="text-sm text-muted-foreground">{t('loading')}</p>
            ) : userGenres.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('links.empty')}</p>
            ) : (
              userGenres.map((g) => (
                <label key={g.genre_id} className="flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-sm">
                  <input type="checkbox" checked={selected.has(g.genre_id)} onChange={() => toggle(g.genre_id)} data-testid={`link-genre-${g.code}`} />
                  <span aria-hidden>{g.icon || '•'}</span>
                  <span>{g.name}</span>
                </label>
              ))
            )}
          </div>

          <div className="flex justify-end gap-2 border-t px-5 py-3">
            <button onClick={close} disabled={submitting} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary disabled:opacity-50">{t('links.cancel')}</button>
            <button onClick={onSave} disabled={submitting || selected === null} className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50" data-testid="links-save">
              {submitting ? t('links.saving') : t('links.save')}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
