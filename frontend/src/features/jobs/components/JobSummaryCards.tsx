import { useTranslation } from 'react-i18next';

import type { JobSummary } from '../types';
import type { QuickFilter } from '../hooks/useJobsDashboard';

const CARDS: { key: QuickFilter; labelKey: string; dot: string }[] = [
  { key: 'active', labelKey: 'summary.active', dot: 'bg-blue-500' },
  { key: 'completed', labelKey: 'summary.completed', dot: 'bg-green-500' },
  { key: 'failed', labelKey: 'summary.failed', dot: 'bg-destructive' },
  { key: 'cancelled', labelKey: 'summary.cancelled', dot: 'bg-muted-foreground' },
];

/** The 4 status-summary cards. Each is a quick-filter: clicking selects it (and the
 *  ring highlight), driving which table(s) the dashboard shows. */
export function JobSummaryCards({
  summary,
  selected,
  onSelect,
}: {
  summary: JobSummary | undefined;
  selected: QuickFilter;
  onSelect: (q: QuickFilter) => void;
}) {
  const { t } = useTranslation('jobs');
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {CARDS.map((c) => (
        <button
          key={c.key}
          type="button"
          onClick={() => onSelect(c.key)}
          aria-pressed={selected === c.key}
          className={`rounded-xl border bg-card p-3.5 text-left transition-colors hover:bg-accent/40 ${
            selected === c.key ? 'border-primary ring-1 ring-primary' : ''
          }`}
        >
          <div className="text-2xl font-semibold tabular-nums">{summary?.[c.key] ?? '—'}</div>
          <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className={`inline-block h-1.5 w-1.5 rounded-full ${c.dot}`} />
            {t(c.labelKey, { defaultValue: c.key })}
          </div>
        </button>
      ))}
    </div>
  );
}
