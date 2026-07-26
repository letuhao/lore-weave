import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FormDialog } from '@/components/shared';
import { useBookOntology } from '../../hooks/useBookOntology';
import { TieredEntityForm } from './TieredEntityForm';

/** G6f create flow. Post-G4 an entity's kind is a `book_kind_id` (the FK targets
 *  book_kinds), so creation must pick a book kind — not a system kind. Step 1 picks a
 *  book kind; step 2 is the merged tiered entity form. If the book has no ontology yet,
 *  it points the user at Adopt. */
export function CreateEntityModal({
  bookId,
  onClose,
  onCreated,
}: {
  bookId: string;
  onClose: () => void;
  onCreated: (entityId: string) => void;
}) {
  const { t } = useTranslation('glossaryTiering');
  const ont = useBookOntology(bookId);
  const [kindId, setKindId] = useState<string | null>(null);
  // Block dismissal (Esc / backdrop / ✕) while a create is in flight, so the entity
  // isn't created server-side with the modal torn down before it can refresh the list.
  // Radix Dialog.Root (inside FormDialog) handles Escape/outside-click → onOpenChange(false);
  // the `!busy` guard (block dismissal mid-submit) moves into that callback below.
  const [busy, setBusy] = useState(false);

  const kinds = ont.ontology.kinds;

  return (
    <FormDialog
      open
      onOpenChange={(next) => { if (!next && !busy) onClose(); }}
      title={t('create.title')}
      description={t('create.subtitle')}
      size="2xl"
    >
      {ont.isLoading ? (
        <p className="text-sm text-muted-foreground">{t('manage.loading')}</p>
      ) : !ont.isAdopted ? (
        <p className="rounded-lg border border-dashed bg-card p-6 text-center text-sm text-muted-foreground">
          {t('create.not_adopted')}
        </p>
      ) : !kindId ? (
        <div className="space-y-2">
          <span className="text-xs font-medium text-muted-foreground">{t('create.pick_kind')}</span>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {kinds.map((k) => (
              <button
                key={k.book_kind_id}
                onClick={() => setKindId(k.book_kind_id)}
                data-testid={`create-pick-kind-${k.code}`}
                className="flex items-center gap-2 rounded-md border px-3 py-2 text-left text-sm hover:bg-secondary"
              >
                {k.icon && <span>{k.icon}</span>}
                <span className="truncate">{k.name}</span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <TieredEntityForm
          bookId={bookId}
          kindId={kindId}
          onCreated={onCreated}
          onCancel={() => setKindId(null)}
          onBusyChange={setBusy}
        />
      )}
    </FormDialog>
  );
}
