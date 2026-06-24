import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { AlertTriangle, Sparkles, Loader2, CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useGaps } from '../hooks/useGaps';
import { useBulkPromote } from '../hooks/useBulkPromote';

// C10 (C10-gap-report) — entity Gap Report tab, rendered inside the C6
// project-detail shell scoped by ROUTE (G6 — no project select-box).
//
// ENTITY gaps: high-mention DISCOVERED entities with no glossary entry,
// from knowledge-service find_gap_candidates(). Distinct from the
// lore-enrichment attribute-dimension detect-gaps (a separate feature).
//
// Controls:
//   - min_mentions threshold — feeds straight to the BE query (the
//     pass-through lock).
//   - limit — caps how many candidates are fetched.
// Bulk-promote: select gaps, promote them SEQUENTIALLY via the C9
// single-promote (useBulkPromote → knowledgeApi.promoteEntity) with a
// live progress indicator that survives a single-item failure.

const DEFAULT_MIN_MENTIONS = 50;
const DEFAULT_LIMIT = 100;
const LIMIT_OPTIONS = [25, 50, 100, 200] as const;

// Debounce the threshold so typing "200" fires ONE query, not three
// (each keystroke changes the useGaps queryKey → a refetch otherwise).
function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const h = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(h);
  }, [value, delayMs]);
  return debounced;
}

interface GapReportTabProps {
  // G6 — project scope from the route. Required: the gap report is always
  // single-project (no cross-project gap view).
  scopedProjectId: string;
}

