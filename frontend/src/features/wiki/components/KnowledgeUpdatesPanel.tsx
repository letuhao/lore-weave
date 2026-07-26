import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import * as Dialog from '@radix-ui/react-dialog';
import { RefreshCw, X, Check, AlertTriangle, ShieldAlert, Clock, Info, ScanSearch, ExternalLink, GitCompare } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { useOptionalStudioHost } from '@/features/studio/host/StudioHostProvider';
import { followStudioLink } from '@/features/studio/host/studioLinks';
import { wikiApi } from '../api';
import { useWikiStaleness } from '../hooks/useWikiStaleness';
import { sourceJumpUrl } from '../lib/stalenessSource';
import { diffLines } from '../lib/wikiDiff';
import type { WikiStalenessRow, WikiGenConfig, WikiStalenessDiff } from '../types';

/**
 * wiki-llm Phase-2b + W2 — the "Knowledge updates" change-feed (§5.3 DECIDE).
 *
 * Lists the pending staleness rows (filled by the §5.2 capture consumer) grouped by
 * WHY they're stale, with a severity badge + when-detected. The user multi-selects +
 * "Regenerate" (→ a cost-capped batch via the M7b dialog) or "Dismiss selected"
 * (accept-as-is, no spend); a header "Rescan" re-runs the recipe/kg fingerprint sweep.
 * Nothing regenerates until the user acts — the whole point of the deferred design.
 *
 * 15_wiki_panels.md B4 — DOCK-9: hand-rolled `fixed inset-0` overlay replaced with raw
 * `Dialog.*` (not `FormDialog` — the header's "Rescan" action button doesn't fit FormDialog's
 * title/description-only template, and relocating it would be a redesign the migration
 * explicitly declined). B4 — DOCK-7: the per-row "view source" jump would navigate the whole
 * studio away from itself when opened from inside the `wiki` dock panel; branch through
 * `followStudioLink` (StepConfig.tsx precedent) when a StudioHost is present, otherwise the
 * original <Link> (classic WikiTab page has no studio to route through).
 */
function severityIcon(sev: string) {
  if (sev === 'hard') return ShieldAlert;
  if (sev === 'structural') return AlertTriangle;
  return Clock;
}
function severityCls(sev: string) {
  if (sev === 'hard') return 'bg-destructive/12 text-destructive';
  if (sev === 'structural') return 'bg-amber-400/15 text-amber-500';
  return 'bg-primary/10 text-primary';
}

/* ── W6b-2b — the inline source diff under a row ──────────────────────────── */

