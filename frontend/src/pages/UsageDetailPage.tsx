import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { aiModelsApi } from '@/features/ai-models/api';

export function UsageDetailPage() {
  const { accessToken } = useAuth();
  const { usageLogId = '' } = useParams();
  const [detail, setDetail] = useState<{
    usage_log: { provider_kind: string; request_status: string; total_tokens: number; billing_decision: string };
    input_payload: Record<string, unknown>;
    output_payload: Record<string, unknown>;
    viewed_at: string;
  } | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const run = async () => {
      if (!accessToken || !usageLogId) return;
      try {
        const res = await aiModelsApi.getUsageLogDetail(accessToken, usageLogId);
        setDetail(res);
      } catch (e) {
        setError((e as Error).message);
      }
    };
    void run();
  }, [accessToken, usageLogId]);

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold">Usage detail</h1>
        <Link to="/m03/usage" className="text-sm underline">
          Back to usage logs
        </Link>
      </div>
      {detail && (
        <div className="space-y-3">
          <div className="rounded border p-3 text-sm">
            <p>
              Provider: <strong>{detail.usage_log.provider_kind}</strong>
            </p>
            <p>Status: {detail.usage_log.request_status}</p>
            <p>
              Tokens: {detail.usage_log.total_tokens} | Billing decision: {detail.usage_log.billing_decision}
            </p>
            <p className="text-muted-foreground">Viewed at: {detail.viewed_at}</p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <pre className="overflow-auto rounded border p-3 text-xs">{JSON.stringify(detail.input_payload, null, 2)}</pre>
            <pre className="overflow-auto rounded border p-3 text-xs">{JSON.stringify(detail.output_payload, null, 2)}</pre>
          </div>
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
