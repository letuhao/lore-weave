import { useTranslation } from 'react-i18next';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { UsageSummary } from './types';

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

type TrendDirection = 'up' | 'down' | 'flat';
type TrendSentiment = 'positive' | 'negative' | 'neutral';

function computeTrend(current: number, previous: number): { direction: TrendDirection; pct: number } {
  if (previous === 0) return { direction: current > 0 ? 'up' : 'flat', pct: 0 };
  const pct = ((current - previous) / previous) * 100;
  if (Math.abs(pct) < 0.5) return { direction: 'flat', pct: 0 };
  return { direction: pct > 0 ? 'up' : 'down', pct: Math.abs(pct) };
}

type StatCardProps = {
  label: string;
  value: string;
  valueColor?: string;
  sub?: string;
  trend?: { direction: TrendDirection; pct: number; sentiment: TrendSentiment };
};

function StatCard({ label, value, valueColor, sub, trend }: StatCardProps) {
  const { t } = useTranslation('usage');
  return (
    <div className="rounded-lg border bg-card p-4 transition-colors hover:border-border/80">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={cn('mt-1 font-mono text-xl font-bold', valueColor)}>{value}</div>
      {trend && trend.direction !== 'flat' && (
        <div
          className={cn(
            'mt-1 flex items-center gap-1 text-[10px]',
            trend.sentiment === 'positive' && 'text-green-500',
            trend.sentiment === 'negative' && 'text-destructive',
            trend.sentiment === 'neutral' && 'text-muted-foreground',
          )}
        >
          {trend.direction === 'up' ? (
            <TrendingUp className="h-2.5 w-2.5" />
          ) : (
            <TrendingDown className="h-2.5 w-2.5" />
          )}
          {trend.direction === 'up' ? '+' : '-'}{trend.pct.toFixed(1)}% {t('stats.vs_prev_period')}
        </div>
      )}
      {trend && trend.direction === 'flat' && trend.pct === 0 && (
        <div className="mt-1 text-[10px] text-muted-foreground">{t('stats.no_prev_data')}</div>
      )}
      {sub && <div className="mt-0.5 text-[10px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

type Props = {
  summary: UsageSummary | null;
  periodLabel: string;
};

export function StatCards({ summary, periodLabel }: Props) {
  const { t } = useTranslation('usage');
  if (!summary) {
    return (
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-lg border bg-card" />
        ))}
      </div>
    );
  }

  const tokenTrend = computeTrend(summary.total_tokens, summary.prev_total_tokens);
  const costTrend = computeTrend(summary.total_cost_usd, summary.prev_total_cost_usd);
  const callsTrend = computeTrend(summary.request_count, summary.prev_request_count);
  const errorTrend = computeTrend(summary.error_rate, summary.prev_error_rate);

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatCard
        label={t('stats.total_tokens', { period: periodLabel })}
        value={formatTokens(summary.total_tokens)}
        valueColor="text-primary"
        trend={{ ...tokenTrend, sentiment: tokenTrend.direction === 'up' ? 'negative' : 'positive' }}
      />
      <StatCard
        label={t('stats.estimated_cost', { period: periodLabel })}
        value={`$${summary.total_cost_usd.toFixed(2)}`}
        trend={{ ...costTrend, sentiment: costTrend.direction === 'up' ? 'negative' : 'positive' }}
      />
      <StatCard
        label={t('stats.api_calls', { period: periodLabel })}
        value={String(summary.request_count)}
        valueColor="text-accent"
        trend={{ ...callsTrend, sentiment: 'neutral' }}
        sub={summary.request_count > 0 ? t('stats.avg_per_day', { n: Math.round(summary.request_count / 7) }) : undefined}
      />
      <StatCard
        label={t('stats.error_rate', { period: periodLabel })}
        value={`${summary.error_rate.toFixed(1)}%`}
        valueColor={summary.error_rate < 5 ? 'text-green-500' : 'text-destructive'}
        trend={{ ...errorTrend, sentiment: errorTrend.direction === 'up' ? 'negative' : 'positive' }}
        sub={t('stats.errors', { count: summary.error_count })}
      />
    </div>
  );
}
