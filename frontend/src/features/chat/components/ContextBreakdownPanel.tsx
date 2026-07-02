import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Archive, ChevronDown, ChevronRight, Loader2, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { CompactControls } from '../hooks/useCompactSession';
import type { ContextBudget, MemoryKnowledgeBreakdown } from '../types';

// Chat Quality Wave W2 — the /context-style drill-down panel behind a click on
// the ContextMeter chip. Pure render + a pure exported math helper (unit-
// tested directly): a horizontal stacked bar (one colored segment per non-zero
// category, sized against the effective limit when known so free space is
// visible) + per-category rows (label · tokens · % of used), the knowledge
// section sub-split, a zero-category one-liner, baseline / free-space lines
// and the auto-compact threshold marker.

/** Fixed category order — mirrors chat-service token_budget.BREAKDOWN_CATEGORIES. */
export const BREAKDOWN_CATEGORIES = [
  'system_prompt',
  'memory_knowledge',
  'working_memory',
  'steering',
  'skills',
  'plan_nudge',
  'book_note',
  'attached_context',
  'history',
  'tool_results',
  'frontend_tool_schemas',
  'mcp_tool_schemas',
] as const;

export type BreakdownCategory = (typeof BREAKDOWN_CATEGORIES)[number];

// One stable color per category (bar segment + row dot). Distinct hues so
// adjacent segments read apart; values are Tailwind palette classes.
const CATEGORY_COLORS: Record<BreakdownCategory, string> = {
  system_prompt: 'bg-amber-400',
  memory_knowledge: 'bg-emerald-400',
  working_memory: 'bg-teal-400',
  steering: 'bg-rose-400',
  skills: 'bg-violet-400',
  plan_nudge: 'bg-fuchsia-400',
  book_note: 'bg-lime-400',
  attached_context: 'bg-orange-400',
  history: 'bg-sky-400',
  tool_results: 'bg-cyan-400',
  frontend_tool_schemas: 'bg-indigo-400',
  mcp_tool_schemas: 'bg-blue-400',
};

// Categories whose row gets a "manage" action (opens the tool/skill modal).
const MANAGEABLE: ReadonlySet<BreakdownCategory> = new Set([
  'skills',
  'frontend_tool_schemas',
  'mcp_tool_schemas',
] as BreakdownCategory[]);

export interface BreakdownRow {
  key: BreakdownCategory;
  tokens: number;
  /** % of used_tokens, 0–100 (one decimal is left to the renderer). */
  pctOfUsed: number;
  /** memory_knowledge only — the per-section split from knowledge-service. */
  sections?: Record<string, number>;
}

export interface BreakdownComputation {
  /** Non-zero categories, fixed vocabulary order. */
  rows: BreakdownRow[];
  /** Zero categories (collapsed to a one-liner in the panel). */
  zeros: BreakdownCategory[];
  usedTokens: number;
  /** effective_limit ?? context_length — null when the model is unregistered. */
  limitTokens: number | null;
  /** limit − used; null when the limit is unknown. */
  freeTokens: number | null;
  /** The auto-compact trigger position as a 0–1 fraction of the limit
   *  (pct + until_compact_pct); null when either half is unknown. */
  compactAtFraction: number | null;
}

/** Extract the flat token count of one category (memory_knowledge nests). */
function categoryTokens(value: number | MemoryKnowledgeBreakdown | undefined): number {
  if (value == null) return 0;
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  return Number.isFinite(value.total) ? value.total : 0;
}

/** Pure math for the panel — exported so tests assert the percentages /
 *  zero-collapse / free-space directly without rendering. */