function StalenessDiffBlock({ diff, loading, t }: {
  diff: WikiStalenessDiff | null;
  loading: boolean;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  if (loading) {
    return <div data-testid="staleness-diff" className="px-3 pb-2 text-[10px] text-muted-foreground">{t('staleness.diffLoading')}</div>;
  }
  if (!diff || !diff.available) {
    // No snapshot (pre-W6b-2 article) or the "after" couldn't be fetched → use the jump.
    return <div data-testid="staleness-diff" className="px-3 pb-2 text-[10px] text-muted-foreground">{t('staleness.noDiff')}</div>;
  }
  const rows = diffLines((diff.before ?? '').split('\n'), (diff.after ?? '').split('\n'));
  return (
    <div data-testid="staleness-diff" className="px-3 pb-2">
      {diff.approximate && (
        <p className="mb-1 text-[10px] text-amber-500">{t('staleness.diffApproximate')}</p>
      )}
      <div className="max-h-48 overflow-y-auto rounded border font-mono text-[11px]">
        {rows.map((row, i) => (
          <div
            key={i}
            className={cn(
              'whitespace-pre-wrap px-2 py-0.5',
              row.type === 'del' ? 'bg-destructive/10 text-destructive'
                : row.type === 'add' ? 'bg-emerald-500/10 text-emerald-600'
                  : 'text-muted-foreground',
            )}
          >
            <span className="select-none opacity-60">{row.type === 'del' ? '- ' : row.type === 'add' ? '+ ' : '  '}</span>
            {row.text}
          </div>
        ))}
      </div>
    </div>
  );
}

export function KnowledgeUpdatesPanel({
  bookId,
  open,
  onClose,
  onRegenerate,
}: {
  bookId: string;
  open: boolean;
  onClose: () => void;
  /** Open the (batch) regenerate dialog scoped to these entities. */
  onRegenerate: (entityIds: string[], label: string) => void;
}) {
  const { t } = useTranslation('wiki');
  const { accessToken } = useAuth();
  const studioHost = useOptionalStudioHost();
  const { rows, dismiss, dismissing, dismissMany, rescan, rescanning } = useWikiStaleness(bookId);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // W6b-2b — on-demand source diff (before snapshot vs current source). Imperative
  // (not useQuery) so it's a one-shot per click and doesn't fight the panel's other
  // queries. diffFor toggles the inline diff under a row.
  const [diffFor, setDiffFor] = useState<string | null>(null);
  const [diff, setDiff] = useState<WikiStalenessDiff | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const openDiff = async (id: string) => {
    if (diffFor === id) { setDiffFor(null); return; }
    setDiffFor(id);
    setDiff(null);
    setDiffLoading(true);
    try {
      setDiff(await wikiApi.getStalenessDiff(bookId, id, accessToken!));
    } catch {
      setDiff({ available: false });
    } finally {
      setDiffLoading(false);
    }
  };

  // Flat per-article cost (same figure the budget gate charges) for the batch estimate.
  const configQuery = useQuery<WikiGenConfig>({
    queryKey: ['wiki-gen-config', bookId],
    queryFn: () => wikiApi.getGenConfig(bookId, accessToken!),
    enabled: open && !!accessToken && !!bookId,
  });

  // Group by reason for the section headers; rows already arrive severity-sorted.
  const groups = useMemo(() => {
    const g: Record<string, WikiStalenessRow[]> = {};
    for (const r of rows) (g[r.reason_code] ??= []).push(r);
    return g;
  }, [rows]);

  // Severity composition of the whole feed (the change-feed at a glance).
  const sev = useMemo(() => {
    const c = { hard: 0, structural: 0, content: 0 };
    for (const r of rows) {
      if (r.severity === 'hard') c.hard++;
      else if (r.severity === 'structural') c.structural++;
      else c.content++;
    }
    return c;
  }, [rows]);

  // De-dupe entity ids (an entity can have several stale rows → one regen covers all).
  const selectedEntityIds = useMemo(() => {
    const ids = new Set<string>();
    for (const r of rows) if (selected.has(r.staleness_id)) ids.add(r.entity_id);
    return [...ids];
  }, [rows, selected]);

  if (!open) return null;

  const perArticle = Number(configQuery.data?.cost_per_article_usd ?? NaN);
  const estTotal = Number.isFinite(perArticle) ? perArticle * selectedEntityIds.length : null;

  const toggle = (id: string) =>
    setSelected((prev) => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });

  const handleRegenerate = () => {
    if (selectedEntityIds.length === 0) return;
    onRegenerate(selectedEntityIds, t('staleness.nArticles', { count: selectedEntityIds.length }));
    onClose();
  };

  const handleDismissSelected = async () => {
    if (selected.size === 0) return;
    await dismissMany([...selected]);
    setSelected(new Set());
  };

  return (
    <Dialog.Root open onOpenChange={(next) => { if (!next) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[80vh] w-[640px] -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg border bg-card shadow-xl">
        <div className="flex items-center justify-between border-b px-5 py-3">
          <div>
            <Dialog.Title className="text-sm font-semibold">{t('staleness.title')}</Dialog.Title>
            <Dialog.Description className="text-[11px] text-muted-foreground">{t('staleness.subtitle', { count: rows.length })}</Dialog.Description>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={rescan}
              disabled={rescanning}
              data-testid="staleness-rescan"
              title={t('staleness.rescan')}
              className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] hover:bg-secondary disabled:opacity-50"
            >
              <ScanSearch className={cn('h-3.5 w-3.5', rescanning && 'animate-pulse')} />
              {rescanning ? t('staleness.rescanning') : t('staleness.rescan')}
            </button>
            <Dialog.Close asChild>
              <button className="rounded p-1 text-muted-foreground hover:bg-secondary" aria-label={t('staleness.close')}>
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>
        </div>

        <div className="flex items-start gap-2 border-b bg-blue-500/[0.06] px-5 py-2.5 text-[11px] text-muted-foreground">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-blue-400" />
          <span>{t('staleness.ledgerNote')}</span>
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-2">
          {rows.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-muted-foreground" data-testid="staleness-empty">
              {t('staleness.empty')}
            </div>
          ) : (
            Object.entries(groups).map(([reason, items]) => (
              <div key={reason} className="mb-2">
                <div className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {t(`staleness.reason.${reason}`, { defaultValue: reason })}
                </div>
                {items.map((r) => {
                  const Icon = severityIcon(r.severity);
                  const when = new Date(r.detected_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
                  // W6b-1 — jump to the CURRENT source that changed (entity → glossary,
                  // chapter → reader); null for recipe/KG drift (no single source).
                  const jump = sourceJumpUrl(bookId, r.source_ref);
                  // W6b-2b — a row has a diffable source when source_ref names one.
                  const sr = (r.source_ref ?? {}) as { source_type?: string; source_id?: string };
                  const diffable = !!(sr.source_type && sr.source_id);
                  return (
                    <div key={r.staleness_id} className="border-b border-border last:border-b-0">
                    <div
                      data-testid="staleness-row"
                      className="flex items-center gap-2 px-3 py-2"
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(r.staleness_id)}
                        onChange={() => toggle(r.staleness_id)}
                        aria-label={t('staleness.select', { name: r.display_name })}
                      />
                      <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: r.kind.color }} />
                      <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{r.display_name || 'Untitled'}</span>
                      <span className="shrink-0 text-[10px] text-muted-foreground">{when}</span>
                      <span className={cn('inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[9px] font-medium', severityCls(r.severity))}>
                        <Icon className="h-2.5 w-2.5" />
                        {t(`staleness.severity.${r.severity}`, { defaultValue: r.severity })}
                      </span>
                      {diffable && (
                        <button
                          onClick={() => openDiff(r.staleness_id)}
                          data-testid="staleness-diff-toggle"
                          title={t('staleness.viewDiff')}
                          className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-secondary hover:text-foreground"
                        >
                          <GitCompare className="h-3 w-3" />
                          {t('staleness.viewDiff')}
                        </button>
                      )}
                      {jump && (
                        studioHost ? (
                          <button
                            type="button"
                            onClick={() => { followStudioLink(jump, studioHost, { bookId }); onClose(); }}
                            data-testid="staleness-source-jump"
                            title={t('staleness.viewSource')}
                            className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-secondary hover:text-foreground"
                          >
                            <ExternalLink className="h-3 w-3" />
                            {t('staleness.viewSource')}
                          </button>
                        ) : (
                          <Link
                            to={jump}
                            onClick={onClose}
                            data-testid="staleness-source-jump"
                            title={t('staleness.viewSource')}
                            className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-secondary hover:text-foreground"
                          >
                            <ExternalLink className="h-3 w-3" />
                            {t('staleness.viewSource')}
                          </Link>
                        )
                      )}
                      <button
                        onClick={() => dismiss(r.staleness_id)}
                        disabled={dismissing === r.staleness_id}
                        data-testid="staleness-dismiss"
                        title={t('staleness.dismiss')}
                        className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] hover:bg-secondary disabled:opacity-50"
                      >
                        <Check className="h-3 w-3" />
                        {t('staleness.dismiss')}
                      </button>
                    </div>
                    {diffFor === r.staleness_id && (
                      <StalenessDiffBlock diff={diff} loading={diffLoading} t={t} />
                    )}
                    </div>
                  );
                })}
              </div>
            ))
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t px-5 py-3">
          <div className="flex items-center gap-3 text-[11px]">
            {sev.hard > 0 && <span className="text-destructive">● {sev.hard} {t('staleness.severity.hard')}</span>}
            {sev.structural > 0 && <span className="text-amber-500">● {sev.structural} {t('staleness.severity.structural')}</span>}
            {sev.content > 0 && <span className="text-blue-400">● {sev.content} {t('staleness.severity.content')}</span>}
          </div>
          <div className="flex items-center gap-3">
            {estTotal != null && selectedEntityIds.length > 0 && (
              <span className="font-mono text-[11px] text-muted-foreground" data-testid="staleness-cost">
                {t('staleness.estimateLabel')} ~${estTotal.toFixed(2)}
              </span>
            )}
            <button
              onClick={handleDismissSelected}
              disabled={selected.size === 0}
              data-testid="staleness-dismiss-all"
              className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-xs hover:bg-secondary disabled:opacity-50"
            >
              <Check className="h-3.5 w-3.5" />
              {t('staleness.dismissSelected')}
            </button>
            <button
              onClick={handleRegenerate}
              disabled={selectedEntityIds.length === 0}
              data-testid="staleness-regenerate"
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:brightness-110 disabled:opacity-50"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              {t('staleness.regenerateSelected', { count: selectedEntityIds.length })}
            </button>
          </div>
        </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
