import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useEntityForm } from '../../hooks/useEntityForm';
import { GenrePillSelector } from './GenrePillSelector';
import { AttributeField } from './AttributeField';

/** 03-entity-form: create an entity with attributes merged across its genres. The genre
 *  set defaults to the book's active genres and is editable per entity (D2); a code
 *  shared by 2+ genres shows both fields, namespaced. */
export function TieredEntityForm({
  bookId,
  kindId,
  onCreated,
  onCancel,
}: {
  bookId: string;
  kindId: string;
  onCreated: (entityId: string) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation('glossaryTiering');
  const form = useEntityForm(bookId, kindId);

  const create = async () => {
    try {
      const id = await form.submit();
      toast.success(t('toast.saved'));
      onCreated(id);
    } catch (e) {
      const msg = (e as { status?: number }).status === 403 ? t('toast.forbidden') : (e as Error).message;
      toast.error(msg || t('toast.save_failed'));
    }
  };

  // Codes that appear under more than one genre section — drives the conflict note.
  const conflictCode = form.sections
    .flatMap((s) => s.fields)
    .find((f) => f.labelCode.includes('·'))
    ?.attr.code;

  if (form.isLoading) return <p className="p-4 text-sm text-muted-foreground">{t('manage.loading')}</p>;

  return (
    <div className="space-y-4">
      <div className="rounded-lg border bg-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-semibold">{t('entity.title_new', { kind: form.kindName })}</h3>
          <div className="flex flex-col items-end gap-1">
            <span className="text-[11px] text-muted-foreground">{t('entity.genres_label')}</span>
            <GenrePillSelector
              genres={form.genres}
              selectedIds={form.selectedGenreIds}
              onChange={form.setSelectedGenreIds}
            />
          </div>
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">{t('entity.genres_hint')}</p>
      </div>

      {form.sections.map((section) => (
        <section key={section.genre.genre_id} className="rounded-lg border bg-card p-4">
          <h4 className="mb-3 text-xs font-semibold" style={{ color: section.genre.color }}>
            {section.genre.icon ? `${section.genre.icon} ` : ''}
            {section.genre.name}
          </h4>
          <div className="grid gap-3 sm:grid-cols-2">
            {section.fields.map((f) => (
              <AttributeField
                key={f.attr.attr_id}
                attr={f.attr}
                labelCode={f.labelCode}
                value={form.values[f.attr.attr_id] ?? ''}
                onChange={(v) => form.setValue(f.attr.attr_id, v)}
              />
            ))}
          </div>
        </section>
      ))}

      {conflictCode && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-[12px] text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          <div className="font-semibold">{t('entity.conflict_title', { code: conflictCode })}</div>
          <p>{t('entity.conflict_body')}</p>
        </div>
      )}

      <div className="flex justify-end gap-2">
        <button onClick={onCancel} className="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-secondary">
          {t('entity.cancel')}
        </button>
        <button
          onClick={() => void create()}
          disabled={form.submitting}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {form.submitting ? t('entity.creating') : t('entity.create')}
        </button>
      </div>
    </div>
  );
}
