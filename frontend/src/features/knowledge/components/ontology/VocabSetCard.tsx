import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { OntologyChip } from './OntologyChip';
import type {
  VocabSet,
  VocabSetPatch,
  VocabValueCreate,
  VocabValuePatch,
} from '../../types/ontology';

// One vocab SET card: the set (label/closed edit + delete) plus its VALUES, each
// with an inline label edit + delete, and an add-value row. Full CRUD (A1).

interface Props {
  set: VocabSet;
  disabled?: boolean;
  onPatchSet: (patch: VocabSetPatch) => void;
  onDeleteSet: () => void;
  onAddValue: (body: VocabValueCreate) => void;
  onPatchValue: (code: string, patch: VocabValuePatch) => void;
  onDeleteValue: (code: string) => void;
}

export function VocabSetCard({
  set, disabled, onPatchSet, onDeleteSet, onAddValue, onPatchValue, onDeleteValue,
}: Props) {
  const { t } = useTranslation('kgOntology');
  const [newCode, setNewCode] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [editValue, setEditValue] = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState('');

  const addValue = () => {
    if (!newCode.trim() || !newLabel.trim()) return;
    onAddValue({ code: newCode.trim(), label: newLabel.trim() });
    setNewCode('');
    setNewLabel('');
  };

  return (
    <section className="rounded-md border p-3" data-testid={`vocab-set-${set.code}`}>
      <header className="mb-2 flex items-center gap-2">
        <h4 className="text-[12px] font-semibold">{set.label}</h4>
        <label className="flex items-center gap-1 text-[11px] text-muted-foreground">
          <input type="checkbox" checked={set.closed} disabled={disabled}
            onChange={(e) => onPatchSet({ closed: e.target.checked })}
            data-testid={`vocab-set-closed-${set.code}`} />
          {t('schema.closed')}
        </label>
        <button type="button" onClick={onDeleteSet} disabled={disabled}
          className="ml-auto rounded border px-2 py-0.5 text-[11px] text-rose-600"
          data-testid={`delete-vocab-set-${set.code}`}>{t('common.delete')}</button>
      </header>

      <ul className="flex flex-wrap gap-1.5">
        {(set.values ?? []).map((v) =>
          editValue === v.code ? (
            <li key={v.code} className="flex items-center gap-1">
              <input value={editLabel} onChange={(e) => setEditLabel(e.target.value)}
                className="rounded-md border bg-background px-1.5 py-0.5 text-[11px]"
                data-testid={`vocab-value-edit-${set.code}-${v.code}`} />
              <button type="button" disabled={disabled}
                onClick={() => { onPatchValue(v.code, { label: editLabel.trim() || v.label }); setEditValue(null); }}
                className="rounded bg-primary px-1.5 py-0.5 text-[10px] text-white">{t('common.save')}</button>
            </li>
          ) : (
            <li key={v.code} className="inline-flex items-center gap-0.5">
              <OntologyChip variant="drive">{v.code}</OntologyChip>
              <button type="button" disabled={disabled}
                onClick={() => { setEditValue(v.code); setEditLabel(v.label); }}
                className="rounded border px-1 text-[10px]"
                data-testid={`edit-vocab-value-${set.code}-${v.code}`}>{t('common.edit')}</button>
              <button type="button" onClick={() => onDeleteValue(v.code)} disabled={disabled}
                className="rounded border px-1 text-[10px] text-rose-600"
                data-testid={`delete-vocab-value-${set.code}-${v.code}`}>×</button>
            </li>
          ),
        )}
      </ul>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <input value={newCode} onChange={(e) => setNewCode(e.target.value)} placeholder={t('schema.code')}
          className="w-28 rounded-md border bg-background px-2 py-1 text-[11px]"
          data-testid={`vocab-value-new-code-${set.code}`} />
        <input value={newLabel} onChange={(e) => setNewLabel(e.target.value)} placeholder={t('schema.label')}
          className="w-32 rounded-md border bg-background px-2 py-1 text-[11px]"
          data-testid={`vocab-value-new-label-${set.code}`} />
        <button type="button" onClick={addValue} disabled={disabled}
          className="rounded-md border px-2 py-1 text-[11px]"
          data-testid={`add-vocab-value-${set.code}`}>{t('schema.addButton')}</button>
      </div>
    </section>
  );
}
