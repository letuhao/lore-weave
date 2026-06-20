import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Copy, Pencil, Trash2, Plus } from 'lucide-react';
import type { Genre } from '@/features/glossary/tieringTypes';
import { StandardRow } from './StandardRow';
import { StandardFormModal, type StandardFormValues } from './StandardFormModal';
import { useUserStandards } from '../hooks/useUserStandards';

/** Genres tab — merged System+User genres; clone System, create/edit/delete your own. */
export function GenresPanel() {
  const { t } = useTranslation('standards');
  const { genres, isLoading, error, cloneGenre, createGenre, patchGenre, deleteGenre } =
    useUserStandards();
  const [form, setForm] = useState<{ mode: 'create' | 'edit'; genre?: Genre } | null>(null);

  const onClone = (g: Genre) =>
    cloneGenre.mutate(g, {
      onSuccess: () => toast.success(t('toast.cloned', { name: g.name })),
      onError: () => toast.error(t('toast.cloneError', { name: g.name })),
    });

  const onDelete = (g: Genre) =>
    deleteGenre.mutate(g.genre_id, {
      onSuccess: () => toast.success(t('toast.deleted', { name: g.name })),
      onError: () => toast.error(t('toast.deleteError', { name: g.name })),
    });

  const onSubmitForm = async (vals: StandardFormValues) => {
    if (form?.mode === 'edit' && form.genre) {
      await patchGenre.mutateAsync(
        { id: form.genre.genre_id, changes: { name: vals.name, icon: vals.icon, color: vals.color } },
        { onSuccess: () => toast.success(t('toast.saved')), onError: () => toast.error(t('toast.saveError')) },
      );
    } else {
      await createGenre.mutateAsync(
        { name: vals.name, icon: vals.icon, color: vals.color, code: vals.code },
        { onSuccess: () => toast.success(t('toast.created', { name: vals.name })), onError: () => toast.error(t('toast.createError')) },
      );
    }
  };

  return (
    <div>
      <div className="mb-3 flex justify-end">
        <button onClick={() => setForm({ mode: 'create' })} className="inline-flex items-center gap-1 rounded border px-2.5 py-1.5 text-[12px] font-medium hover:bg-secondary" data-testid="new-genre">
          <Plus className="h-3.5 w-3.5" />{t('genres.new')}
        </button>
      </div>

      {isLoading ? (
        <p className="py-6 text-sm text-muted-foreground">{t('loading')}</p>
      ) : error ? (
        <p className="py-6 text-sm text-destructive">{t('error')}</p>
      ) : genres.length === 0 ? (
        <p className="py-6 text-sm text-muted-foreground">{t('empty.genres')}</p>
      ) : (
        <ul className="space-y-1.5" data-testid="standards-genres">
          {genres.map((g) => (
            <li key={g.genre_id}>
              <StandardRow icon={g.icon} name={g.name} code={g.code} tier={g.tier}>
                {g.tier === 'system' ? (
                  <button type="button" onClick={() => onClone(g)} disabled={cloneGenre.isPending} className="inline-flex items-center gap-1 rounded border px-2 py-1 text-[12px] font-medium text-muted-foreground hover:text-foreground disabled:opacity-50" data-testid={`clone-genre-${g.code}`}>
                    <Copy className="h-3 w-3" />{t('action.clone')}
                  </button>
                ) : (
                  <>
                    <button type="button" onClick={() => setForm({ mode: 'edit', genre: g })} className="rounded border p-1 text-muted-foreground hover:text-foreground" aria-label={t('action.edit')} data-testid={`edit-genre-${g.code}`}>
                      <Pencil className="h-3 w-3" />
                    </button>
                    <button type="button" onClick={() => onDelete(g)} className="rounded border p-1 text-destructive hover:bg-destructive/10" aria-label={t('action.delete')} data-testid={`delete-genre-${g.code}`}>
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </>
                )}
              </StandardRow>
            </li>
          ))}
        </ul>
      )}

      {form && (
        <StandardFormModal
          entity="genre"
          mode={form.mode}
          initial={form.genre ? { name: form.genre.name, icon: form.genre.icon, color: form.genre.color } : undefined}
          onSubmit={onSubmitForm}
          onClose={() => setForm(null)}
        />
      )}
    </div>
  );
}