export function GapReportTab({ scopedProjectId }: GapReportTabProps) {
  const { t } = useTranslation('knowledge');
  const [minMentions, setMinMentions] = useState<number>(DEFAULT_MIN_MENTIONS);
  const [limit, setLimit] = useState<number>(DEFAULT_LIMIT);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // The query reads the DEBOUNCED threshold; the input stays responsive.
  const debouncedMinMentions = useDebounced(minMentions, 300);

  const { gaps, total, isLoading, isFetching, error } = useGaps({
    projectId: scopedProjectId,
    minMentions: debouncedMinMentions,
    limit,
  });

  const bulk = useBulkPromote({
    onComplete: ({ succeeded, failures }) => {
      if (failures.length === 0) {
        toast.success(
          t('gap.bulkPromote.allOk', { count: succeeded.length }),
        );
      } else if (succeeded.length === 0) {
        toast.error(
          t('gap.bulkPromote.allFailed', { count: failures.length }),
        );
      } else {
        toast.warning(
          t('gap.bulkPromote.partial', {
            ok: succeeded.length,
            failed: failures.length,
          }),
        );
      }
      // Promoted gaps leave the list (the hook invalidates the gap query,
      // which refetches). Keep the FAILED ids selected so the user can
      // retry them directly; drop the succeeded ones.
      setSelected(new Set(failures.map((f) => f.entityId)));
    },
  });

  const allSelected = gaps.length > 0 && selected.size === gaps.length;

  const toggleOne = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    setSelected((prev) =>
      prev.size === gaps.length ? new Set() : new Set(gaps.map((g) => g.id)),
    );
  };

  const runBulkPromote = () => {
    const ids = gaps.filter((g) => selected.has(g.id)).map((g) => g.id);
    if (ids.length === 0) return;
    void bulk.run(ids);
  };

  // Top gap = the highest-mention candidate (find_gap_candidates returns
  // mention_count DESC). A cheap "most urgent" summary signal.
  const topGap = useMemo(() => (gaps.length > 0 ? gaps[0] : null), [gaps]);

  const failedIds = useMemo(
    () => new Set(bulk.failures.map((f) => f.entityId)),
    [bulk.failures],
  );

  return (
    <div data-testid="gap-report-tab" className="space-y-5">
      <header className="space-y-1">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-500" />
          <h2 className="font-serif text-base font-semibold">
            {t('gap.heading')}
          </h2>
        </div>
        <p className="text-[12px] text-muted-foreground">
          {t('gap.subtitle')}
        </p>
      </header>

      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="rounded-md border bg-card p-3">
          <div
            className="text-2xl font-semibold tabular-nums"
            data-testid="gap-summary-count"
          >
            {total}
          </div>
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {t('gap.summary.candidates')}
          </div>
        </div>
        <div className="rounded-md border bg-card p-3">
          <div className="text-2xl font-semibold tabular-nums">
            {minMentions}
          </div>
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {t('gap.summary.threshold')}
          </div>
        </div>
        <div className="col-span-2 rounded-md border bg-card p-3 sm:col-span-1">
          <div
            className="truncate text-base font-medium"
            data-testid="gap-summary-top"
          >
            {topGap ? topGap.name : t('gap.summary.none')}
          </div>
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {topGap
              ? t('gap.summary.topMentions', { count: topGap.mention_count })
              : t('gap.summary.topLabel')}
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-end gap-4 rounded-md border bg-muted/30 p-3">
        <label className="flex flex-col gap-1 text-[12px]">
          <span className="font-medium text-muted-foreground">
            {t('gap.controls.minMentions')}
          </span>
          <input
            type="number"
            min={0}
            value={minMentions}
            data-testid="gap-min-mentions"
            onChange={(e) => {
              const v = Number(e.target.value);
              setMinMentions(Number.isFinite(v) && v >= 0 ? v : 0);
            }}
            className="w-24 rounded border bg-background px-2 py-1 text-[13px]"
          />
        </label>
        <label className="flex flex-col gap-1 text-[12px]">
          <span className="font-medium text-muted-foreground">
            {t('gap.controls.limit')}
          </span>
          <select
            value={limit}
            data-testid="gap-limit"
            onChange={(e) => setLimit(Number(e.target.value))}
            className="rounded border bg-background px-2 py-1 text-[13px]"
          >
            {LIMIT_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>

        {isFetching && (
          <span className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            {t('gap.loading')}
          </span>
        )}
      </div>

      {/* Bulk-promote bar */}
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
          <input
            type="checkbox"
            checked={allSelected}
            onChange={toggleAll}
            data-testid="gap-select-all"
            disabled={gaps.length === 0 || bulk.isRunning}
          />
          {t('gap.selectAll')}
        </label>
        <button
          type="button"
          onClick={runBulkPromote}
          data-testid="gap-bulk-promote"
          disabled={selected.size === 0 || bulk.isRunning}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-[13px] font-medium text-primary-foreground transition-colors',
            'hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50',
          )}
        >
          {bulk.isRunning ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="h-3.5 w-3.5" />
          )}
          {t('gap.bulkPromote.cta', { count: selected.size })}
        </button>

        {/* Progress indicator */}
        {(bulk.isRunning || bulk.progress.total > 0) && (
          <span
            className="flex items-center gap-1.5 text-[12px] text-muted-foreground"
            data-testid="gap-bulk-progress"
            role="status"
            aria-live="polite"
          >
            {bulk.isRunning ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
            )}
            {t('gap.bulkPromote.progress', {
              done: bulk.progress.done,
              total: bulk.progress.total,
            })}
            {bulk.progress.failed > 0 && (
              <span className="text-destructive">
                {t('gap.bulkPromote.failedCount', {
                  count: bulk.progress.failed,
                })}
              </span>
            )}
          </span>
        )}
      </div>

      {/* Gap list */}
      {error ? (
        <div
          className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-[13px] text-destructive"
          data-testid="gap-error"
        >
          {t('gap.error')}
        </div>
      ) : isLoading ? (
        <div className="p-6 text-center text-[13px] text-muted-foreground">
          {t('gap.loading')}
        </div>
      ) : gaps.length === 0 ? (
        <div
          className="rounded-md border border-dashed p-8 text-center text-[13px] text-muted-foreground"
          data-testid="gap-empty"
        >
          {t('gap.empty')}
        </div>
      ) : (
        <ul className="divide-y rounded-md border" data-testid="gap-list">
          {gaps.map((g) => {
            const failed = failedIds.has(g.id);
            return (
              <li
                key={g.id}
                className={cn(
                  'flex items-center gap-3 px-3 py-2.5',
                  failed && 'bg-destructive/5',
                )}
              >
                <input
                  type="checkbox"
                  checked={selected.has(g.id)}
                  onChange={() => toggleOne(g.id)}
                  data-testid={`gap-select-${g.id}`}
                  aria-label={t('gap.selectRow', { name: g.name })}
                  disabled={bulk.isRunning}
                />
                <span className="min-w-0 flex-1 truncate text-[13px] font-medium">
                  {g.name}
                </span>
                <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                  {g.kind}
                </span>
                <span
                  className="shrink-0 text-[12px] tabular-nums text-muted-foreground"
                  title={t('gap.mentionsTitle')}
                >
                  {t('gap.mentions', { count: g.mention_count })}
                </span>
                {failed && (
                  <span className="shrink-0 text-[11px] font-medium text-destructive">
                    {t('gap.itemFailed')}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
