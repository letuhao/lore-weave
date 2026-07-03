import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Cardinality, EdgeTypeCreate } from '../../types/ontology';

// Small render-only add form (mirrors the "Edit edge type" panel in
// 02-schema-editor.html). Owns only its transient input state; business logic
// (the POST + invalidate) lives in useGraphSchema, invoked via onSubmit.

interface Props {
  onSubmit: (body: EdgeTypeCreate) => void;
  isSubmitting?: boolean;
}

export function AddEdgeTypeForm({ onSubmit, isSubmitting }: Props) {
  const { t } = useTranslation('kgOntology');
  const [code, setCode] = useState('');
  const [label, setLabel] = useState('');
  const [temporal, setTemporal] = useState(false);
  const [cardinality, setCardinality] = useState<Cardinality>('single_active');

  const valid = code.trim() !== '' && label.trim() !== '';

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    onSubmit({
      code: code.trim(),
      label: label.trim(),
      temporal,
      cardinality,
    });
    setCode('');
    setLabel('');
    setTemporal(false);
    setCardinality('single_active');
  };

  return (
    <form
      onSubmit={submit}
      className="space-y-2 rounded-md border p-3 text-[12px]"
      data-testid="add-edge-type-form"
    >
      <h3 className="text-sm font-bold">{t('schema.addEdgeType')}</h3>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="space-y-0.5">
          <span className="text-muted-foreground">{t('schema.code')}</span>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="w-full rounded-md border bg-input px-2 py-1"
            placeholder="LOVER_OF"
            data-testid="edge-code-input"
          />
        </label>
        <label className="space-y-0.5">
          <span className="text-muted-foreground">{t('schema.label')}</span>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            className="w-full rounded-md border bg-input px-2 py-1"
            data-testid="edge-label-input"
          />
        </label>
      </div>
      <div className="flex items-center gap-4">
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={temporal}
            onChange={(e) => setTemporal(e.target.checked)}
            data-testid="edge-temporal-input"
          />
          {t('schema.temporalField')}
        </label>
        <label className="flex items-center gap-1.5">
          <span className="text-muted-foreground">{t('schema.cardinality')}</span>
          <select
            value={cardinality}
            onChange={(e) => setCardinality(e.target.value as Cardinality)}
            className="rounded-md border bg-input px-1 py-0.5"
            data-testid="edge-cardinality-input"
          >
            <option value="single_active">single_active</option>
            <option value="multi_active">multi_active</option>
          </select>
        </label>
      </div>
      <button
        type="submit"
        disabled={!valid || isSubmitting}
        className="rounded-md bg-primary px-3 py-1.5 text-[12px] font-medium text-primary-foreground disabled:opacity-50"
        data-testid="edge-submit"
      >
        {t('schema.addButton')}
      </button>
    </form>
  );
}
