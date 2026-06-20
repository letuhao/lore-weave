import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { OntologyChip } from './OntologyChip';
import type { GraphView, ViewCreate } from '../../types/ontology';

// Render-only view builder (mirrors 03-views.html). Toggles edge-type +
// node-kind codes into a per-user lens and emits onSave(ViewCreate). Owns only
// its draft selection state; persistence lives in useGraphViews.

interface Props {
  // the schema's available codes to pick from
  availableEdgeTypes: string[];
  availableNodeKinds: string[];
  // optional existing view to edit (else a new draft)
  initial?: GraphView | null;
  onSave: (body: ViewCreate) => void;
  isSaving?: boolean;
}

function toggle(list: string[], code: string): string[] {
  return list.includes(code) ? list.filter((c) => c !== code) : [...list, code];
}

export function ViewBuilder({
  availableEdgeTypes,
  availableNodeKinds,
  initial,
  onSave,
  isSaving,
}: Props) {
  const { t } = useTranslation('kgOntology');
  const [name, setName] = useState(initial?.name ?? '');
  const [edges, setEdges] = useState<string[]>(initial?.edge_type_codes ?? []);
  const [kinds, setKinds] = useState<string[]>(initial?.node_kind_codes ?? []);

  const valid = name.trim() !== '';

  const save = () => {
    if (!valid) return;
    onSave({
      code: initial?.code,
      name: name.trim(),
      edge_type_codes: edges,
      node_kind_codes: kinds,
    });
  };

  return (
    <div className="space-y-3" data-testid="view-builder">
      <label className="block space-y-0.5 text-[12px]">
        <span className="text-[11px] font-semibold uppercase text-muted-foreground">
          {t('views.name')}
        </span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-md border px-2 py-1"
          data-testid="view-name-input"
        />
      </label>

      <fieldset className="space-y-1">
        <legend className="text-[11px] font-semibold uppercase text-muted-foreground">
          {t('views.edgeTypes')}
        </legend>
        <div className="flex flex-wrap gap-1">
          {availableEdgeTypes.map((code) => {
            const on = edges.includes(code);
            return (
              <button
                key={code}
                type="button"
                onClick={() => setEdges((p) => toggle(p, code))}
                aria-pressed={on}
                data-testid={`view-edge-${code}`}
                className={cn('rounded px-1.5 py-0.5 text-[10px] font-medium', on ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-500')}
              >
                {code} {on ? '✓' : ''}
              </button>
            );
          })}
        </div>
      </fieldset>

      <fieldset className="space-y-1">
        <legend className="text-[11px] font-semibold uppercase text-muted-foreground">
          {t('views.nodeKinds')}
        </legend>
        <div className="flex flex-wrap gap-1">
          {availableNodeKinds.map((code) => {
            const on = kinds.includes(code);
            return (
              <button
                key={code}
                type="button"
                onClick={() => setKinds((p) => toggle(p, code))}
                aria-pressed={on}
                data-testid={`view-kind-${code}`}
                className={cn('rounded px-1.5 py-0.5 text-[10px] font-medium', on ? 'bg-teal-600 text-white' : 'bg-slate-100 text-slate-500')}
              >
                {code} {on ? '✓' : ''}
              </button>
            );
          })}
        </div>
      </fieldset>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={save}
          disabled={!valid || isSaving}
          className="rounded-md bg-primary px-3 py-1.5 text-[12px] font-medium text-white disabled:opacity-50"
          data-testid="view-save"
        >
          {initial ? t('views.saveButton') : t('views.createButton')}
        </button>
        <span className="text-[11px] text-muted-foreground">
          <OntologyChip variant="project">{t('views.perUser')}</OntologyChip>
        </span>
      </div>
    </div>
  );
}
