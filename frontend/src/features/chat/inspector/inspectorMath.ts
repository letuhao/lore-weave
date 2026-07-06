// Context Compiler · Trace Inspector — pure math + config (spec §11). Exported so
// component/E2E tests assert EFFECTS (gauge color state, KPI aggregate, filter
// result) directly without rendering. No React, no I/O.

import type { ContextTraceFrame, ContextTracePoint, TraceSpanFrame } from '../types';

// ── status chips ──────────────────────────────────────────────────────────────
// The turn's status_flags[] → a label + a Tailwind text-color token. Only the
// flags the BE actually emits today (gated/included/compacted/elastic/overflow/
// wire) drive real turns; the rest (continuity/collapsed) are defined for when
// their tier lands so the chip renders instead of showing a raw flag string.
export interface StatusMeta {
  label: string;
  className: string;
}
export const STATUS_META: Record<string, StatusMeta> = {
  gated: { label: 'grounding gated', className: 'text-emerald-400' },
  included: { label: 'grounding included', className: 'text-amber-400' },
  compacted: { label: 'compacted', className: 'text-purple-400' },
  overflow: { label: 'overflow rejected', className: 'text-red-400' },
  elastic: { label: 'elastic budget', className: 'text-yellow-400' },
  continuity: { label: 'continuity kept', className: 'text-emerald-400' },
  collapsed: { label: 'dup collapsed', className: 'text-sky-400' },
  wire: { label: 'wire hygiene', className: 'text-green-400' },
};

/** The status filters offered in the turn-list rail (a subset of STATUS_META). */
export const STATUS_FILTERS = ['all', 'gated', 'compacted', 'overflow', 'elastic'] as const;
export type StatusFilter = (typeof STATUS_FILTERS)[number];

export function statusMeta(flag: string): StatusMeta {
  return STATUS_META[flag] ?? { label: flag, className: 'text-muted-foreground' };
}

// ── gauge state ─────────────────────────────────────────────────────────────
export type GaugeState = 'under' | 'over-target' | 'over-ceiling';

/** Where compiled sits vs the soft target and the hard ceiling (window). Drives
 *  the gauge color: under-target (good) → over-target (warning) → over-ceiling (bad). */
export function gaugeState(
  compiled: number,
  target: number | null | undefined,
  ceiling: number | null | undefined,
): GaugeState {
  if (ceiling != null && compiled > ceiling) return 'over-ceiling';
  if (target != null && compiled > target) return 'over-target';
  return 'under';
}

// ── KPIs (session aggregate) ─────────────────────────────────────────────────
export interface InspectorKpis {
  /** Mean reduction % across turns that HAVE a raw baseline, 0–100. null = none. */
  avgReductionPct: number | null;
  /** Σ (raw − compiled) across turns that have a raw baseline. */
  tokensSaved: number;
  /** The model window (ceiling) from the latest turn, when known. */
  modelWindow: number | null;
  turnCount: number;
}

export function computeKpis(points: ContextTracePoint[]): InspectorKpis {
  let saved = 0;
  const reductions: number[] = [];
  for (const p of points) {
    const raw = p.frame.raw_tokens;
    if (raw != null && raw > 0) {
      saved += Math.max(0, raw - p.frame.used_tokens);
      if (p.frame.reduction_pct != null) reductions.push(p.frame.reduction_pct);
    }
  }
  const avg =
    reductions.length > 0
      ? (reductions.reduce((a, b) => a + b, 0) / reductions.length) * 100
      : null;
  const latest = points[points.length - 1]?.frame;
  return {
    avgReductionPct: avg,
    tokensSaved: saved,
    modelWindow: latest?.context_length ?? null,
    turnCount: points.length,
  };
}

// ── turn-list filter/search ───────────────────────────────────────────────────
/** Filter by status flag + free-text over the user message and intent. Case-
 *  insensitive. `all` status keeps everything. */
export function filterTurns(
  points: ContextTracePoint[],
  status: StatusFilter,
  query: string,
): ContextTracePoint[] {
  const q = query.trim().toLowerCase();
  return points.filter((p) => {
    if (status !== 'all' && !(p.frame.status_flags ?? []).includes(status)) return false;
    if (q) {
      const hay = `${p.user_message ?? ''} ${p.frame.intent ?? ''}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

/** Per-turn reduction %, 0–100, or null when there's no raw baseline. */
export function turnReductionPct(frame: ContextTraceFrame): number | null {
  return frame.reduction_pct != null ? frame.reduction_pct * 100 : null;
}

// ── compile-trace filter ──────────────────────────────────────────────────────
export type TraceFilter = 'all' | 'planner' | 'compiler' | 'saved';

export function filterSpans(spans: TraceSpanFrame[], filter: TraceFilter): TraceSpanFrame[] {
  if (filter === 'planner') return spans.filter((s) => s.phase === 'planner');
  if (filter === 'compiler') return spans.filter((s) => s.phase === 'compiler');
  if (filter === 'saved') return spans.filter((s) => s.delta < 0);
  return spans;
}

/** A span's delta color intent: saved (good), included (warning), reject (bad),
 *  neutral. The renderer maps these to concrete classes. */
export function spanDeltaKind(span: TraceSpanFrame): 'saved' | 'included' | 'reject' | 'neutral' {
  if (span.is_error) return 'reject';
  if (span.delta < 0) return 'saved';
  if (span.delta > 0) return 'included';
  return 'neutral';
}

/** Compact number format: 12345 → "12.3K". */
export function kfmt(n: number): string {
  const a = Math.abs(n);
  if (a >= 10000) return `${Math.round(n / 1000)}K`;
  if (a >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}
