import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { FactTypeCreate } from '../../types/ontology';

// Render-only add form for a schema fact-type (code + label). Transient input
// state only; the POST + invalidate live in useGraphSchema via onSubmit.
interface Props {
  onSubmit: (body: FactTypeCreate) => void;
  isSubmitting?: boolean;
}

export function AddFactTypeForm({ onSubmit, isSubmitting }: Props) {
  const { t } = useTranslation('kgOntology');
  const [code, setCode] = useState('');
  const [label, setLabel] = useState('');

  const valid = code.trim() !== '' && label.trim() !== '';

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    onSubmit({ code: code.trim(), label: label.trim() });
    setCode('');
    setLabel('');
  };

  return (
    <form onSubmit={submit} className="space-y-2 rounded-md border p-3 text-[12px]" data-testid="add-fact-type-form">
      <h3 className="text-sm font-bold">{t('schema.addFactType')}</h3>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="space-y-0.5">
          <span className="text-muted-foreground">{t('schema.code')}</span>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="w-full rounded-md border px-2 py-1"
            placeholder="birth"
            data-testid="fact-type-code-input"
          />
        </label>
        <label className="space-y-0.5">
          <span className="text-muted-foreground">{t('schema.label')}</span>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            className="w-full rounded-md border px-2 py-1"
            data-testid="fact-type-label-input"
          />
        </label>
      </div>
      <button
        type="submit"
        disabled={!valid || isSubmitting}
        className="rounded-md bg-primary px-3 py-1.5 text-[12px] font-medium text-white disabled:opacity-50"
        data-testid="fact-type-submit"
      >
        {t('schema.add')}
      </button>
    </form>
  );
}