export function computeBreakdown(budget: ContextBudget): BreakdownComputation {
  const breakdown = budget.breakdown ?? {};
  const used = budget.used_tokens;
  const rows: BreakdownRow[] = [];
  const zeros: BreakdownCategory[] = [];
  for (const key of BREAKDOWN_CATEGORIES) {
    const raw = breakdown[key];
    const tokens = categoryTokens(raw);
    if (tokens <= 0) {
      zeros.push(key);
      continue;
    }
    const sections =
      key === 'memory_knowledge' && raw && typeof raw === 'object' && raw.sections
        ? raw.sections
        : undefined;
    rows.push({
      key,
      tokens,
      pctOfUsed: used > 0 ? (tokens / used) * 100 : 0,
      ...(sections && Object.keys(sections).length > 0 ? { sections } : {}),
    });
  }
  const limit = budget.effective_limit ?? budget.context_length ?? null;
  const free = limit != null ? Math.max(0, limit - used) : null;
  const compactAt =
    budget.pct != null && budget.until_compact_pct != null
      ? Math.min(1, budget.pct + budget.until_compact_pct)
      : null;
  return {
    rows,
    zeros,
    usedTokens: used,
    limitTokens: limit,
    freeTokens: free,
    compactAtFraction: compactAt,
  };
}

interface Props {
  budget: ContextBudget;
  /** Opens the tool/skill manager (the rack's add modal). Omitted on surfaces
   *  without the rack — the manage action is hidden then. */
  onManageTools?: () => void;
  /** W3 — the "Compact now" controls (useCompactSession). Omitted on surfaces
   *  without a compactable session — the section is hidden then. */
  compact?: CompactControls;
}

