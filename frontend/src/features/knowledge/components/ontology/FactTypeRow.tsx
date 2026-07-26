import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { OntologyChip } from './OntologyChip';
import type { FactType, FactTypePatch } from '../../types/ontology';

// One fact-type row: display + inline edit (label/description) + delete.

interface Props {
  factType: FactType;
  disabled?: boolean;
  onPatch: (patch: FactTypePatch) => void;
  onDelete: () => void;
}

export function FactTypeRow({ factType, disabled, onPatch, onDelete }: Props) {
  const { t } = useTranslation('kgOntology');
  const [editing, setEditing] = useState(false);
  const [label, setLabel] = useState(factType.label);
  const [description, setDescription] = useState(factType.description ?? '');

  if (editing) {
    return (
      <li className="flex flex-wrap items-center gap-1.5 py-1" data-testid={`fact-row-edit-${factType.code}`}>
        <input value={label} onChange={(e) => setLabel(e.target.value)}
          className="rounded-md border bg-input px-2 py-1 text-[12px]"
          data-testid={`fact-edit-label-${factType.code}`} />
        <input value={description} onChange={(e) => setDescription(e.target.value)}
          placeholder={t('schema.descriptionField')}
          className="rounded-md border bg-input px-2 py-1 text-[12px]" />
        <button type="button" disabled={disabled}
          onClick={() => { onPatch({ label: label.trim() || factType.label, description }); setEditing(false); }}
          className="rounded-md bg-primary px-2.5 py-1 text-[11px] text-primary-foreground disabled:opacity-50"
          data-testid={`fact-save-${factType.code}`}>{t('common.save')}</button>
        <button type="button" onClick={() => setEditing(false)}
          className="rounded-md border px-2.5 py-1 text-[11px]">{t('common.cancel')}</button>
      </li>
    );
  }

  return (
    <li className="flex items-center gap-1.5 py-1" data-testid={`fact-row-${factType.code}`}>
      <OntologyChip variant="neutral">{factType.label}</OntologyChip>
      <button type="button" onClick={() => setEditing(true)} disabled={disabled}
        className="rounded border px-2 py-0.5 text-[11px]"
        data-testid={`edit-fact-${factType.code}`}>{t('common.edit')}</button>
      <button type="button" onClick={onDelete} disabled={disabled}
        className="rounded border px-2 py-0.5 text-[11px] text-rose-600"
        data-testid={`delete-fact-${factType.code}`}>{t('common.delete')}</button>
    </li>
  );
}
