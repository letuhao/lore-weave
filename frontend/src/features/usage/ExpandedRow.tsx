import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { usageApi } from './api';
import type { UsageLogDetail } from './types';

type Tab = 'input' | 'output' | 'raw';

type Props = {
  usageLogId: string;
  colSpan: number;
};

export function ExpandedRow({ usageLogId, colSpan }: Props) {
  const { t } = useTranslation('usage');
  const { accessToken } = useAuth();
  const [detail, setDetail] = useState<UsageLogDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState<Tab>('input');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    setLoading(true);
    usageApi
      .getLogDetail(accessToken, usageLogId)
      .then((d) => { if (!cancelled) setDetail(d); })
      .catch((e) => { if (!cancelled) setError((e as Error).message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [accessToken, usageLogId]);

  // Clean up copied timeout on unmount
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(timer);
  }, [copied]);

  function handleCopy(text: string) {
    navigator.clipboard.writeText(text).then(
      () => setCopied(true),
      () => { /* clipboard denied — fail silently, button stays as Copy */ },
    );
  }

  if (loading) {
    return (
      <tr>
        <td colSpan={colSpan} className="px-3 pb-3">
          <div className="h-32 animate-pulse rounded-md border bg-background" />
        </td>
      </tr>
    );
  }

  if (error || !detail) {
    return (
      <tr>
        <td colSpan={colSpan} className="px-3 pb-3">
          <div className="rounded-md border bg-background p-3 text-xs text-destructive">
            {error || t('detail.load_failed')}
          </div>
        </td>
      </tr>
    );
  }

  const { usage_log, input_payload, output_payload } = detail;

  const isEmpty = (v: unknown) => !v || (typeof v === 'object' && Object.keys(v as object).length === 0) || (typeof v === 'string' && (v === 'null' || v.includes('ciphertext')));

  const tabContent: Record<Tab, string> = {
    input: isEmpty(input_payload) ? t('detail.no_input') : JSON.stringify(input_payload, null, 2),
    output: isEmpty(output_payload) ? t('detail.no_output') : JSON.stringify(output_payload, null, 2),
    raw: JSON.stringify({ usage_log, input_payload, output_payload }, null, 2),
  };

  return (
    <tr>
      <td colSpan={colSpan} className="px-3 pb-3" style={{ background: 'rgba(232,168,50,0.02)' }}>
        <div className="overflow-hidden rounded-md border bg-background">
          {/* Request metadata */}
          <div className="flex flex-wrap gap-x-6 gap-y-1 border-b px-4 py-3 text-[11px]">
            <div>
              <span className="text-muted-foreground">{t('detail.request_id')} </span>
              <span className="font-mono text-muted-foreground">{usage_log.request_id.slice(0, 12)}</span>
            </div>
            <div>
              <span className="text-muted-foreground">{t('detail.provider')} </span>
              <span className="capitalize">{usage_log.provider_kind}</span>
            </div>
            <div>
              <span className="text-muted-foreground">{t('detail.model_ref')} </span>
              <span className="font-mono text-muted-foreground">{usage_log.model_ref.slice(0, 12)}</span>
            </div>
            <div>
              <span className="text-muted-foreground">{t('detail.billing')} </span>
              <span className="capitalize">{usage_log.billing_decision}</span>
            </div>
            <div>
              <span className="text-muted-foreground">{t('detail.viewed_at')} </span>
              <span>{detail.viewed_at}</span>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-0 border-b px-4" role="tablist" aria-label={t('detail.payload_view_aria')}>
            {(['input', 'output', 'raw'] as Tab[]).map((tabKey) => (
              <button
                key={tabKey}
                role="tab"
                aria-selected={tab === tabKey}
                onClick={() => setTab(tabKey)}
                className={cn(
                  'border-b-2 px-3 py-2 text-xs font-medium transition-colors',
                  tab === tabKey
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground',
                )}
              >
                {tabKey === 'input' ? t('detail.tab_input') : tabKey === 'output' ? t('detail.tab_output') : t('detail.tab_raw')}
              </button>
            ))}
            <div className="flex-1" />
            <button
              onClick={() => handleCopy(tabContent[tab])}
              aria-label={t('detail.copy_aria')}
              className="flex items-center gap-1 px-2 text-[10px] text-muted-foreground hover:text-foreground"
            >
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              {copied ? t('detail.copied') : t('detail.copy')}
            </button>
          </div>

          {/* Content */}
          <div className="max-h-52 overflow-auto p-4" role="tabpanel">
            <pre className="whitespace-pre-wrap break-all font-mono text-[11px] leading-relaxed text-secondary-foreground">
              {tabContent[tab]}
            </pre>
          </div>
        </div>
      </td>
    </tr>
  );
}