export function ContextBreakdownPanel({ budget, onManageTools, compact }: Props) {
  const { t } = useTranslation('chat');
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [instructions, setInstructions] = useState('');
  const c = computeBreakdown(budget);

  // Bar segments are sized against the LIMIT when known (free space stays
  // visible + the compact marker has a meaningful position); against used
  // tokens otherwise (segments fill the bar).
  const barDenominator = c.limitTokens ?? (c.usedTokens > 0 ? c.usedTokens : 1);

  return (
    <div
      data-testid="context-breakdown-panel"
      className="absolute right-0 top-full z-20 mt-1 w-72 rounded-md border border-border bg-card p-3 text-left shadow-lg"
    >
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <span className="text-xs font-semibold text-foreground">{t('context_panel.title')}</span>
        <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
          {c.usedTokens.toLocaleString()}
          {c.limitTokens != null ? ` / ${c.limitTokens.toLocaleString()}` : ''} tok
        </span>
      </div>

      {/* Stacked bar + auto-compact threshold marker */}
      <div className="relative mb-3 flex h-2 w-full overflow-hidden rounded-full bg-secondary" data-testid="context-breakdown-bar">
        {c.rows.map((row) => (
          <div
            key={row.key}
            title={`${t(`context_panel.cat.${row.key}`)} · ${row.tokens.toLocaleString()}`}
            className={cn('h-full', CATEGORY_COLORS[row.key])}
            style={{ width: `${Math.max(0.75, (row.tokens / barDenominator) * 100)}%` }}
          />
        ))}
        {c.compactAtFraction != null && c.limitTokens != null && (
          <div
            data-testid="context-compact-marker"
            title={t('context_panel.compact_at', { pct: Math.round(c.compactAtFraction * 100) })}
            className="absolute top-0 h-full w-0.5 bg-destructive/80"
            style={{ left: `${c.compactAtFraction * 100}%` }}
          />
        )}
      </div>

      {/* Category rows */}
      <div className="flex flex-col gap-1">
        {c.rows.map((row) => (
          <div key={row.key} className="min-w-0">
            <div className="flex items-center gap-1.5 text-[11px]">
              <span className={cn('h-2 w-2 shrink-0 rounded-sm', CATEGORY_COLORS[row.key])} />
              {row.key === 'memory_knowledge' && row.sections ? (
                <button
                  type="button"
                  onClick={() => setMemoryOpen((v) => !v)}
                  data-testid="context-row-memory-toggle"
                  className="flex min-w-0 items-center gap-0.5 truncate text-foreground hover:text-accent"
                >
                  {memoryOpen ? <ChevronDown className="h-3 w-3 shrink-0" /> : <ChevronRight className="h-3 w-3 shrink-0" />}
                  <span className="truncate">{t(`context_panel.cat.${row.key}`)}</span>
                </button>
              ) : (
                <span className="min-w-0 truncate text-foreground">{t(`context_panel.cat.${row.key}`)}</span>
              )}
              {MANAGEABLE.has(row.key) && onManageTools && (
                <button
                  type="button"
                  onClick={onManageTools}
                  data-testid={`context-manage-${row.key}`}
                  title={t('context_panel.manage')}
                  className="rounded p-0.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
                >
                  <Plus className="h-3 w-3" />
                </button>
              )}
              {row.key === 'steering' && (
                // Steering panel arrives in a later wave — honest placeholder.
                <span className="text-[9px] text-muted-foreground/70">{t('context_panel.coming_soon')}</span>
              )}
              <span className="ml-auto shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground">
                {row.tokens.toLocaleString()} · {row.pctOfUsed >= 10 ? Math.round(row.pctOfUsed) : row.pctOfUsed.toFixed(1)}%
              </span>
            </div>
            {row.key === 'memory_knowledge' && row.sections && memoryOpen && (
              <div className="ml-5 mt-0.5 flex flex-col gap-0.5" data-testid="context-memory-sections">
                {Object.entries(row.sections)
                  .filter(([, v]) => v > 0)
                  .sort(([, a], [, b]) => b - a)
                  .map(([name, tokens]) => (
                    <div key={name} className="flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
                      <span className="truncate">{name}</span>
                      <span className="font-mono tabular-nums">{tokens.toLocaleString()}</span>
                    </div>
                  ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Zero categories — one-liner instead of 12 empty rows */}
      {c.zeros.length > 0 && (
        <p className="mt-1.5 truncate text-[10px] text-muted-foreground/70" data-testid="context-zero-line" title={c.zeros.map((k) => t(`context_panel.cat.${k}`)).join(', ')}>
          · {t('context_panel.zero')}: {c.zeros.map((k) => t(`context_panel.cat.${k}`)).join(', ')}
        </p>
      )}

      {/* Baseline / free / compact-threshold footer */}
      <div className="mt-2 flex flex-col gap-0.5 border-t border-border pt-1.5 text-[10px] text-muted-foreground">
        {budget.baseline_tokens != null && (
          <span data-testid="context-baseline-line">
            {t('header.context_meter.baseline', { tokens: budget.baseline_tokens.toLocaleString() })}
          </span>
        )}
        {c.freeTokens != null && (
          <span data-testid="context-free-line">
            {t('context_panel.free', { tokens: c.freeTokens.toLocaleString() })}
          </span>
        )}
        {budget.until_compact_pct != null && (
          <span data-testid="context-until-compact-line">
            {t('header.context_meter.until_compact', { pct: Math.round(budget.until_compact_pct * 100) })}
          </span>
        )}
      </div>

      {/* W3 — manual steerable compact: optional preserve-these instructions +
          the button; persisted server-side so every later turn (any device)
          loads the summary instead of the old turns. */}
      {compact && (
        <div className="mt-2 flex flex-col gap-1.5 border-t border-border pt-2" data-testid="context-compact-section">
          <input
            type="text"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            maxLength={500}
            placeholder={t('context_panel.compact.placeholder')}
            disabled={compact.pending}
            data-testid="context-compact-instructions"
            className="w-full rounded-md border border-border bg-background px-2 py-1 text-[11px] text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-50"
          />
          <button
            type="button"
            onClick={() => compact.onCompact(instructions)}
            disabled={compact.pending}
            data-testid="context-compact-now"
            className="flex items-center justify-center gap-1.5 rounded-md border border-border bg-secondary/60 px-2 py-1 text-[11px] font-medium text-foreground transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {compact.pending
              ? <Loader2 className="h-3 w-3 animate-spin" />
              : <Archive className="h-3 w-3" />}
            {compact.pending ? t('context_panel.compact.pending') : t('context_panel.compact.button')}
          </button>
          {compact.compactedBeforeSeq != null && (
            <span className="text-[10px] text-muted-foreground" data-testid="context-compacted-through">
              {/* compacted_before_seq = first KEPT message → compacted THROUGH the one before it */}
              {t('context_panel.compact.compacted_through', { seq: compact.compactedBeforeSeq - 1 })}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
