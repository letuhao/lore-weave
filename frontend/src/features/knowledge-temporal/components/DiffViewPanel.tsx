import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useFacts } from '../hooks/useTemporalReads';
import { useAsOf } from '../context/AsOfContext';
import type { Fact } from '../types';
import type { TemporalSurfaceProps } from './CanonicalCard';

// knowledge-temporal X6c — what changed between the AS-OF ordinal and the head. Reads the
// entity's facts twice (head + as-of) and computes a per-attr diff of single-valued facts:
//   ADDED   — present at head, absent at as-of
//   REMOVED — present at as-of, absent at head
//   CHANGED — present in both, value differs
// Multi-valued facts (cardinality !== 'single') carry no single "current value" to diff, so we
// scope the comparison to single-valued attrs (the bi-temporal "what is X now" reads). Rendered
// side-by-side: "At chapter {asOf}" vs "Current", with subtle add/remove/change coloring.

type DiffStatus = 'added' | 'removed' | 'changed';

interface DiffRow {
  attr: string;
  status: DiffStatus;
  asOfValue: string | null; // value at the as-of ordinal (null when added since)
  headValue: string | null; // current value at head (null when removed since)
}

/** Fold single-valued facts to one value per attr. If the read carries multiple rows for an attr
 *  (the KAL may return history, not a strict as-of fold), pick the one with the GREATEST
 *  valid_from_ordinal — the interval-correct "current at this ordinal" value, not array order. */
function foldSingle(facts: Fact[]): Map<string, string> {
  const m = new Map<string, string>();
  const fromByAttr = new Map<string, number>();
  for (const f of facts) {
    if (f.cardinality !== 'single') continue;
    const prevFrom = fromByAttr.get(f.attr_or_predicate);
    if (prevFrom === undefined || f.valid_from_ordinal >= prevFrom) {
      m.set(f.attr_or_predicate, f.value);
      fromByAttr.set(f.attr_or_predicate, f.valid_from_ordinal);
    }
  }
  return m;
}

function computeDiff(asOfFacts: Fact[], headFacts: Fact[]): DiffRow[] {
  const asOf = foldSingle(asOfFacts);
  const head = foldSingle(headFacts);
  const attrs = new Set<string>([...asOf.keys(), ...head.keys()]);
  const rows: DiffRow[] = [];
  for (const attr of attrs) {
    const a = asOf.get(attr);
    const h = head.get(attr);
    if (a == null && h != null) {
      rows.push({ attr, status: 'added', asOfValue: null, headValue: h });
    } else if (a != null && h == null) {
      rows.push({ attr, status: 'removed', asOfValue: a, headValue: null });
    } else if (a != null && h != null && a !== h) {
      rows.push({ attr, status: 'changed', asOfValue: a, headValue: h });
    }
    // a === h (unchanged) is omitted — the diff shows only deltas.
  }
  // Stable, deterministic order for the CJK-safe render.
  return rows.sort((x, y) => x.attr.localeCompare(y.attr));
}

const STATUS_CLASS: Record<DiffStatus, string> = {
  added: 'bg-emerald-500/5 border-emerald-500/30',
  removed: 'bg-destructive/5 border-destructive/30',
  changed: 'bg-amber-500/5 border-amber-500/30',
};

function DiffValueCell({ value, muted }: { value: string | null; muted?: boolean }) {
  const { t } = useTranslation('knowledge');
  if (value == null) {
    return <span className="text-muted-foreground/60">{t('temporal.diff.absent', '—')}</span>;
  }
  return <span className={cn('break-words', muted && 'text-muted-foreground line-through')}>{value}</span>;
}

/**
 * View (render-only) for the entity bi-temporal diff. Pure of side effects: it derives the diff
 * from the two reads with useMemo. The slider (AsOfContext) gates it — with no as-of set there is
 * nothing to compare against, so it prompts the user to move the slider.
 */
export function DiffViewPanel({ bookId, entityId }: TemporalSurfaceProps) {
  const { t } = useTranslation('knowledge');
  const { asOf } = useAsOf();

  const head = useFacts(bookId, entityId);
  // The as-of read is only meaningful (and only enabled-gated to a distinct query key) when an
  // ordinal is set. asOf === undefined ⇒ this resolves to the head read; we don't render it then.
  const atAsOf = useFacts(bookId, entityId, asOf != null ? { asOf } : undefined);

  const rows = useMemo(
    () => (asOf == null ? [] : computeDiff(atAsOf.facts, head.facts)),
    [asOf, atAsOf.facts, head.facts],
  );

  if (asOf == null) {
    return (
      <section data-testid="diff-view" className="space-y-2">
        <h3 className="text-[12px] font-semibold text-foreground">{t('temporal.diff.title', 'Diff view')}</h3>
        <div
          className="rounded-md border border-dashed px-3 py-6 text-center text-[12px] text-muted-foreground"
          data-testid="diff-hint"
        >
          {t('temporal.diff.hint', 'Move the time slider to compare a past chapter with the current state.')}
        </div>
      </section>
    );
  }

  const isLoading = head.isLoading || atAsOf.isLoading;
  const error = head.error ?? atAsOf.error;

  return (
    <section data-testid="diff-view" className="space-y-2">
      <h3 className="text-[12px] font-semibold text-foreground">{t('temporal.diff.title', 'Diff view')}</h3>

      {isLoading ? (
        <div className="text-[12px] text-muted-foreground" data-testid="diff-loading">
          {t('temporal.diff.loading', 'Loading diff…')}
        </div>
      ) : error ? (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
          data-testid="diff-error"
        >
          {t('temporal.diff.loadFailed', 'Could not load the diff: {{error}}', { error: error.message })}
        </div>
      ) : rows.length === 0 ? (
        <div
          className="rounded-md border border-dashed px-3 py-6 text-center text-[12px] text-muted-foreground"
          data-testid="diff-empty"
        >
          {t('temporal.diff.noChanges', 'No single-valued changes between chapter {{asOf}} and now.', { asOf })}
        </div>
      ) : (
        <div className="overflow-hidden rounded-md border" data-testid="diff-list">
          <div className="grid grid-cols-2 gap-px border-b bg-muted/40 text-[10px] font-medium text-muted-foreground">
            <div className="px-2 py-1" data-testid="diff-col-asof">
              {t('temporal.diff.atChapter', 'At chapter {{asOf}}', { asOf })}
            </div>
            <div className="px-2 py-1" data-testid="diff-col-head">
              {t('temporal.diff.current', 'Current')}
            </div>
          </div>
          <ul className="divide-y">
            {rows.map((row) => (
              <li
                key={row.attr}
                className={cn('border-l-2 text-[12px]', STATUS_CLASS[row.status])}
                data-testid={`diff-row-${row.status}`}
              >
                <div className="px-2 pt-1 text-[10px] font-medium text-foreground/80 break-words">
                  {row.attr}
                </div>
                <div className="grid grid-cols-2 gap-2 px-2 pb-1.5 pt-0.5">
                  <DiffValueCell value={row.asOfValue} muted={row.status === 'removed' || row.status === 'changed'} />
                  <DiffValueCell value={row.headValue} />
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
