import { TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { UsageSummary, AccountBalance } from './types';

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
          {trend.direction === 'up' ? '+' : '-'}{trend.pct.toFixed(1)}% vs prev period
        </div>
      )}
      {trend && trend.direction === 'flat' && trend.pct === 0 && (
        <div className="mt-1 text-[10px] text-muted-foreground">— no previous data</div>
      )}
      {sub && <div className="mt-0.5 text-[10px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

type Props = {
  summary: UsageSummary | null;
  balance: AccountBalance | null;
  periodLabel: string;
};

export function StatCards({ summary, balance, periodLabel }: Props) {
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
        label={`Total Tokens (${periodLabel})`}
        value={formatTokens(summary.total_tokens)}
        valueColor="text-primary"
        trend={{ ...tokenTrend, sentiment: tokenTrend.direction === 'up' ? 'negative' : 'positive' }}
        sub={balance ? `Quota remaining: ${formatTokens(balance.month_quota_remaining_tokens)}` : undefined}
      />
      <StatCard
        label={`Estimated Cost (${periodLabel})`}
        value={`$${summary.total_cost_usd.toFixed(2)}`}
        trend={{ ...costTrend, sentiment: costTrend.direction === 'up' ? 'negative' : 'positive' }}
        sub={balance ? `Credits: ${balance.credits_balance}` : undefined}
      />
      <StatCard
        label={`API Calls (${periodLabel})`}
        value={String(summary.request_count)}
        valueColor="text-accent"
        trend={{ ...callsTrend, sentiment: 'neutral' }}
        sub={summary.request_count > 0 ? `avg ${Math.round(summary.request_count / 7)}/day` : undefined}
      />
      <StatCard
        label={`Error Rate (${periodLabel})`}
        value={`${summary.error_rate.toFixed(1)}%`}
        valueColor={summary.error_rate < 5 ? 'text-green-500' : 'text-destructive'}
        trend={{ ...errorTrend, sentiment: errorTrend.direction === 'up' ? 'negative' : 'positive' }}
        sub={`${summary.error_count} errors`}
      />
    </div>
  );
}
