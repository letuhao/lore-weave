import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/auth';
import { UsageLog, aiModelsApi } from '@/features/ai-models/api';

export function UsageLogsPage() {
  const { accessToken } = useAuth();
  const [items, setItems] = useState<UsageLog[]>([]);
  const [balance, setBalance] = useState<{
    tier_name: string;
    month_quota_tokens: number;
    month_quota_remaining_tokens: number;
    credits_balance: number;
  } | null>(null);
  const [summary, setSummary] = useState<{
    request_count: number;
    total_tokens: number;
    total_cost_usd: number;
  } | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const run = async () => {
      if (!accessToken) return;
      try {
        const [logs, balanceRes, summaryRes] = await Promise.all([
          aiModelsApi.listUsageLogs(accessToken, { limit: 50, offset: 0 }),
          aiModelsApi.getAccountBalance(accessToken),
          aiModelsApi.getUsageSummary(accessToken),
        ]);
        setItems(logs.items);
        setBalance(balanceRes);
        setSummary(summaryRes);
      } catch (e) {
        setError((e as Error).message);
      }
    };
    void run();
  }, [accessToken]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Usage logs</h1>
        <p className="text-sm text-muted-foreground">Inspect request-level usage, billing decision, and open encrypted detail by owner.</p>
      </div>
      {balance && (
        <div className="rounded border p-3 text-sm">
          <p>
            Tier: <strong>{balance.tier_name}</strong>
          </p>
          <p>
            Quota remaining: {balance.month_quota_remaining_tokens}/{balance.month_quota_tokens} tokens
          </p>
          <p>Credits: {balance.credits_balance}</p>
        </div>
      )}
      {summary && (
        <div className="rounded border p-3 text-sm">
          <p>Requests: {summary.request_count}</p>
          <p>Total tokens: {summary.total_tokens}</p>
          <p>Total cost (USD): {summary.total_cost_usd.toFixed(6)}</p>
        </div>
      )}
      <div className="space-y-2">
        {items.map((item) => (
          <Link key={item.usage_log_id} to={`/m03/usage/${item.usage_log_id}`} className="block rounded border p-3 text-sm hover:bg-accent">
            <p>
              <strong>{item.provider_kind}</strong> {item.model_source} {item.billing_decision}
            </p>
            <p className="text-muted-foreground">
              Tokens: {item.total_tokens} | Cost: {item.total_cost_usd.toFixed(6)} | Status: {item.request_status}
            </p>
          </Link>
        ))}
        {items.length === 0 && <p className="text-sm text-muted-foreground">No usage logs yet.</p>}
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
