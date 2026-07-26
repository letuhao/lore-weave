import { useTranslation } from 'react-i18next';
import type { ProviderBreakdown, PurposeBreakdown } from './types';
import { purposeColor } from './types';

const PROVIDER_COLORS: Record<string, string> = {
  anthropic: '#d4a574',
  openai: '#74c0a4',
  ollama: '#7ab4f0',
  lm_studio: '#a78bfa',
};

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  ollama: 'Ollama',
  lm_studio: 'LM Studio',
};

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

type Props = {
  byProvider: ProviderBreakdown[];
  byPurpose: PurposeBreakdown[];
  periodLabel: string;
};

export function BreakdownPanels({ byProvider, byPurpose, periodLabel }: Props) {
  const { t } = useTranslation('usage');
  const maxProviderTokens = Math.max(1, ...byProvider.map((p) => p.total_tokens));
  const maxPurposeTokens = Math.max(1, ...byPurpose.map((p) => p.total_tokens));

  return (
    <div className="grid gap-3 md:grid-cols-2">
      {/* By Provider */}
      <div className="overflow-hidden rounded-lg border bg-card">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <span className="text-sm font-semibold">{t('breakdown.tokens_by_provider')}</span>
          <span className="text-[10px] text-muted-foreground">{periodLabel}</span>
        </div>
        <div className="space-y-3 p-4">
          {byProvider.length === 0 && (
            <p className="text-xs text-muted-foreground">{t('breakdown.no_data')}</p>
          )}
          {byProvider.map((item) => (
            <div key={item.provider_kind} className="flex items-center gap-3">
              <span className="flex w-28 items-center gap-1.5 text-xs" style={{ color: PROVIDER_COLORS[item.provider_kind] }}>
                <span
                  className="inline-block h-2 w-2 rounded-sm"
                  style={{ background: PROVIDER_COLORS[item.provider_kind] }}
                />
                {PROVIDER_LABELS[item.provider_kind] ?? item.provider_kind}
              </span>
              <div className="flex-1">
                <div className="h-5 rounded-sm bg-secondary">
                  <div
                    className="h-full rounded-sm"
                    style={{
                      width: `${(item.total_tokens / maxProviderTokens) * 100}%`,
                      background: PROVIDER_COLORS[item.provider_kind] ?? '#888',
                    }}
                  />
                </div>
              </div>
              <span className="w-16 text-right font-mono text-[11px] text-muted-foreground">
                {formatTokens(item.total_tokens)}
              </span>
              <span className="w-14 text-right font-mono text-[10px] text-muted-foreground">
                ${item.total_cost_usd.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* By Purpose */}
      <div className="overflow-hidden rounded-lg border bg-card">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <span className="text-sm font-semibold">{t('breakdown.tokens_by_purpose')}</span>
          <span className="text-[10px] text-muted-foreground">{periodLabel}</span>
        </div>
        <div className="space-y-3 p-4">
          {byPurpose.length === 0 && (
            <p className="text-xs text-muted-foreground">{t('breakdown.no_data')}</p>
          )}
          {byPurpose.map((item) => (
            <div key={item.purpose} className="flex items-center gap-3">
              <span className="flex w-28 items-center gap-1.5 text-xs">
                <span
                  className="inline-block h-2 w-2 rounded-sm"
                  style={{ background: purposeColor(item.purpose) }}
                />
                {t(`purpose.${item.purpose}`, { defaultValue: item.purpose })}
              </span>
              <div className="flex-1">
                <div className="h-5 rounded-sm bg-secondary">
                  <div
                    className="h-full rounded-sm opacity-70"
                    style={{
                      width: `${(item.total_tokens / maxPurposeTokens) * 100}%`,
                      background: purposeColor(item.purpose),
                    }}
                  />
                </div>
              </div>
              <span className="w-16 text-right font-mono text-[11px] text-muted-foreground">
                {formatTokens(item.total_tokens)}
              </span>
              <span className="w-16 text-right text-[10px] text-muted-foreground">
                {t('breakdown.calls', { count: item.request_count })}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
