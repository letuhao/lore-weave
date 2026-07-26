import { useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { AllocationMap } from './AllocationMap';
import { CompileTrace } from './CompileTrace';
import { PressureGauge } from './PressureGauge';
import { TurnList } from './TurnList';
import { useContextTrace } from './useContextTrace';
import {
  type StatusFilter,
  type TraceFilter,
  computeKpis,
  filterTurns,
  kfmt,
} from './inspectorMath';

// Context Compiler · Trace Inspector — the container (MVC controller-for-view): it
// owns the VOLATILE view state (session pick, status/search filter, page, selected
// turn, trace filter) and composes the rail + the per-turn inspector. Data comes
// from useContextTrace. `enabled` gates the fetch (panel mounted-but-hidden). Any
// filter change resets the page to 0; j/k navigate turns.

const PER = 8;

export function ContextInspectorView({
  enabled = true,
  initialSessionId,
}: {
  enabled?: boolean;
  initialSessionId?: string | null;
}) {
  const { sessions, sessionId, selectSession, points, loading, error, reload } = useContextTrace(
    enabled,
    initialSessionId,
  );

  const [status, setStatusRaw] = useState<StatusFilter>('all');
  const [query, setQueryRaw] = useState('');
  const [page, setPage] = useState(0);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const [traceFilter, setTraceFilter] = useState<TraceFilter>('all');

  // Any filter change resets to page 0 (§11a) so the first result is visible.
  const setStatus = (s: StatusFilter) => {
    setStatusRaw(s);
    setPage(0);
  };
  const setQuery = (q: string) => {
    setQueryRaw(q);
    setPage(0);
  };

  const filtered = useMemo(() => filterTurns(points, status, query), [points, status, query]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PER));
  const clampedPage = Math.min(page, pageCount - 1);
  const paged = filtered.slice(clampedPage * PER, clampedPage * PER + PER);
  const kpis = useMemo(() => computeKpis(points), [points]);

  // Default the selection to the most recent turn once data loads / the selection
  // falls out of the current set.
  useEffect(() => {
    if (points.length === 0) {
      setSelectedSeq(null);
      return;
    }
    setSelectedSeq((cur) =>
      cur != null && points.some((p) => p.sequence_num === cur)
        ? cur
        : points[points.length - 1].sequence_num,
    );
  }, [points]);

  // j/k keyboard navigation across the FILTERED order (skips typing in the search).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT') return;
      if (e.key !== 'j' && e.key !== 'k') return;
      const idx = filtered.findIndex((p) => p.sequence_num === selectedSeq);
      if (idx < 0) return;
      const next = e.key === 'j' ? idx + 1 : idx - 1;
      if (next < 0 || next >= filtered.length) return;
      setSelectedSeq(filtered[next].sequence_num);
      setPage(Math.floor(next / PER));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [filtered, selectedSeq]);

  const selected = points.find((p) => p.sequence_num === selectedSeq) ?? null;

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="context-inspector">
      {/* top bar: session picker + KPIs — wraps on narrow screens (multi-device) */}
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border bg-background/40 px-4 py-2">
        <div className="text-sm font-semibold">
          Context Compiler <span className="text-muted-foreground">· Trace Inspector</span>
        </div>
        <select
          value={sessionId ?? ''}
          onChange={(e) => selectSession(e.target.value)}
          className="max-w-[220px] truncate rounded-lg border border-border bg-input px-2 py-1 text-xs outline-none"
          data-testid="inspector-session-select"
        >
          {sessions.length === 0 && <option value="">no sessions</option>}
          {sessions.map((s) => (
            <option key={s.session_id} value={s.session_id}>
              {s.title || s.session_id.slice(0, 8)}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={reload}
          className="rounded-full border border-border px-2.5 py-0.5 text-[11px] text-muted-foreground hover:text-foreground"
        >
          refresh
        </button>
        <div className="ml-auto flex flex-wrap items-center gap-x-5 gap-y-1 text-right">
          <Kpi label="avg reduction" value={kpis.avgReductionPct != null ? `−${Math.round(kpis.avgReductionPct)}%` : '—'} className="text-green-400" />
          <Kpi label="tokens saved" value={kpis.tokensSaved > 0 ? kfmt(kpis.tokensSaved) : '—'} className="text-accent" />
          <Kpi label="model window" value={kpis.modelWindow != null ? kpis.modelWindow.toLocaleString() : '—'} />
        </div>
      </header>

      {/* stack (rail above content) on mobile/tablet; side-by-side from md up */}
      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <TurnList
          paged={paged}
          selectedSeq={selectedSeq}
          onSelect={setSelectedSeq}
          status={status}
          onStatus={setStatus}
          query={query}
          onQuery={setQuery}
          page={clampedPage}
          pageCount={pageCount}
          filteredCount={filtered.length}
          onPage={setPage}
        />

        <main className="min-h-0 flex-1 overflow-y-auto p-3 sm:p-5">
          {loading && points.length === 0 ? (
            <Centered>loading context trace…</Centered>
          ) : error ? (
            <Centered className="text-red-400">{error}</Centered>
          ) : !selected ? (
            <Centered>
              {points.length === 0
                ? 'no measured turns in this session yet'
                : 'select a turn'}
            </Centered>
          ) : (
            <div className="mx-auto max-w-[900px] space-y-4">
              <div className="flex items-start gap-3">
                <span className="rounded bg-secondary px-2 py-1 font-mono text-xs text-muted-foreground">
                  T-{selected.sequence_num}
                </span>
                <div className="flex-1">
                  <div className="text-lg leading-snug" data-testid="inspector-selected-message">
                    {selected.user_message || '(no message)'}
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 font-mono text-[11px] text-muted-foreground">
                    <Chip label="intent" value={selected.frame.intent ?? '—'} />
                    <Chip
                      label="entity-presence"
                      value={
                        selected.frame.entity_presence?.matched?.length
                          ? selected.frame.entity_presence.matched.join(', ')
                          : selected.frame.entity_presence?.reason ?? '—'
                      }
                    />
                    <Chip label="retrieval" value={selected.frame.retrieval_mode ?? '—'} />
                    <Chip label="window" value={selected.frame.context_length != null ? kfmt(selected.frame.context_length) : '—'} />
                  </div>
                </div>
              </div>

              <PressureGauge frame={selected.frame} />
              <AllocationMap frame={selected.frame} />
              <CompileTrace
                spans={selected.frame.trace ?? []}
                filter={traceFilter}
                onFilter={setTraceFilter}
              />
              <div className="pb-2 text-center font-mono text-[11px] text-muted-foreground">
                <kbd className="rounded border border-border bg-secondary px-1">j</kbd> /{' '}
                <kbd className="rounded border border-border bg-secondary px-1">k</kbd> navigate turns
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function Kpi({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn('font-mono text-base font-bold', className)}>{value}</div>
    </div>
  );
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5">
      {label}: <b className="text-foreground">{value}</b>
    </span>
  );
}

function Centered({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('flex h-full items-center justify-center text-sm text-muted-foreground', className)}>
      {children}
    </div>
  );
}
