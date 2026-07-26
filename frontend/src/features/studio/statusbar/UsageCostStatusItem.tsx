// #11 F2 / W1-8 — last-24h spend meter on the studio status bar (the Cursor-style ambient cost
// readout). Reads the existing usage summary endpoint; refreshes on an interval so a long writing
// session with background jobs doesn't show a stale number. Live per-session spend is out of
// scope this wave (spec 11).
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CircleDollarSign } from 'lucide-react';
import { useAuth } from '@/auth';
import { usageApi } from '@/features/usage/api';
import { useStudioHost } from '../host/StudioHostProvider';
import { getStudioPanelDef } from '../panels/catalog';

const REFRESH_MS = 5 * 60_000;

export function formatUsd(cost: number): string {
  if (cost > 0 && cost < 0.01) return '<$0.01';
  return `$${cost.toFixed(2)}`;
}

export function UsageCostStatusItem() {
  const { t } = useTranslation('studio');
  const { accessToken } = useAuth();
  const host = useStudioHost();
  const [cost, setCost] = useState<number | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    let mounted = true;
    const load = () => {
      usageApi.getSummary(accessToken, 'last_24h')
        .then((s) => { if (mounted) setCost(s.total_cost_usd); })
        .catch(() => { /* meter is cosmetic; panel shows the truth */ });
    };
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => { mounted = false; clearInterval(timer); };
  }, [accessToken]);

  const openPanel = () => {
    const def = getStudioPanelDef('usage');
    host.openPanel('usage', {
      title: def ? t(def.titleKey, { defaultValue: 'Usage' }) : undefined,
    });
  };

  return (
    <button
      type="button"
      data-testid="studio-status-usage"
      onClick={openPanel}
      title={t('status.cost24h', { defaultValue: 'Spend, last 24h' })}
      className="inline-flex items-center gap-1 rounded px-1 py-0.5 font-mono hover:bg-secondary hover:text-foreground"
    >
      <CircleDollarSign className="h-3 w-3" />
      {cost === null ? '—' : formatUsd(cost)}
    </button>
  );
}
