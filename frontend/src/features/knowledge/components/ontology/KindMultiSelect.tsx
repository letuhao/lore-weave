import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { OntologyChip } from './OntologyChip';

// M1 — typed multiselect of node kinds (replaces the free-text comma string for an
// edge type's source/target kinds). You pick from the kinds that ACTUALLY exist in
// the schema, so you can't reference a kind that isn't defined; a free-add input is
// kept for a kind you haven't declared yet (it'll show as "unknown" until you add
// it as a node kind). Pure render — value/onChange owned by the parent.

interface Props {
  value: string[];
  options: string[]; // the node-kind codes defined in this schema
  onChange: (next: string[]) => void;
  disabled?: boolean;
  testid?: string;
}

export function KindMultiSelect({ value, options, onChange, disabled, testid }: Props) {
  const { t } = useTranslation('kgOntology');
  const [free, setFree] = useState('');
  const remaining = options.filter((o) => !value.includes(o));

  const add = (code: string) => {
    const c = code.trim();
    if (c && !value.includes(c)) onChange([...value, c]);
  };

  return (
    <div className="flex flex-wrap items-center gap-1" data-testid={testid}>
      {value.length === 0 && (
        <span className="text-[11px] text-muted-foreground">{t('schema.anyKind')}</span>
      )}
      {value.map((code) => (
        <span key={code} className="inline-flex items-center gap-0.5">
          <OntologyChip variant={options.includes(code) ? 'glossary' : 'deprecated'}>{code}</OntologyChip>
          <button type="button" disabled={disabled}
            onClick={() => onChange(value.filter((c) => c !== code))}
            className="rounded border px-1 text-[10px] text-rose-600"
            data-testid={`${testid}-remove-${code}`}
            aria-label={`remove ${code}`}>×</button>
        </span>
      ))}
      {remaining.length > 0 && (
        <select
          value=""
          disabled={disabled}
          onChange={(e) => { if (e.target.value) add(e.target.value); }}
          className="rounded-md border bg-input px-1.5 py-0.5 text-[11px]"
          data-testid={`${testid}-add`}
        >
          <option value="">＋ {t('schema.addKind')}</option>
          {remaining.map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
      )}
      <input
        value={free}
        disabled={disabled}
        onChange={(e) => setFree(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(free); setFree(''); } }}
        placeholder={t('schema.otherKind')}
        className="w-24 rounded-md border bg-input px-1.5 py-0.5 text-[11px]"
        data-testid={`${testid}-free`}
      />
    </div>
  );
}
