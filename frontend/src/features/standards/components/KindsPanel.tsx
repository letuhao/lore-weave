import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Copy, Link2, Pencil, Trash2, Plus } from 'lucide-react';
import { StandardRow } from './StandardRow';
import { KindGenresModal } from './KindGenresModal';
import { StandardFormModal, type StandardFormValues } from './StandardFormModal';
import { useUserStandards, type KindRow } from '../hooks/useUserStandards';

/** Kinds tab — merged System+User kinds; clone System, create/edit/delete your own,
 *  and edit a User kind's genre links. */
export function KindsPanel() {
  const { t } = useTranslation('standards');
  const { genres, kinds, isLoading, error, cloneKind, createKind, patchKind, deleteKind } =
    useUserStandards();
  const userGenres = genres.filter((g) => g.tier === 'user');
  const [linkKind, setLinkKind] = useState<KindRow | null>(null);
  const [form, setForm] = useState<{ mode: 'create' | 'edit'; kind?: KindRow } | null>(null);

  const onClone = (k: KindRow) =>
    cloneKind.mutate(k, {
      onSuccess: () => toast.success(t('toast.cloned', { name: k.name })),
      onError: () => toast.error(t('toast.cloneError', { name: k.name })),
    });

  const onDelete = (k: KindRow) =>
    deleteKind.mutate(k.id, {
      onSuccess: () => toast.success(t('toast.deleted', { name: k.name })),
      onError: () => toast.error(t('toast.deleteError', { name: k.name })),
    });

  const onSubmitForm = async (vals: StandardFormValues) => {
    if (form?.mode === 'edit' && form.kind) {
      await patchKind.mutateAsync(
        { id: form.kind.id, changes: { name: vals.name, icon: vals.icon, color: vals.color, description: vals.description } },
        { onSuccess: () => toast.success(t('toast.saved')), onError: () => toast.error(t('toast.saveError')) },
      );
    } else {
      await createKind.mutateAsync(
        { name: vals.name, icon: vals.icon, color: vals.color, code: vals.code, description: vals.description },
        { onSuccess: () => toast.success(t('toast.created', { name: vals.name })), onError: () => toast.error(t('toast.createError')) },
      );
    }
  };

  return (
    <div>
      <div className="mb-3 flex justify-end">
        <button onClick={() => setForm({ mode: 'create' })} className="inline-flex items-center gap-1 rounded border px-2.5 py-1.5 text-[12px] font-medium hover:bg-secondary" data-testid="new-kind">
          <Plus className="h-3.5 w-3.5" />{t('kinds.new')}
        </button>
      </div>

      {isLoading ? (
        <p className="py-6 text-sm text-muted-foreground">{t('loading')}</p>
      ) : error ? (
        <p className="py-6 text-sm text-destructive">{t('error')}</p>
      ) : kinds.length === 0 ? (
        <p className="py-6 text-sm text-muted-foreground">{t('empty.kinds')}</p>
      ) : (
        <ul className="space-y-1.5" data-testid="standards-kinds">
          {kinds.map((k) => (
            <li key={`${k.tier}:${k.id}`}>
              <StandardRow icon={k.icon} name={k.name} code={k.code} tier={k.tier}>
                {k.tier === 'system' ? (
                  <button type="button" onClick={() => onClone(k)} disabled={cloneKind.isPending} className="inline-flex items-center gap-1 rounded border px-2 py-1 text-[12px] font-medium text-muted-foreground hover:text-foreground disabled:opacity-50" data-testid={`clone-kind-${k.code}`}>
                    <Copy className="h-3 w-3" />{t('action.clone')}
                  </button>
                ) : (
                  <>
                    <button type="button" onClick={() => setLinkKind(k)} className="inline-flex items-center gap-1 rounded border px-2 py-1 text-[12px] font-medium text-muted-foreground hover:text-foreground" data-testid={`links-kind-${k.code}`}>
                      <Link2 className="h-3 w-3" />{t('links.edit')}
                    </button>
                    <button type="button" onClick={() => setForm({ mode: 'edit', kind: k })} className="rounded border p-1 text-muted-foreground hover:text-foreground" aria-label={t('action.edit')} data-testid={`edit-kind-${k.code}`}>
                      <Pencil className="h-3 w-3" />
                    </button>
                    <button type="button" onClick={() => onDelete(k)} className="rounded border p-1 text-destructive hover:bg-destructive/10" aria-label={t('action.delete')} data-testid={`delete-kind-${k.code}`}>
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </>
                )}
              </StandardRow>
            </li>
          ))}
        </ul>
      )}

      {linkKind && (
        <KindGenresModal userKindId={linkKind.id} kindName={linkKind.name} userGenres={userGenres} onClose={() => setLinkKind(null)} />
      )}
      {form && (
        <StandardFormModal
          entity="kind"
          mode={form.mode}
          initial={form.kind ? { name: form.kind.name, icon: form.kind.icon, color: form.kind.color, description: form.kind.description ?? '' } : undefined}
          onSubmit={onSubmitForm}
          onClose={() => setForm(null)}
        />
      )}
    </div>
  );
}
