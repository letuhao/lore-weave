import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Loader2 } from 'lucide-react';
import {
  BREAKDOWN_CATEGORIES,
  CATEGORY_HEX,
  type BreakdownCategory,
} from './ContextBreakdownPanel';
import type { ContextHistoryPoint, MemoryKnowledgeBreakdown } from '../types';

// W1-residual — the per-turn token HISTORY view of the breakdown panel. A
// recharts stacked bar per assistant turn (x = turn seq, y = tokens, one stack
// segment per non-zero category) reusing the live panel's category color map so
// the two views read as one. Pure render: useContextHistory owns the fetch.

/** Flatten one category's stored value (memory_knowledge nests {total,…}). */
function catTokens(value: number | MemoryKnowledgeBreakdown | undefined): number {
  if (value == null) return 0;
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  return Number.isFinite(value.total) ? value.total : 0;
}

interface ChartDatum {
  turn: number;
  total: number;
  [category: string]: number;
}

/** Map the series → recharts rows + the set of categories that are non-zero
 *  somewhere (so we don't render 12 empty stacks). Exported for unit test. */
export function buildChartData(points: ContextHistoryPoint[]): {
  data: ChartDatum[];
  activeCategories: BreakdownCategory[];
} {
  const present = new Set<BreakdownCategory>();
  const data: ChartDatum[] = points.map((p) => {
    const row: ChartDatum = { turn: p.sequence_num, total: 0 };
    for (const key of BREAKDOWN_CATEGORIES) {
      const tok = catTokens(p.breakdown?.[key]);
      row[key] = tok;
      row.total += tok;
      if (tok > 0) present.add(key);
    }
    return row;
  });
  const activeCategories = BREAKDOWN_CATEGORIES.filter((k) => present.has(k));
  return { data, activeCategories };
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

interface Props {
  points: ContextHistoryPoint[];
  loading: boolean;
  error: string | null;
}

export function ContextHistoryChart({ points, loading, error }: Props) {
  const { t } = useTranslation('chat');
  const { data, activeCategories } = useMemo(() => buildChartData(points), [points]);

  if (loading && points.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-muted-foreground" data-testid="context-history-loading">
        <Loader2 className="h-4 w-4 animate-spin" />
      </div>
    );
  }
  if (error) {
    return (
      <p className="py-6 text-center text-[11px] text-destructive" data-testid="context-history-error">
        {t('context_panel.history.error')}
      </p>
    );
  }
  if (data.length === 0) {
    return (
      <p className="py-6 text-center text-[11px] text-muted-foreground" data-testid="context-history-empty">
        {t('context_panel.history.empty')}
      </p>
    );
  }

  return (
    <div data-testid="context-history-chart">
      <div style={{ height: 160 }} className="w-full">
        <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
          <BarChart data={data} barCategoryGap={2}>
            <XAxis
              dataKey="turn"
              tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }}
              axisLine={false}
              tickLine={false}
              tickFormatter={formatTokens}
              width={34}
            />
            <Tooltip
              cursor={{ fill: 'hsl(var(--muted) / 0.15)' }}
              wrapperStyle={{ outline: 'none' }}
              content={<HistoryTooltip labelFor={(k) => t(`context_panel.cat.${k}`)} turnLabel={t('context_panel.history.turn')} totalLabel={t('context_panel.history.total')} />}
            />
            {activeCategories.map((key) => (
              <Bar key={key} dataKey={key} stackId="ctx" fill={CATEGORY_HEX[key]} isAnimationActive={false} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Legend — only the categories actually present in the series. */}
      <div className="mt-2 flex flex-wrap gap-x-2 gap-y-1" data-testid="context-history-legend">
        {activeCategories.map((key) => (
          <span key={key} className="flex items-center gap-1 text-[9px] text-muted-foreground">
            <span className="inline-block h-2 w-2 shrink-0 rounded-sm" style={{ background: CATEGORY_HEX[key] }} />
            {t(`context_panel.cat.${key}`)}
          </span>
        ))}
      </div>
    </div>
  );
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string; dataKey: string }>;
  label?: number | string;
  labelFor: (key: string) => string;
  turnLabel: string;
  totalLabel: string;
}

/** Per-turn hover: turn seq + total + each non-zero category's tokens. */
function HistoryTooltip({ active, payload, label, labelFor, turnLabel, totalLabel }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const rows = payload.filter((p) => (p.value ?? 0) > 0);
  const total = rows.reduce((sum, p) => sum + (p.value ?? 0), 0);
  return (
    <div className="rounded-md border border-border bg-card p-2 text-[10px] shadow-lg" data-testid="context-history-tooltip">
      <div className="mb-1 flex items-baseline justify-between gap-3 font-medium text-foreground">
        <span>{turnLabel} {label}</span>
        <span className="font-mono tabular-nums">{totalLabel}: {total.toLocaleString()}</span>
      </div>
      <div className="flex flex-col gap-0.5">
        {rows
          .sort((a, b) => (b.value ?? 0) - (a.value ?? 0))
          .map((p) => (
            <div key={p.dataKey} className="flex items-center justify-between gap-3 text-muted-foreground">
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded-sm" style={{ background: p.color }} />
                {labelFor(p.dataKey)}
              </span>
              <span className="font-mono tabular-nums">{(p.value ?? 0).toLocaleString()}</span>
            </div>
          ))}
      </div>
    </div>
  );
}
