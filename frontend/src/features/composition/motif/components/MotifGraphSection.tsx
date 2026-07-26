// 3a-C — the motif GRAPH as a collapsible SECTION (not a canvas — OQ-2; a list is honest,
// cheap, keyboard-navigable). Shows one motif's composed_of members, precedes successions,
// and variant_of siblings, each a neighbor code+name row with a delete. An add-edge form
// picks a kind + a neighbor from your own motifs. The DB guard's 409 (self-link/cycle/
// cross-tier) renders INLINE on the form (spec 33 §3.1) — never a swallowed toast.
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { motifApi, type MotifLinkKind, type MotifLinkRow } from '../api';
import { useMotifLinks } from '../hooks/useMotifLinks';

const KINDS: MotifLinkKind[] = ['composed_of', 'precedes', 'variant_of'];
const KIND_LABEL: Record<MotifLinkKind, string> = {
  composed_of: 'Composed of', precedes: 'Precedes', variant_of: 'Variant of',
};

function errMsg(e: unknown): string | null {
  if (!e) return null;
  return e instanceof Error ? e.message : String(e);
}

export function MotifGraphSection(
  { motifId, token, bookId, readOnly = false }:
  { motifId: string; token: string | null; bookId?: string | null; readOnly?: boolean },
) {
  const { t } = useTranslation('composition');
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [kind, setKind] = useState<MotifLinkKind>('precedes');
  const [neighbor, setNeighbor] = useState('');
  const graph = useMotifLinks(open ? motifId : null, token, bookId);

  // Candidates for the neighbor picker: your own motifs (you can only link motifs you own),
  // minus the anchor itself. Only fetched once the add-form opens.
  const candidatesQ = useQuery({
    queryKey: ['composition', 'motifs', 'mine-for-link'],
    queryFn: () => motifApi.list({ scope: 'mine', limit: 100 }, token!),
    enabled: !!token && adding,
    select: (d) => d.motifs.filter((m) => m.id !== motifId),
  });

  const submit = () => {
    if (!neighbor) return;
    graph.create.mutate({ to_motif_id: neighbor, kind }, {
      onSuccess: () => { setNeighbor(''); setAdding(false); },
    });
  };

  const byKind = (k: MotifLinkKind) => graph.links.filter((l) => l.kind === k);

  return (
    <section data-testid="motif-graph-section" className="border-t border-neutral-200 dark:border-neutral-700">
      <button
        type="button"
        data-testid="motif-graph-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:text-neutral-200 dark:hover:bg-neutral-800/50"
      >
        <span className={`transition-transform ${open ? 'rotate-90' : ''}`}>▸</span>
        {t('motif.graph.title', { defaultValue: 'Graph — composed of · precedes · variant of' })}
        {graph.links.length > 0 && <span className="ml-1 text-neutral-400">({graph.links.length})</span>}
      </button>

      {open && (
        <div className="px-2 pb-2">
          {graph.isLoading && (
            <p className="p-2 text-center text-[11px] text-neutral-500">{t('motif.graph.loading', { defaultValue: 'Loading edges…' })}</p>
          )}
          {graph.isError && (
            <p data-testid="motif-graph-error" className="rounded bg-red-50 px-2 py-1 text-[11px] text-red-700 dark:bg-red-950/30 dark:text-red-300">
              {t('motif.graph.error', { defaultValue: 'Could not load the motif graph.' })}
              <button type="button" className="ml-2 underline" onClick={() => graph.refetch()}>{t('motif.graph.retry', { defaultValue: 'Retry' })}</button>
            </p>
          )}
          {!graph.isLoading && !graph.isError && graph.links.length === 0 && (
            <p data-testid="motif-graph-empty" className="p-2 text-[11px] text-neutral-500">{t('motif.graph.empty', { defaultValue: 'No relationships yet.' })}</p>
          )}

          {KINDS.map((k) => {
            const rows = byKind(k);
            if (rows.length === 0) return null;
            return (
              <div key={k} className="mt-1">
                <div className="text-[10px] uppercase tracking-wide text-neutral-400">{t(`motif.graph.kind.${k}`, { defaultValue: KIND_LABEL[k] })}</div>
                <ul className="mt-0.5 space-y-0.5">
                  {rows.map((l: MotifLinkRow) => (
                    <li key={l.id} data-testid="motif-graph-edge" className="flex items-center gap-1.5 rounded bg-neutral-50 px-1.5 py-0.5 text-[11px] dark:bg-neutral-800/50">
                      <span className="text-neutral-400" title={l.direction === 'out' ? 'this → neighbor' : 'neighbor → this'}>{l.direction === 'out' ? '→' : '←'}</span>
                      <span className="min-w-0 flex-1 truncate"><span className="font-medium">{l.neighbor_name}</span> <span className="text-neutral-400">{l.neighbor_code}</span></span>
                      {!readOnly && (
                        <button
                          type="button"
                          data-testid="motif-graph-edge-delete"
                          aria-label={t('motif.graph.deleteEdge', { defaultValue: 'Remove edge' })}
                          disabled={graph.remove.isPending}
                          onClick={() => graph.remove.mutate(l.id)}
                          className="rounded px-1 text-neutral-400 hover:bg-red-100 hover:text-red-600 disabled:opacity-40 dark:hover:bg-red-950/40"
                        >×</button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}

          {/* delete error (rare — a foreign/missing edge) */}
          {graph.remove.isError && (
            <p data-testid="motif-graph-delete-error" className="mt-1 rounded bg-red-50 px-2 py-1 text-[11px] text-red-700 dark:bg-red-950/30 dark:text-red-300">{errMsg(graph.remove.error)}</p>
          )}

          {!readOnly && (
            adding ? (
              <div data-testid="motif-graph-add-form" className="mt-2 space-y-1 rounded border border-neutral-200 p-1.5 dark:border-neutral-700">
                <div className="flex gap-1">
                  <select data-testid="motif-graph-kind" value={kind} onChange={(e) => setKind(e.target.value as MotifLinkKind)} className="rounded border border-neutral-300 bg-white px-1 py-0.5 text-[11px] dark:border-neutral-600 dark:bg-neutral-800">
                    {KINDS.map((k) => <option key={k} value={k}>{t(`motif.graph.kind.${k}`, { defaultValue: KIND_LABEL[k] })}</option>)}
                  </select>
                  <select data-testid="motif-graph-neighbor" value={neighbor} onChange={(e) => setNeighbor(e.target.value)} className="min-w-0 flex-1 rounded border border-neutral-300 bg-white px-1 py-0.5 text-[11px] dark:border-neutral-600 dark:bg-neutral-800">
                    <option value="">{t('motif.graph.pickNeighbor', { defaultValue: 'Pick a motif…' })}</option>
                    {(candidatesQ.data ?? []).map((m) => <option key={m.id} value={m.id}>{m.name} · {m.code}</option>)}
                  </select>
                </div>
                {graph.create.isError && (
                  <p data-testid="motif-graph-add-error" className="rounded bg-red-50 px-2 py-1 text-[11px] text-red-700 dark:bg-red-950/30 dark:text-red-300">{errMsg(graph.create.error)}</p>
                )}
                <div className="flex gap-1">
                  <button type="button" data-testid="motif-graph-add-submit" disabled={!neighbor || graph.create.isPending} onClick={submit} className="rounded bg-amber-600 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-amber-700 disabled:opacity-40">
                    {t('motif.graph.add', { defaultValue: 'Add edge' })}
                  </button>
                  <button type="button" onClick={() => { setAdding(false); graph.create.reset(); }} className="rounded border border-neutral-300 px-2 py-0.5 text-[11px] dark:border-neutral-600">{t('motif.graph.cancel', { defaultValue: 'Cancel' })}</button>
                </div>
              </div>
            ) : (
              <button type="button" data-testid="motif-graph-add-toggle" onClick={() => { setAdding(true); setOpen(true); }} className="mt-2 rounded border border-neutral-300 px-2 py-0.5 text-[11px] text-neutral-600 hover:bg-neutral-50 dark:border-neutral-600 dark:text-neutral-300 dark:hover:bg-neutral-800">
                + {t('motif.graph.addEdge', { defaultValue: 'Add relationship' })}
              </button>
            )
          )}
        </div>
      )}
    </section>
  );
}
