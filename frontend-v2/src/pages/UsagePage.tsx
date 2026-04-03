import { useCallback, useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { usageApi } from '@/features/usage/api';
import { StatCards } from '@/features/usage/StatCards';
import { BreakdownPanels } from '@/features/usage/BreakdownPanels';
import { DailyChart } from '@/features/usage/DailyChart';
import { RequestLogTable } from '@/features/usage/RequestLogTable';
import type { UsageSummary, AccountBalance, UsageLog, UsageFilters, Period } from '@/features/usage/types';

const PERIODS: { value: Period; label: string }[] = [
  { value: 'last_24h', label: '24h' },
  { value: 'last_7d', label: '7d' },
  { value: 'last_30d', label: '30d' },
  { value: 'last_90d', label: '90d' },
];

function periodToDateRange(period: Period): { from?: string; to?: string } {
  const now = new Date();
  const ms: Record<Period, number> = {
    last_24h: 24 * 60 * 60 * 1000,
    last_7d: 7 * 24 * 60 * 60 * 1000,
    last_30d: 30 * 24 * 60 * 60 * 1000,
    last_90d: 90 * 24 * 60 * 60 * 1000,
  };
  return {
    from: new Date(now.getTime() - ms[period]).toISOString(),
    to: now.toISOString(),
  };
}

export function UsagePage() {
  const { accessToken } = useAuth();
  const [period, setPeriod] = useState<Period>('last_7d');
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [balance, setBalance] = useState<AccountBalance | null>(null);
  const [logs, setLogs] = useState<UsageLog[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(25);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<UsageFilters>({});
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  const periodLabel = PERIODS.find((p) => p.value === period)?.label ?? '7d';

  // Fetch summary + balance
  useEffect(() => {
    if (!accessToken) return;
    Promise.all([
      usageApi.getSummary(accessToken, period),
      usageApi.getBalance(accessToken),
    ]).then(([s, b]) => {
      setSummary(s);
      setBalance(b);
    }).catch(() => {});
  }, [accessToken, period]);

  // Fetch logs with server-side filters
  const fetchLogs = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const dateRange = periodToDateRange(period);
      const res = await usageApi.listLogs(accessToken, {
        limit,
        offset,
        ...filters,
        from: dateRange.from,
        to: dateRange.to,
      });
      setLogs(res.items ?? []);
      setTotal(res.total);
    } catch {
      setLogs([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [accessToken, period, limit, offset, filters]);

  useEffect(() => { void fetchLogs(); }, [fetchLogs]);

  // Client-side search (text filter on already-loaded page of logs)
  const filteredLogs = search.trim()
    ? logs.filter((l) => {
        const q = search.toLowerCase();
        return (
          l.provider_kind.toLowerCase().includes(q) ||
          l.purpose.toLowerCase().includes(q) ||
          l.model_ref.toLowerCase().includes(q) ||
          l.request_status.toLowerCase().includes(q)
        );
      })
    : logs;

  // CSV export
  function handleExportCSV() {
    const headers = ['Time', 'Status', 'Purpose', 'Provider', 'Input Tokens', 'Output Tokens', 'Cost USD', 'Billing', 'Request ID'];
    const rows = filteredLogs.map((l) => [
      l.created_at,
      l.request_status,
      l.purpose,
      l.provider_kind,
      l.input_tokens,
      l.output_tokens,
      l.total_cost_usd.toFixed(6),
      l.billing_decision,
      l.request_id,
    ]);
    const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `loreweave-usage-${period}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleFiltersChange(f: UsageFilters) {
    setFilters(f);
    setOffset(0);
  }

  return (
    <div className="mx-auto max-w-[1200px] space-y-6 px-6 py-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-serif text-xl font-semibold">AI Usage Monitor</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Track token usage, costs, and performance across all AI operations.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Period selector */}
          <div className="flex items-center gap-0.5 rounded-md bg-secondary p-0.5">
            {PERIODS.map((p) => (
              <button
                key={p.value}
                onClick={() => { setPeriod(p.value); setOffset(0); }}
                className={cn(
                  'rounded px-2.5 py-1 text-xs font-medium transition-colors',
                  period === p.value
                    ? 'bg-primary/15 text-primary'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
          <button
            onClick={handleExportCSV}
            className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary"
          >
            <Download className="h-3 w-3" />
            Export CSV
          </button>
        </div>
      </div>

      {/* Stat cards */}
      <StatCards summary={summary} balance={balance} periodLabel={periodLabel} />

      {/* Breakdown panels */}
      {summary && (
        <BreakdownPanels
          byProvider={summary.by_provider ?? []}
          byPurpose={summary.by_purpose ?? []}
          periodLabel={periodLabel}
        />
      )}

      {/* Daily chart */}
      {summary && <DailyChart data={summary.daily ?? []} />}

      {/* Request log table */}
      <RequestLogTable
        logs={filteredLogs}
        total={total}
        limit={limit}
        offset={offset}
        filters={filters}
        search={search}
        onSearchChange={setSearch}
        onFiltersChange={handleFiltersChange}
        onOffsetChange={setOffset}
        onLimitChange={setLimit}
      />
    </div>
  );
}
