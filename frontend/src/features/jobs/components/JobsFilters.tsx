import { useTranslation } from 'react-i18next';

import type { JobListParams, JobStatus } from '../types';

const STATUSES: JobStatus[] = [
  'pending', 'running', 'paused', 'cancelling', 'completed', 'failed', 'cancelled',
];
// Known kinds across services (open-ended; the list still shows any kind).
const KINDS = ['extraction', 'translation', 'composition.generate', 'video_gen', 'campaign', 'enrichment_job'];

/** Filter bar (view): status + kind selects + a title search. Controlled by the
 *  parent list, which owns the filter state and re-queries on change. */
export function JobsFilters({
  filters,
  onChange,
}: {
  filters: JobListParams;
  onChange: (next: JobListParams) => void;
}) {
  const { t } = useTranslation('jobs');
  const sel = 'rounded-md border bg-input px-2 py-1 text-sm outline-none focus:border-ring';

  return (
    <div className="flex flex-wrap items-center gap-2">
      <select
        className={sel}
        value={filters.status ?? ''}
        onChange={(e) => onChange({ ...filters, status: e.target.value as JobStatus | '' })}
        aria-label={t('filters.status', { defaultValue: 'Status' })}
      >
        <option value="">{t('filters.allStatuses', { defaultValue: 'All statuses' })}</option>
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {t(`status.${s}`, { defaultValue: s })}
          </option>
        ))}
      </select>

      <select
        className={sel}
        value={filters.kind ?? ''}
        onChange={(e) => onChange({ ...filters, kind: e.target.value })}
        aria-label={t('filters.kind', { defaultValue: 'Kind' })}
      >
        <option value="">{t('filters.allKinds', { defaultValue: 'All kinds' })}</option>
        {KINDS.map((k) => (
          <option key={k} value={k}>
            {t(`kind.${k}`, { defaultValue: k })}
          </option>
        ))}
      </select>

      <input
        className={`${sel} flex-1 min-w-[8rem]`}
        value={filters.q ?? ''}
        onChange={(e) => onChange({ ...filters, q: e.target.value })}
        placeholder={t('filters.search', { defaultValue: 'Search title…' })}
        aria-label={t('filters.search', { defaultValue: 'Search title…' })}
      />
    </div>
  );
}
