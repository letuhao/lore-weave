import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import { OntologyChip } from './OntologyChip';
import type { ObservedComponents } from '../../types/ontology';

// M3a — "your book's extracted graph already has these kinds + relations; add the
// missing ones to the schema?" Deterministic (no LLM): the observed set comes from
// GET …/schema/observed. Shows only what's NOT already in the schema; ticked items
// are promoted via the A1 add routes (edges pre-filled with observed source/target).

export interface InferEdgePick {
  code: string;
  source_kinds: string[];
  target_kinds: string[];
}

interface Props {
  observed: ObservedComponents;
  existingKinds: Set<string>;
  existingEdges: Set<string>;
  disabled?: boolean;
  onAdd: (kinds: string[], edges: InferEdgePick[]) => void;
}

export function InferFromGraphPanel({ observed, existingKinds, existingEdges, disabled, onAdd }: Props) {
  const { t } = useTranslation('kgOntology');
  const missingKinds = useMemo(
    () => observed.node_kinds.filter((k) => !existingKinds.has(k.code)),
    [observed.node_kinds, existingKinds],
  );
  const missingEdges = useMemo(
    () => observed.edge_types.filter((e) => !existingEdges.has(e.code)),
    [observed.edge_types, existingEdges],
  );

  // default: everything ticked
  const [skip, setSkip] = useState<Set<string>>(new Set());
  const toggle = (key: string) =>
    setSkip((s) => { const n = new Set(s); n.has(key) ? n.delete(key) : n.add(key); return n; });

  if (missingKinds.length === 0 && missingEdges.length === 0) return null;

  const add = () => {
    const kinds = missingKinds.filter((k) => !skip.has(`k:${k.code}`)).map((k) => k.code);
    const edges: InferEdgePick[] = missingEdges
      .filter((e) => !skip.has(`e:${e.code}`))
      .map((e) => ({ code: e.code, source_kinds: e.source_kinds, target_kinds: e.target_kinds }));
    if (kinds.length || edges.length) onAdd(kinds, edges);
  };

  const selected =
    missingKinds.filter((k) => !skip.has(`k:${k.code}`)).length +
    missingEdges.filter((e) => !skip.has(`e:${e.code}`)).length;

  return (
    <section className="space-y-2 rounded-lg border border-primary/40 bg-primary/5 p-3" data-testid="infer-from-graph">
      <header className="flex items-center gap-1.5">
        <Sparkles className="h-3.5 w-3.5 text-primary" />
        <h3 className="text-[12px] font-semibold">{t('infer.title')}</h3>
        <span className="text-[11px] text-muted-foreground">{t('infer.help')}</span>
      </header>

      {missingKinds.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold uppercase text-muted-foreground">{t('schema.nodeKinds')}</p>
          <ul className="flex flex-wrap gap-2">
            {missingKinds.map((k) => (
              <li key={k.code} className="flex items-center gap-1 text-[12px]">
                <input type="checkbox" checked={!skip.has(`k:${k.code}`)} disabled={disabled}
                  onChange={() => toggle(`k:${k.code}`)} data-testid={`infer-kind-${k.code}`} />
                <OntologyChip variant="glossary">{k.code}</OntologyChip>
                <span className="text-[10px] text-muted-foreground">{t('schema.usedBy', { count: k.count })}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {missingEdges.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold uppercase text-muted-foreground">{t('schema.edgeTypes')}</p>
          <ul className="space-y-1">
            {missingEdges.map((e) => (
              <li key={e.code} className="flex flex-wrap items-center gap-1 text-[12px]">
                <input type="checkbox" checked={!skip.has(`e:${e.code}`)} disabled={disabled}
                  onChange={() => toggle(`e:${e.code}`)} data-testid={`infer-edge-${e.code}`} />
                <OntologyChip variant="edge">{e.code}</OntologyChip>
                <span className="text-[10px] text-muted-foreground">
                  {(e.source_kinds.join('/') || '—')} → {(e.target_kinds.join('/') || '—')} · {t('schema.usedBy', { count: e.count })}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <button type="button" onClick={add} disabled={disabled || selected === 0}
        className="rounded-md bg-primary px-3 py-1.5 text-[12px] font-medium text-primary-foreground disabled:opacity-50"
        data-testid="infer-add-selected">
        {t('infer.addButton', { count: selected })}
      </button>
    </section>
  );
}
