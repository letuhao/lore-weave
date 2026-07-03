import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Sparkles, X } from 'lucide-react';
import { ModelPicker } from '@/components/model-picker';
import { OntologyChip } from './OntologyChip';
import { useSchemaPropose } from '../../hooks/useGraphSchema';
import type { SchemaProposal } from '../../types/ontology';

// M3b — "describe your world → AI proposes a schema". Single-shot LLM generate
// (propose→confirm): nothing is written until the human ticks components and
// adopts them via the A1 add routes (onAdopt). A real BYOK model is required
// (no hardcoded model); prefer a local chat model for $0 spend.

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
  const { propose, isProposing } = useSchemaPropose(projectId);
  const [premise, setPremise] = useState('');
  const [genre, setGenre] = useState('');
  const [modelRef, setModelRef] = useState('');
  const [proposal, setProposal] = useState<SchemaProposal | null>(null);
  const [skip, setSkip] = useState<Set<string>>(new Set());
  const [adopting, setAdopting] = useState(false);

  const toggle = (k: string) =>
    setSkip((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });

  const generate = async () => {
    try {
      const p = await propose({ premise: premise.trim(), genre: genre.trim() || undefined, model_ref: modelRef });
      setProposal(p);
      setSkip(new Set());
    } catch (e) {
      const body = (e as { body?: { message?: string } }).body;
      toast.error(body?.message || (e as Error).message || t('generate.failed'));
    }
  };

  const adopt = async () => {
    if (!proposal) return;
    const picks: ProposalPicks = {
      kinds: proposal.node_kinds.filter((k) => !skip.has(`k:${k.code}`)),
      edges: proposal.edge_types.filter((e) => !skip.has(`e:${e.code}`)),
      facts: proposal.fact_types.filter((f) => !skip.has(`f:${f.code}`)),
    };
    setAdopting(true);
    try {
      await onAdopt(picks);
      onClose();
    } finally {
      setAdopting(false);
    }
  };

  const busy = isProposing || adopting;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog" aria-modal="true" data-testid="generate-schema-dialog">
      <div className="max-h-[85vh] w-full max-w-lg space-y-3 overflow-y-auto rounded-lg border bg-card p-4 shadow-lg">
        <header className="flex items-center gap-1.5">
          <Sparkles className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-bold">{t('generate.title')}</h3>
          <button type="button" onClick={onClose} className="ml-auto rounded p-1 hover:bg-muted/40" aria-label="close">
            <X className="h-4 w-4" />
          </button>
        </header>

        {!proposal ? (
          <>
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
              {isProposing ? t('generate.generating') : t('generate.generateButton')}
            </button>
          </>
        ) : (
          <>
            <p className="text-[12px] text-muted-foreground">{t('generate.reviewHelp')}</p>
            <ProposalList title={t('schema.nodeKinds')} prefix="k" items={proposal.node_kinds.map((k) => ({ code: k.code }))} skip={skip} onToggle={toggle} variant="glossary" />
            <ProposalList title={t('schema.edgeTypes')} prefix="e" items={proposal.edge_types.map((e) => ({ code: e.code, hint: `${e.source_kinds.join('/') || '—'} → ${e.target_kinds.join('/') || '—'}` }))} skip={skip} onToggle={toggle} variant="edge" />
            <ProposalList title={t('schema.factTypes')} prefix="f" items={proposal.fact_types.map((f) => ({ code: f.code }))} skip={skip} onToggle={toggle} variant="neutral" />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setProposal(null)} disabled={busy}
                className="rounded-md border px-3 py-1.5 text-[12px]" data-testid="generate-back">{t('generate.regenerate')}</button>
              <button type="button" onClick={() => void adopt()} disabled={busy}
                className="rounded-md bg-primary px-3 py-1.5 text-[12px] font-medium text-primary-foreground disabled:opacity-50"
                data-testid="generate-adopt">{t('generate.adoptButton')}</button>
            </div>
          </>
        )}
      </div>
    </div>
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
