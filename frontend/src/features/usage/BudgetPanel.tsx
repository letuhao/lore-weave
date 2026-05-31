// Phase 6a-γ — the spend-guardrail budget panel. Shows the user's daily +
// monthly USD limits vs spend, lets them edit the limits, and shows the
// read-only platform balance (free tier + credits). Render-only — logic
// lives in useBudget.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pencil } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useBudget } from './useBudget';

function usd(n: number): string {
  return `$${n.toFixed(2)}`;
}

// LimitRow renders one window (daily / monthly): a usage bar of
// (spent + reserved) against the limit.
function LimitRow({
  label,
  limit,
  spent,
  reserved,
}: {
  label: string;
  limit: number;
  spent: number;
  reserved: number;
}) {
  const used = spent + reserved;
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  const over = used > limit;
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono">
          {usd(used)} <span className="text-muted-foreground">/ {usd(limit)}</span>
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded bg-secondary">
        <div
          className={cn('h-full rounded', over ? 'bg-destructive' : 'bg-primary')}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function BudgetPanel() {
  const { t } = useTranslation('usage');
  const { guardrail, platform, loading, saving, saveLimits } = useBudget();
  const [editing, setEditing] = useState(false);
  const [dailyInput, setDailyInput] = useState('');
  const [monthlyInput, setMonthlyInput] = useState('');

  if (loading) {
    return (
      <div className="rounded-lg border bg-card p-4 text-xs text-muted-foreground">
        {t('budget.loading')}
      </div>
    );
  }
  if (!guardrail) return null;

  function startEdit() {
    if (!guardrail) return;
    setDailyInput(String(guardrail.daily_limit_usd));
    setMonthlyInput(String(guardrail.monthly_limit_usd));
    setEditing(true);
  }

  const invalid = !(Number(dailyInput) > 0) || !(Number(monthlyInput) > 0);

  async function handleSave() {
    if (invalid) return;
    const ok = await saveLimits(Number(dailyInput), Number(monthlyInput));
    if (ok) setEditing(false);
  }

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">{t('budget.spend_guardrail')}</h2>
        {!editing && (
          <button
            onClick={startEdit}
            className="flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
          >
            <Pencil className="h-3 w-3" /> {t('budget.edit_limits')}
          </button>
        )}
      </div>

      {!editing ? (
        <div className="mt-3 space-y-3">
          <LimitRow
            label={t('budget.daily')}
            limit={guardrail.daily_limit_usd}
            spent={guardrail.daily_spent_usd}
            reserved={guardrail.reserved_usd}
          />
          <LimitRow
            label={t('budget.monthly')}
            limit={guardrail.monthly_limit_usd}
            spent={guardrail.monthly_spent_usd}
            reserved={guardrail.reserved_usd}
          />
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          <label className="block text-xs">
            <span className="text-muted-foreground">{t('budget.daily_limit_usd')}</span>
            <input
              type="number"
              min="0"
              step="0.01"
              value={dailyInput}
              onChange={(e) => setDailyInput(e.target.value)}
              className="mt-0.5 w-full rounded border bg-background px-2 py-1 font-mono text-xs"
            />
          </label>
          <label className="block text-xs">
            <span className="text-muted-foreground">{t('budget.monthly_limit_usd')}</span>
            <input
              type="number"
              min="0"
              step="0.01"
              value={monthlyInput}
              onChange={(e) => setMonthlyInput(e.target.value)}
              className="mt-0.5 w-full rounded border bg-background px-2 py-1 font-mono text-xs"
            />
          </label>
          {invalid && (
            <p className="text-[10px] text-destructive">{t('budget.limits_invalid')}</p>
          )}
          <div className="flex gap-2 pt-1">
            <button
              onClick={handleSave}
              disabled={saving || invalid}
              className="rounded bg-primary px-3 py-1 text-xs font-medium text-primary-foreground transition-opacity disabled:opacity-50"
            >
              {saving ? t('budget.saving') : t('budget.save')}
            </button>
            <button
              onClick={() => setEditing(false)}
              disabled={saving}
              className="rounded border px-3 py-1 text-xs transition-colors hover:bg-secondary"
            >
              {t('budget.cancel')}
            </button>
          </div>
        </div>
      )}

      {/* Subsystem B — platform balance (LoreWeave-funded; read-only). */}
      {platform && (
        <div className="mt-4 border-t pt-3">
          <div className="text-[11px] text-muted-foreground">{t('budget.platform_balance')}</div>
          <div className="mt-1 flex items-baseline justify-between text-xs">
            <span className="text-muted-foreground">{t('budget.free_tier')}</span>
            <span className="font-mono">
              {usd(platform.free_tier_used_usd)}{' '}
              <span className="text-muted-foreground">
                / {usd(platform.free_tier_allowance_usd)}
              </span>
            </span>
          </div>
          <div className="mt-1 flex items-baseline justify-between text-xs">
            <span className="text-muted-foreground">{t('budget.credits')}</span>
            <span className="font-mono">{usd(platform.credits_balance_usd)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
