import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
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
  const [busy, setBusy] = useState(false);
  const close = () => { if (!busy) onClose(); };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, busy]);

  const kinds = ont.ontology.kinds;

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={close} />
      <div className="fixed inset-0 z-50 flex items-start justify-center overflow-auto p-4">
        <div
          className="my-8 flex w-full max-w-2xl flex-col rounded-xl border bg-background shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-start justify-between border-b bg-card px-5 py-4">
            <div>
              <h2 className="text-sm font-semibold">{t('create.title')}</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">{t('create.subtitle')}</p>
            </div>
            <button onClick={close} disabled={busy} className="rounded-md p-1 hover:bg-secondary disabled:opacity-40" aria-label={t('entity.cancel')}>
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="p-5">
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
          </div>
        </div>
      </div>
    </>
  );
}
