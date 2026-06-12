import { useTranslation } from 'react-i18next';

interface Props {
  spentUsd: string;
  budgetUsd: string | null;
}

/** S6 (view) — spend vs budget. With a cap: a filled bar + amounts; uncapped: the
 *  running spend only. Bar turns amber/red as spend nears/exceeds the cap. */
export function SpentBudgetBar({ spentUsd, budgetUsd }: Props) {
  const { t } = useTranslation('campaigns');
  const spent = Number(spentUsd);

  if (!budgetUsd) {
    return (
      <div className="text-sm">
        <span className="text-muted-foreground">{t('monitor.spent', { defaultValue: 'Spent' })}: </span>
        <span className="font-medium">${spent.toFixed(4)}</span>
        <span className="text-muted-foreground"> · {t('monitor.uncapped', { defaultValue: 'uncapped' })}</span>
      </div>
    );
  }

  const budget = Number(budgetUsd);
  const pct = budget > 0 ? Math.min(100, (spent / budget) * 100) : 0;
  const tone = pct >= 100 ? 'bg-destructive' : pct >= 80 ? 'bg-amber-500' : 'bg-primary';

  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between text-sm">
        <span className="text-muted-foreground">{t('monitor.budget', { defaultValue: 'Budget' })}</span>
        <span className="font-medium">${spent.toFixed(4)} / ${budget.toFixed(2)}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div className={`h-full ${tone}`} style={{ width: `${pct}%` }} role="progressbar"
          aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} />
      </div>
    </div>
  );
}
