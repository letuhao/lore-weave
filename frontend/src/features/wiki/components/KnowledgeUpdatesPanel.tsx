import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw, X, Check, AlertTriangle, ShieldAlert, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useWikiStaleness } from '../hooks/useWikiStaleness';
import type { WikiStalenessRow } from '../types';

/**
 * wiki-llm Phase-2b — the "Knowledge updates" change-feed (§5.3 DECIDE).
 *
 * Lists the pending staleness rows (filled by the §5.2 capture consumer) grouped
 * by WHY they're stale, with a severity badge. The user multi-selects + hits
 * "Regenerate" (→ a single cost-capped batch via the M7b dialog, entity_ids), or
 * "Dismiss" a row (accept-as-is, no spend). Nothing regenerates until the user
 * acts — the whole point of the deferred design.
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
  const { rows, dismiss, dismissing } = useWikiStaleness(bookId);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Group by reason for the section headers; rows already arrive severity-sorted.
  const groups = useMemo(() => {
    const g: Record<string, WikiStalenessRow[]> = {};
    for (const r of rows) (g[r.reason_code] ??= []).push(r);
    return g;
  }, [rows]);

  // De-dupe entity ids (an entity can have several stale rows → one regen covers all).
  const selectedEntityIds = useMemo(() => {
    const ids = new Set<string>();
    for (const r of rows) if (selected.has(r.staleness_id)) ids.add(r.entity_id);
    return [...ids];
  }, [rows, selected]);

  if (!open) return null;

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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="flex max-h-[80vh] w-[620px] flex-col rounded-lg border bg-card shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b px-5 py-3">
          <div>
            <h3 className="text-sm font-semibold">{t('staleness.title')}</h3>
            <p className="text-[11px] text-muted-foreground">{t('staleness.subtitle', { count: rows.length })}</p>
          </div>
          <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-secondary" aria-label={t('staleness.close')}>
            <X className="h-4 w-4" />
          </button>
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
                  return (
                    <div
                      key={r.staleness_id}
                      data-testid="staleness-row"
                      className="flex items-center gap-2 border-b border-border px-3 py-2 last:border-b-0"
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(r.staleness_id)}
                        onChange={() => toggle(r.staleness_id)}
                        aria-label={t('staleness.select', { name: r.display_name })}
                      />
                      <span
                        className="h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: r.kind.color }}
                      />
                      <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{r.display_name || 'Untitled'}</span>
                      <span className={cn('inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[9px] font-medium', severityCls(r.severity))}>
                        <Icon className="h-2.5 w-2.5" />
                        {t(`staleness.severity.${r.severity}`, { defaultValue: r.severity })}
                      </span>
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
                  );
                })}
              </div>
            ))
          )}
        </div>

        <div className="flex items-center justify-between border-t px-5 py-3">
          <span className="text-[11px] text-muted-foreground">
            {t('staleness.selectedCount', { count: selectedEntityIds.length })}
          </span>
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
    </div>
  );
}
