import { cn } from '@/lib/utils';
import type { TraceSpanFrame } from '../types';
import { CATEGORY_COLORS } from '../components/ContextBreakdownPanel';
import {
  type TraceFilter,
  filterSpans,
  kfmt,
  spanDeltaKind,
} from './inspectorMath';

// The compile-trace waterfall — the ordered Planner→Compiler decisions for one
// turn, each a span with a tier tag, category dot, action text, and a signed
// delta bar (saved / included / reject). Filterable by phase / saved-only. Pure
// render; the parent owns the `filter` state (volatile view state).

const TRACE_FILTERS: { key: TraceFilter; label: string }[] = [
  { key: 'all', label: 'all' },
  { key: 'planner', label: 'planner' },
  { key: 'compiler', label: 'compiler' },
  { key: 'saved', label: 'saved only' },
];

const DELTA_TEXT: Record<string, string> = {
  saved: 'text-green-400',
  included: 'text-yellow-400',
  reject: 'text-red-400',
  neutral: 'text-muted-foreground',
};
const DELTA_BAR: Record<string, string> = {
  saved: 'bg-green-400',
  included: 'bg-yellow-400',
  reject: 'bg-red-400',
  neutral: 'bg-muted-foreground/40',
};

export function CompileTrace({
  spans,
  filter,
  onFilter,
}: {
  spans: TraceSpanFrame[];
  filter: TraceFilter;
  onFilter: (f: TraceFilter) => void;
}) {
  const rows = filterSpans(spans, filter);
  const maxAbs = Math.max(1, ...spans.map((s) => Math.abs(s.delta)));

  return (
    <div className="rounded-xl border border-border bg-card p-4" data-testid="inspector-trace">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Compile trace — Planner → Compiler
        </div>
        <div className="flex gap-1.5">
          {TRACE_FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => onFilter(f.key)}
              data-trace-filter={f.key}
              className={cn(
                'rounded-full border px-2.5 py-0.5 text-[11px] font-semibold transition-colors',
                filter === f.key
                  ? 'border-primary bg-primary/15 text-primary'
                  : 'border-border text-muted-foreground hover:text-foreground',
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="py-4 text-center text-xs text-muted-foreground" data-testid="trace-empty">
          {spans.length === 0
            ? 'no compile-trace spans for this turn (nothing was cut — raw = compiled)'
            : '— no span matches this filter —'}
        </div>
      ) : (
        <div className="space-y-1">
          {rows.map((s, i) => {
            const kind = spanDeltaKind(s);
            const w = (Math.abs(s.delta) / maxAbs) * 100;
            return (
              <div
                key={i}
                className="flex items-center gap-3 rounded-lg bg-background/40 px-2 py-2"
                data-span-phase={s.phase}
              >
                <span
                  className={cn(
                    'inline-flex min-w-[64px] justify-center rounded-full px-2 py-0.5 text-[11px] font-semibold',
                    s.phase === 'planner' ? 'bg-sky-500/15 text-sky-400' : 'bg-emerald-500/15 text-emerald-400',
                  )}
                >
                  {s.phase}
                </span>
                <span className="rounded border border-border bg-secondary px-1.5 py-0.5 font-mono text-[10px] font-semibold text-muted-foreground">
                  {s.tier}
                </span>
                <span
                  className={cn('h-2 w-2 shrink-0 rounded-full', CATEGORY_COLORS[s.category as keyof typeof CATEGORY_COLORS] ?? 'bg-muted-foreground')}
                  title={s.category}
                />
                <span className={cn('flex-1 text-xs leading-snug', s.is_error && 'text-red-400')}>
                  {s.action}
                </span>
                <div className="flex w-24 shrink-0 items-center justify-end gap-2">
                  <div
                    className={cn('h-1.5 max-w-[56px] rounded', DELTA_BAR[kind])}
                    style={{ width: `${w}%`, opacity: s.delta === 0 ? 0.25 : 0.85 }}
                  />
                  <span className={cn('w-12 text-right font-mono text-[11px] font-semibold', DELTA_TEXT[kind])}>
                    {s.is_error
                      ? 'reject'
                      : s.delta === 0
                        ? '·'
                        : `${s.delta < 0 ? '−' : '+'}${kfmt(Math.abs(s.delta))}`}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
