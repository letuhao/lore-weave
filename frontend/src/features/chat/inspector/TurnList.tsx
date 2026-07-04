import { cn } from '@/lib/utils';
import type { ContextTracePoint } from '../types';
import {
  STATUS_FILTERS,
  type StatusFilter,
  kfmt,
  statusMeta,
  turnReductionPct,
} from './inspectorMath';

// The left rail — search + status filters + a card per turn (id, reduction %,
// message snippet, mini compiled/target bar, ≤2 status chips) + pagination. Pure
// render; the container owns all filter/page/selection state (verify-by-effect:
// changing the status filter changes which cards render).

export function TurnList({
  paged,
  selectedSeq,
  onSelect,
  status,
  onStatus,
  query,
  onQuery,
  page,
  pageCount,
  filteredCount,
  onPage,
}: {
  paged: ContextTracePoint[];
  selectedSeq: number | null;
  onSelect: (seq: number) => void;
  status: StatusFilter;
  onStatus: (s: StatusFilter) => void;
  query: string;
  onQuery: (q: string) => void;
  page: number;
  pageCount: number;
  filteredCount: number;
  onPage: (p: number) => void;
}) {
  return (
    <aside
      className="flex w-full max-h-[45vh] shrink-0 flex-col border-b border-border bg-background/40 md:max-h-none md:w-[300px] md:border-b-0 md:border-r"
      data-testid="inspector-turn-list"
    >
      <div className="border-b border-border p-3">
        <input
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder="filter turns by message / intent…"
          className="mb-2.5 w-full rounded-lg border border-border bg-input px-3 py-2 text-xs outline-none"
          data-testid="inspector-search"
        />
        <div className="flex flex-wrap gap-1.5">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => onStatus(f)}
              data-status-filter={f}
              className={cn(
                'rounded-full border px-2.5 py-0.5 text-[11px] font-semibold transition-colors',
                status === f
                  ? 'border-primary bg-primary/15 text-primary'
                  : 'border-border text-muted-foreground hover:text-foreground',
              )}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 space-y-1.5 overflow-y-auto p-2">
        {paged.length === 0 ? (
          <div className="py-6 text-center text-xs text-muted-foreground">no turns</div>
        ) : (
          paged.map((p) => {
            const red = turnReductionPct(p.frame);
            const compiled = p.frame.used_tokens;
            const target = p.frame.target ?? null;
            const over = target != null && compiled > target;
            const compPct = target != null ? Math.min(100, (compiled / target) * 100) : 100;
            const active = p.sequence_num === selectedSeq;
            return (
              <button
                type="button"
                key={p.sequence_num}
                onClick={() => onSelect(p.sequence_num)}
                data-turn-seq={p.sequence_num}
                data-active={active}
                className={cn(
                  'w-full rounded-lg border px-3 py-2.5 text-left transition-colors',
                  active
                    ? 'border-accent bg-accent/10'
                    : 'border-border bg-card hover:bg-accent/5',
                )}
              >
                <div className="mb-1 flex items-center justify-between">
                  <span className="font-mono text-[11px] text-muted-foreground">
                    T-{p.sequence_num}
                  </span>
                  <span
                    className={cn(
                      'font-mono text-[11px] font-semibold',
                      red != null && red >= 60 ? 'text-green-400' : 'text-yellow-400',
                    )}
                  >
                    {red != null ? `−${Math.round(red)}%` : '—'}
                  </span>
                </div>
                <div className="mb-2 line-clamp-2 text-xs leading-snug text-foreground">
                  {p.user_message || <span className="text-muted-foreground">(no message)</span>}
                </div>
                <div className="mb-1.5 flex items-center gap-2">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
                    <div
                      className={cn('h-full', over ? 'bg-yellow-400' : 'bg-accent')}
                      style={{ width: `${compPct}%` }}
                    />
                  </div>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {kfmt(compiled)}/{target != null ? kfmt(target) : '—'}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {(p.frame.status_flags ?? []).slice(0, 2).map((f) => (
                    <span
                      key={f}
                      className={cn(
                        'rounded-full border border-border bg-secondary px-1.5 py-0.5 text-[10px] font-semibold',
                        statusMeta(f).className,
                      )}
                    >
                      {statusMeta(f).label}
                    </span>
                  ))}
                </div>
              </button>
            );
          })
        )}
      </div>

      <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs text-muted-foreground">
        <button
          type="button"
          onClick={() => onPage(page - 1)}
          disabled={page <= 0}
          className="rounded-full border border-border px-2.5 py-0.5 disabled:opacity-40"
        >
          ‹ prev
        </button>
        <span className="font-mono" data-testid="inspector-page-label">
          {pageCount === 0 ? '0 / 0' : `${page + 1} / ${pageCount}`} · {filteredCount}
        </span>
        <button
          type="button"
          onClick={() => onPage(page + 1)}
          disabled={page >= pageCount - 1}
          className="rounded-full border border-border px-2.5 py-0.5 disabled:opacity-40"
        >
          next ›
        </button>
      </div>
    </aside>
  );
}
