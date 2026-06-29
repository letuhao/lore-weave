import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { X } from 'lucide-react';
import type { BookGenre } from '../../tieringTypes';

type Props = {
  kindName: string;
  /** All of the book's genres — the linkable set (replace-set on save). */
  genres: BookGenre[];
  /** The book genre_ids this kind is currently linked to. */
  linkedGenreIds: string[];
  /** Bound to ont.setKindGenres(kindId, …); throws on failure (403 → forbidden). */
  onSave: (genreIds: string[]) => Promise<unknown>;
  onClose: () => void;
};

/**
 * #25 — book-tier kind↔genre link editor. Toggle which of the book's genres a kind
 * belongs to; replace-set on save. A book kind with no genre link is invisible in the
 * genre-first Manage drilldown (and can hold no attributes, which live per kind×genre),
 * so the book tier enforces a "≥1 genre" invariant: Save is disabled with an empty set.
 */
export function BookKindGenresModal({ kindName, genres, linkedGenreIds, onSave, onClose }: Props) {
  const { t } = useTranslation('glossaryTiering');
  const [selected, setSelected] = useState<Set<string>>(() => new Set(linkedGenreIds));
  const [submitting, setSubmitting] = useState(false);
  const close = () => {
    if (!submitting) onClose();
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submitting) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, submitting]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const onSubmit = async () => {
    if (selected.size === 0) return;
    setSubmitting(true);
    try {
      await onSave([...selected]);
      toast.success(t('toast.links_saved'));
      onClose();
    } catch (e) {
      const msg = (e as { status?: number }).status === 403 ? t('toast.forbidden') : (e as Error).message;
      toast.error(msg || t('toast.links_failed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={close} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="flex w-full max-w-sm flex-col rounded-xl border bg-background shadow-2xl"
          onClick={(e) => e.stopPropagation()}
          data-testid="book-kind-genres-modal"
        >
          <div className="flex items-start justify-between border-b bg-card px-5 py-4">
            <h2 className="text-sm font-semibold">{t('links.title', { name: kindName })}</h2>
            <button onClick={close} disabled={submitting} className="rounded-md p-1 hover:bg-secondary disabled:opacity-40" aria-label={t('links.cancel')}>
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="max-h-72 space-y-1.5 overflow-y-auto p-5">
            <p className="mb-2 text-xs text-muted-foreground">{t('links.hint')}</p>
            {genres.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('links.empty')}</p>
            ) : (
              genres.map((g) => (
                <label key={g.genre_id} className="flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-sm">
                  <input
                    type="checkbox"
                    checked={selected.has(g.genre_id)}
                    onChange={() => toggle(g.genre_id)}
                    data-testid={`link-genre-${g.code}`}
                  />
                  <span aria-hidden>{g.icon || '•'}</span>
                  <span>{g.name}</span>
                </label>
              ))
            )}
          </div>

          <div className="flex justify-end gap-2 border-t px-5 py-3">
            <button onClick={close} disabled={submitting} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary disabled:opacity-50">
              {t('links.cancel')}
            </button>
            <button
              onClick={onSubmit}
              disabled={submitting || selected.size === 0}
              className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              data-testid="book-links-save"
            >
              {submitting ? t('links.saving') : t('links.save')}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
