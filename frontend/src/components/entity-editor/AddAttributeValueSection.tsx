import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useBookOntology } from '@/features/glossary/hooks/useBookOntology';
import type { GlossaryEntity } from '@/features/glossary/types';

// S-06 — the "add-later" GUI the audit named ("an LLM can fill it, you can't"): if the ontology
// gained an attribute after this entity was created, the entity has no value row for it and the
// editor could not add one. This offers the kind's attr-defs the entity is MISSING a value for,
// and POSTs a new value row. The set matches exactly what the BE add route accepts (the attr-def's
// kind == the entity's kind, not deprecated — the ontology read already excludes deprecated), so
// there is no offer-then-422 dead-end. Renders nothing when the entity already has every value.
export function AddAttributeValueSection({
  bookId,
  entity,
  onAdd,
  onAdded,
}: {
  bookId: string;
  entity: GlossaryEntity;
  onAdd: (attributeDefId: string, value: string) => Promise<void>;
  onAdded: () => void;
}) {
  const { t } = useTranslation('entityEditor');
  const ont = useBookOntology(bookId);
  const { attributes } = ont.ontology;
  const [selectedDefId, setSelectedDefId] = useState('');
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);

  const present = new Set(entity.attribute_values.map((v) => v.attr_def_id));
  const missing = attributes
    .filter((a) => a.kind_id === entity.kind.kind_id && !present.has(a.attr_id))
    .sort((a, b) => a.sort_order - b.sort_order);

  if (missing.length === 0) return null;

  const submit = async () => {
    if (!selectedDefId || busy) return;
    setBusy(true);
    try {
      await onAdd(selectedDefId, value.trim());
      toast.success(t('modal.add_attr_success', { defaultValue: 'Attribute added' }));
      setSelectedDefId('');
      setValue('');
      onAdded();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="add-attr-section" className="rounded-lg border border-dashed p-3">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {t('modal.add_attr_heading', { defaultValue: 'Add a value for another attribute' })}
      </p>
      <div className="flex items-center gap-2">
        <select
          data-testid="add-attr-select"
          value={selectedDefId}
          onChange={(e) => setSelectedDefId(e.target.value)}
          aria-label={t('modal.add_attr_pick', { defaultValue: 'Pick an attribute' })}
          className="rounded-md border bg-background px-2 py-1 text-xs"
        >
          <option value="">{t('modal.add_attr_pick', { defaultValue: 'Pick an attribute…' })}</option>
          {missing.map((a) => (
            <option key={a.attr_id} value={a.attr_id}>{a.name}</option>
          ))}
        </select>
        <input
          data-testid="add-attr-value"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={t('modal.add_attr_value_placeholder', { defaultValue: 'Value' })}
          className="min-w-0 flex-1 rounded-md border bg-background px-2 py-1 text-xs"
        />
        <button
          type="button"
          data-testid="add-attr-submit"
          disabled={!selectedDefId || busy}
          onClick={submit}
          className="rounded-md border border-primary/40 px-2 py-1 text-xs text-primary transition-colors hover:bg-primary/10 disabled:opacity-50"
        >
          {t('modal.add_attr_button', { defaultValue: 'Add' })}
        </button>
      </div>
    </div>
  );
}
