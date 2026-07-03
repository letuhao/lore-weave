import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { VocabSet, VocabValueCreate } from '../../types/ontology';

// Render-only add form for a vocab value. Targets one of the schema's existing
// vocab SETS (new sets aren't creatable here — additive value-only, matching the
// API). Disabled with a hint when the schema has no vocab sets.
interface Props {
  vocabSets: VocabSet[];
  onSubmit: (args: { setCode: string; body: VocabValueCreate }) => void;
  isSubmitting?: boolean;
}

export function AddVocabValueForm({ vocabSets, onSubmit, isSubmitting }: Props) {
  const { t } = useTranslation('kgOntology');
  const [selectedSet, setSelectedSet] = useState(vocabSets[0]?.code ?? '');
  const [code, setCode] = useState('');
  const [label, setLabel] = useState('');

  const hasSets = vocabSets.length > 0;
  // Guard against the selected set disappearing (deprecated upstream): fall back
  // to the first available set so the submit target is always live.
  const effectiveSet = vocabSets.some((s) => s.code === selectedSet) ? selectedSet : vocabSets[0]?.code ?? '';
  const valid = hasSets && effectiveSet !== '' && code.trim() !== '' && label.trim() !== '';

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    onSubmit({ setCode: effectiveSet, body: { code: code.trim(), label: label.trim() } });
    setCode('');
    setLabel('');
  };

  if (!hasSets) {
    return (
      <div className="rounded-md border p-3 text-[12px]" data-testid="add-vocab-value-form">
        <h3 className="text-sm font-bold">{t('schema.addVocabValue')}</h3>
        <p className="mt-1 text-muted-foreground" data-testid="no-vocab-sets">{t('schema.noVocabSets')}</p>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-2 rounded-md border p-3 text-[12px]" data-testid="add-vocab-value-form">
      <h3 className="text-sm font-bold">{t('schema.addVocabValue')}</h3>
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="space-y-0.5">
          <span className="text-muted-foreground">{t('schema.vocabSet')}</span>
          <select
            value={effectiveSet}
            onChange={(e) => setSelectedSet(e.target.value)}
            className="w-full rounded-md border bg-input px-1 py-1"
            data-testid="vocab-set-select"
          >
            {vocabSets.map((s) => (
              <option key={s.code} value={s.code}>{s.label || s.code}</option>
            ))}
          </select>
        </label>
        <label className="space-y-0.5">
          <span className="text-muted-foreground">{t('schema.code')}</span>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="w-full rounded-md border bg-input px-2 py-1"
            placeholder="alive"
            data-testid="vocab-value-code-input"
          />
        </label>
        <label className="space-y-0.5">
          <span className="text-muted-foreground">{t('schema.label')}</span>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            className="w-full rounded-md border bg-input px-2 py-1"
            data-testid="vocab-value-label-input"
          />
        </label>
      </div>
      <button
        type="submit"
        disabled={!valid || isSubmitting}
        className="rounded-md bg-primary px-3 py-1.5 text-[12px] font-medium text-primary-foreground disabled:opacity-50"
        data-testid="vocab-value-submit"
      >
        {t('schema.add')}
      </button>
    </form>
  );
}
