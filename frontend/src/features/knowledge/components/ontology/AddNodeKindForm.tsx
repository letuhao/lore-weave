import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { SchemaNodeKindCreate, Strength } from '../../types/ontology';

// Render-only add form for a schema node-kind (kind_code + strength). Transient
// input state only; the POST + invalidate live in useGraphSchema via onSubmit.
interface Props {
  onSubmit: (body: SchemaNodeKindCreate) => void;
  isSubmitting?: boolean;
}

export function AddNodeKindForm({ onSubmit, isSubmitting }: Props) {
  const { t } = useTranslation('kgOntology');
  const [kindCode, setKindCode] = useState('');
  const [strength, setStrength] = useState<Strength>('optional');

  const valid = kindCode.trim() !== '';

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    onSubmit({ kind_code: kindCode.trim(), strength });
    setKindCode('');
    setStrength('optional');
  };

  return (
    <form onSubmit={submit} className="space-y-2 rounded-md border p-3 text-[12px]" data-testid="add-node-kind-form">
      <h3 className="text-sm font-bold">{t('schema.addNodeKind')}</h3>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="space-y-0.5">
          <span className="text-muted-foreground">{t('schema.kindCode')}</span>
          <input
            value={kindCode}
            onChange={(e) => setKindCode(e.target.value)}
            className="w-full rounded-md border bg-input px-2 py-1"
            placeholder="character"
            data-testid="node-kind-code-input"
          />
        </label>
        <label className="space-y-0.5">
          <span className="text-muted-foreground">{t('schema.strength')}</span>
          <select
            value={strength}
            onChange={(e) => setStrength(e.target.value as Strength)}
            className="w-full rounded-md border bg-input px-1 py-1"
            data-testid="node-kind-strength-input"
          >
            <option value="optional">{t('schema.optional')}</option>
            <option value="required">{t('schema.required')}</option>
          </select>
        </label>
      </div>
      <button
        type="submit"
        disabled={!valid || isSubmitting}
        className="rounded-md bg-primary px-3 py-1.5 text-[12px] font-medium text-primary-foreground disabled:opacity-50"
        data-testid="node-kind-submit"
      >
        {t('schema.add')}
      </button>
    </form>
  );
}
