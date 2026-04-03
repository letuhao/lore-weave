import { TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { UsageSummary, AccountBalance } from './types';

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

type StatCardProps = {
  label: string;
  value: string;
  valueColor?: string;
  sub?: string;
};

function StatCard({ label, value, valueColor, sub }: StatCardProps) {
  return (
    <div className="rounded-lg border bg-card p-4 transition-colors hover:border-border/80">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={cn('mt-1 font-mono text-xl font-bold', valueColor)}>{value}</div>
      {sub && <div className="mt-1 text-[10px] text-muted-foreground">{sub}</div>}
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

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatCard
        label={`Total Tokens (${periodLabel})`}
        value={formatTokens(summary.total_tokens)}
        valueColor="text-primary"
        sub={balance ? `Quota remaining: ${formatTokens(balance.month_quota_remaining_tokens)}` : undefined}
      />
      <StatCard
        label={`Estimated Cost (${periodLabel})`}
        value={`$${summary.total_cost_usd.toFixed(2)}`}
        sub={balance ? `Credits: ${balance.credits_balance}` : undefined}
      />
      <StatCard
        label={`API Calls (${periodLabel})`}
        value={String(summary.request_count)}
        valueColor="text-accent"
        sub={summary.request_count > 0 ? `avg ${Math.round(summary.request_count / 7)}/day` : undefined}
      />
      <StatCard
        label={`Error Rate (${periodLabel})`}
        value={`${summary.error_rate.toFixed(1)}%`}
        valueColor={summary.error_rate < 5 ? 'text-green-500' : 'text-destructive'}
        sub={`${summary.error_count} errors`}
      />
    </div>
  );
}
