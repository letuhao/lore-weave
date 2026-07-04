import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ModelPicker } from '@/components/model-picker';
import { useAiTask } from '@/components/ai-task';
import { FormDialog } from '@/components/shared';
import { OntologyChip } from './OntologyChip';
import { useSchemaPropose } from '../../hooks/useGraphSchema';
import type { SchemaProposal } from '../../types/ontology';

// M3b — "describe your world → AI proposes a schema". Single-shot LLM generate
// (propose→confirm): nothing is written until the human ticks components and
// adopts them via the A1 add routes (onAdopt). A real BYOK model is required
// (no hardcoded model); prefer a local chat model for $0 spend.
//
// 14_kg_panels.md K8 (DOCK-9) — was a hand-rolled `fixed inset-0` overlay;
// migrated onto the shared FormDialog (Radix-portal-based), mirroring
// Glossary's ResolveKindModal precedent (13_glossary_panels.md A4). The caller
// (SchemaWorkbench) only mounts this component while `showGenerate` is true, so
// `open` is always true here — the same shape ResolveKindModal uses.

export interface ProposalPicks {
  kinds: { code: string; label?: string }[];
  edges: { code: string; label?: string; source_kinds: string[]; target_kinds: string[] }[];
  facts: { code: string; label?: string }[];
}

interface Props {
  projectId: string;
  onClose: () => void;
  onAdopt: (picks: ProposalPicks) => Promise<void>;
}

export function GenerateSchemaDialog({ projectId, onClose, onAdopt }: Props) {
  const { t } = useTranslation('kgOntology');
  const { propose } = useSchemaPropose(projectId);
  const [premise, setPremise] = useState('');
  const [genre, setGenre] = useState('');
  const [modelRef, setModelRef] = useState('');
  const [skip, setSkip] = useState<Set<string>>(new Set());

  // Shared AI-task controller (propose→review→adopt). Errors flow through the ONE
  // shared reader (WHY — e.g. "empty response" — not a generic "Bad Gateway").
  const task = useAiTask<{ premise: string; genre?: string; model_ref: string }, SchemaProposal>({
    run: (cfg) => propose(cfg),
    confirm: async (proposal) => {
      const picks: ProposalPicks = {
        kinds: proposal.node_kinds.filter((k) => !skip.has(`k:${k.code}`)),
        edges: proposal.edge_types.filter((e) => !skip.has(`e:${e.code}`)),
        facts: proposal.fact_types.filter((f) => !skip.has(`f:${f.code}`)),
      };
      await onAdopt(picks);
      onClose();
    },
    onError: (msg) => toast.error(msg || t('generate.failed')),
  });
  const proposal = task.result;
  const busy = task.busy;

  const toggle = (k: string) =>
    setSkip((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });

  const generate = async () => {
    const p = await task.run({ premise: premise.trim(), genre: genre.trim() || undefined, model_ref: modelRef });
    if (p) setSkip(new Set());
  };

  const adopt = () => { void task.confirm().catch(() => { /* toast shown by onError; keep open */ }); };

  return (
    <FormDialog
      open
      onOpenChange={(o) => { if (!o) onClose(); }}
      title={t('generate.title')}
      size="lg"
    >
      {!proposal ? (
        <div className="space-y-3">
          <label className="block space-y-1 text-[12px]">
            <span className="text-muted-foreground">{t('generate.premise')}</span>
            <textarea value={premise} onChange={(e) => setPremise(e.target.value)} rows={3}
              placeholder={t('generate.premisePlaceholder')}
              className="w-full rounded-md border bg-input px-2 py-1.5"
              data-testid="generate-premise" />
          </label>
          <label className="block space-y-1 text-[12px]">
            <span className="text-muted-foreground">{t('generate.genre')}</span>
            <input value={genre} onChange={(e) => setGenre(e.target.value)}
              placeholder="Tiên hiệp, Fantasy…" className="w-full rounded-md border bg-input px-2 py-1.5" />
          </label>
          <div className="space-y-1 text-[12px]">
            <span className="text-muted-foreground">{t('generate.model')}</span>
            <ModelPicker capability="chat" value={modelRef || null} onChange={(id) => setModelRef(id ?? '')} />
          </div>
          <button type="button" disabled={busy || !premise.trim() || !modelRef} onClick={() => void generate()}
            className="w-full rounded-md bg-primary px-3 py-2 text-[12px] font-medium text-primary-foreground disabled:opacity-50"
            data-testid="generate-run">
            {busy ? t('generate.generating') : t('generate.generateButton')}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-[12px] text-muted-foreground">{t('generate.reviewHelp')}</p>
          <ProposalList title={t('schema.nodeKinds')} prefix="k" items={proposal.node_kinds.map((k) => ({ code: k.code }))} skip={skip} onToggle={toggle} variant="glossary" />
          <ProposalList title={t('schema.edgeTypes')} prefix="e" items={proposal.edge_types.map((e) => ({ code: e.code, hint: `${e.source_kinds.join('/') || '—'} → ${e.target_kinds.join('/') || '—'}` }))} skip={skip} onToggle={toggle} variant="edge" />
          <ProposalList title={t('schema.factTypes')} prefix="f" items={proposal.fact_types.map((f) => ({ code: f.code }))} skip={skip} onToggle={toggle} variant="neutral" />
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => task.reset()} disabled={busy}
              className="rounded-md border px-3 py-1.5 text-[12px]" data-testid="generate-back">{t('generate.regenerate')}</button>
            <button type="button" onClick={() => void adopt()} disabled={busy}
              className="rounded-md bg-primary px-3 py-1.5 text-[12px] font-medium text-primary-foreground disabled:opacity-50"
              data-testid="generate-adopt">{t('generate.adoptButton')}</button>
          </div>
        </div>
      )}
    </FormDialog>
  );
}

function ProposalList({
  title, prefix, items, skip, onToggle, variant,
}: {
  title: string;
  prefix: string;
  items: { code: string; hint?: string }[];
  skip: Set<string>;
  onToggle: (key: string) => void;
  variant: 'glossary' | 'edge' | 'neutral';
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase text-muted-foreground">{title}</p>
      <ul className="space-y-0.5">
        {items.map((it) => (
          <li key={it.code} className="flex items-center gap-1.5 text-[12px]">
            <input type="checkbox" checked={!skip.has(`${prefix}:${it.code}`)}
              onChange={() => onToggle(`${prefix}:${it.code}`)}
              data-testid={`generate-pick-${prefix}-${it.code}`} />
            <OntologyChip variant={variant}>{it.code}</OntologyChip>
            {it.hint && <span className="text-[10px] text-muted-foreground">{it.hint}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
