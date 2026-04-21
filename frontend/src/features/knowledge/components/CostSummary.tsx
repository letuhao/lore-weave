import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { FormDialog } from '@/components/shared';
import { useAuth } from '@/auth';
import { cn } from '@/lib/utils';
import { knowledgeApi, type UserCostSummary } from '../api';
import { useUserCosts } from '../hooks/useUserCosts';
import { formatUSD } from '../lib/formatUSD';

// K19b.6 — user-wide AI-spending card. Placed at the top of
// ExtractionJobsTab. Surfaces: this-month spend, all-time spend, and
// (when set) the monthly budget cap with a progress bar. The "Edit
// budget" button opens an inline FormDialog that calls
// PUT /v1/knowledge/me/budget.
//
// BE caveat carried over from K16.12 handoff: until D-K16.11-01
// wires record_spending into the extraction worker, `current_month`
// stays at 0 even as jobs succeed — the card renders correctly but
// figures lag reality. Not this cycle's scope.

// Matches the BE router's Field(ge=0) + server-side Decimal precision.
// Regex enforces non-negative, optional decimal with up to 4 fraction
// digits. Empty string is a valid "clear the cap" signal.
const DECIMAL_REGEX = /^\d+(\.\d{1,4})?$/;

// ── CostSummary card ────────────────────────────────────────────────

export function CostSummary() {
  const { t } = useTranslation('knowledge');
  const { costs, isLoading, error } = useUserCosts();
  const [editOpen, setEditOpen] = useState(false);

  if (isLoading) {
    return (
      <div
        className="rounded-lg border bg-card p-4"
        data-testid="cost-summary-loading"
      >
        <p className="text-[12px] text-muted-foreground">
          {t('jobs.costSummary.loading')}
        </p>
      </div>
    );
  }

  if (error || !costs) {
    return (
      <div
        role="alert"
        className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-[12px] text-destructive"
        data-testid="cost-summary-error"
      >
        {t('jobs.costSummary.loadFailed')}
        {error && <span className="ml-2 text-destructive/80">{error.message}</span>}
      </div>
    );
  }

  const hasBudget = costs.monthly_budget_usd !== null;
  const budgetNum = hasBudget ? Number(costs.monthly_budget_usd) : null;
  const currentNum = Number(costs.current_month_usd);
  const pct =
    hasBudget && budgetNum != null && budgetNum > 0
      ? Math.min(100, Math.max(0, (currentNum / budgetNum) * 100))
      : 0;
  const barColor =
    pct >= 100
      ? 'bg-destructive'
      : pct >= 80
        ? 'bg-amber-500'
        : 'bg-primary';

  return (
    <div
      className="rounded-lg border bg-card p-4"
      data-testid="cost-summary"
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('jobs.costSummary.title')}
        </h3>
        <button
          type="button"
          onClick={() => setEditOpen(true)}
          className="text-[11px] text-primary hover:underline"
          data-testid="cost-summary-edit"
        >
          {t('jobs.costSummary.editBudget')}
        </button>
      </div>
      <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-[13px]">
        <dt className="text-muted-foreground">
          {t('jobs.costSummary.thisMonth')}
        </dt>
        <dd className="font-medium" data-testid="cost-summary-month">
          {formatUSD(costs.current_month_usd)}
        </dd>
        <dt className="text-muted-foreground">
          {t('jobs.costSummary.allTime')}
        </dt>
        <dd className="font-medium" data-testid="cost-summary-alltime">
          {formatUSD(costs.all_time_usd)}
        </dd>
        {hasBudget && (
          <>
            <dt className="text-muted-foreground">
              {t('jobs.costSummary.budget')}
            </dt>
            <dd className="font-medium" data-testid="cost-summary-budget">
              {formatUSD(costs.monthly_budget_usd)}
            </dd>
          </>
        )}
      </dl>
      {hasBudget && (
        <div className="mt-3 space-y-1">
          <div
            className="relative h-1.5 w-full overflow-hidden rounded-full bg-muted"
            role="progressbar"
            aria-valuenow={Math.round(pct)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={t('jobs.costSummary.title')}
            data-testid="cost-summary-bar"
            data-pct={Math.round(pct)}
          >
            <div
              className={cn('h-full transition-all', barColor)}
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="text-[11px] text-muted-foreground">
            {t('jobs.costSummary.remaining', {
              remaining: formatUSD(costs.monthly_remaining_usd ?? '0'),
            })}
          </p>
        </div>
      )}
      {editOpen && (
        <EditBudgetDialog
          onClose={() => setEditOpen(false)}
          currentBudget={costs.monthly_budget_usd}
        />
      )}
    </div>
  );
}

// ── inline EditBudgetDialog ─────────────────────────────────────────

interface EditBudgetDialogProps {
  onClose: () => void;
  currentBudget: string | null;
}

function EditBudgetDialog({ onClose, currentBudget }: EditBudgetDialogProps) {
  const { t } = useTranslation('knowledge');
  const { accessToken, user } = useAuth();
  const queryClient = useQueryClient();
  const userId = user?.user_id ?? 'anon';
  const [value, setValue] = useState<string>(currentBudget ?? '');
  const [saving, setSaving] = useState(false);

  const trimmed = value.trim();
  // Empty = clear the cap; otherwise the regex must match.
  const isValid = trimmed === '' || DECIMAL_REGEX.test(trimmed);

  const handleSave = async () => {
    if (saving || !accessToken || !isValid) return;
    setSaving(true);
    try {
      await knowledgeApi.setUserBudget(
        { ai_monthly_budget_usd: trimmed === '' ? null : trimmed },
        accessToken,
      );
      await queryClient.invalidateQueries({
        queryKey: ['knowledge-costs', userId],
      });
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(t('jobs.costSummary.saveFailed', { error: msg }));
    } finally {
      setSaving(false);
    }
  };

  return (
    <FormDialog
      open={true}
      onOpenChange={(o) => {
        if (!o && !saving) onClose();
      }}
      title={t('jobs.costSummary.dialog.title')}
      description={t('jobs.costSummary.dialog.description')}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t('jobs.costSummary.dialog.cancel')}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !isValid}
            className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="cost-summary-save"
          >
            {saving
              ? t('jobs.costSummary.dialog.saving')
              : t('jobs.costSummary.dialog.save')}
          </button>
        </>
      }
    >
      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">
          {t('jobs.costSummary.dialog.label')}
        </span>
        <input
          type="text"
          inputMode="decimal"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="0.00"
          aria-invalid={!isValid}
          className="rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring aria-[invalid=true]:border-destructive"
          data-testid="cost-summary-input"
        />
        <span className="text-[11px] text-muted-foreground">
          {t('jobs.costSummary.dialog.hint')}
        </span>
        {!isValid && (
          <span className="text-[11px] text-destructive">
            {t('jobs.costSummary.invalid')}
          </span>
        )}
      </label>
    </FormDialog>
  );
}

export type { UserCostSummary };
