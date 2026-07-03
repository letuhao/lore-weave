import { useTranslation } from 'react-i18next';
import { OntologyChip } from './OntologyChip';
import type { SchemaNodeKind, Strength } from '../../types/ontology';

// One node-kind row: display + a strength toggle (required/optional — the only
// editable attribute; `kind_code` is IMMUTABLE) + delete.

interface Props {
  nodeKind: SchemaNodeKind;
  disabled?: boolean;
  onPatchStrength: (strength: Strength) => void;
  onDelete: () => void;
}

export function NodeKindRow({ nodeKind, disabled, onPatchStrength, onDelete }: Props) {
  const { t } = useTranslation('kgOntology');
  return (
    <li className="flex items-center gap-2 py-1" data-testid={`node-kind-row-${nodeKind.kind_code}`}>
      <OntologyChip variant="glossary">{nodeKind.kind_code}</OntologyChip>
      <select
        value={nodeKind.strength}
        disabled={disabled}
        onChange={(e) => onPatchStrength(e.target.value as Strength)}
        className="rounded-md border bg-input px-1.5 py-0.5 text-[11px]"
        data-testid={`node-kind-strength-${nodeKind.kind_code}`}
      >
        <option value="required">required</option>
        <option value="optional">optional</option>
      </select>
      <button
        type="button"
        onClick={onDelete}
        disabled={disabled}
        className="rounded border px-2 py-0.5 text-[11px] text-rose-600"
        data-testid={`delete-node-kind-${nodeKind.kind_code}`}
      >
        {t('common.delete')}
      </button>
    </li>
  );
}
