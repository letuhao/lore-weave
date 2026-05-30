// Phase 6a-γ — controller for the spend-guardrail budget panel. Owns the
// fetch of the guardrail (Subsystem A) + platform balance (Subsystem B) and
// the limit-update mutation; BudgetPanel renders.
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { usageApi } from './api';
import type { Guardrail, PlatformBalance } from './types';

export function useBudget() {
  const { t } = useTranslation('usage');
  const { accessToken } = useAuth();
  const [guardrail, setGuardrail] = useState<Guardrail | null>(null);
  const [platform, setPlatform] = useState<PlatformBalance | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      usageApi.getGuardrail(accessToken),
      usageApi.getPlatformBalance(accessToken),
    ])
      .then(([g, p]) => {
        if (cancelled) return;
        setGuardrail(g);
        setPlatform(p);
      })
      .catch(() => {
        if (!cancelled) toast.error(t('budget.load_failed'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  // saveLimits PATCHes the daily + monthly USD limits and folds the
  // server's authoritative response back into state. Returns true on success
  // so the caller can close its edit form.
  const saveLimits = useCallback(
    async (dailyLimit: number, monthlyLimit: number): Promise<boolean> => {
      if (!accessToken) return false;
      setSaving(true);
      try {
        const updated = await usageApi.patchGuardrail(accessToken, {
          daily_limit_usd: dailyLimit,
          monthly_limit_usd: monthlyLimit,
        });
        setGuardrail(updated);
        toast.success(t('budget.limits_updated'));
        return true;
      } catch {
        toast.error(t('budget.update_failed'));
        return false;
      } finally {
        setSaving(false);
      }
    },
    [accessToken],
  );

  return { guardrail, platform, loading, saving, saveLimits };
}
