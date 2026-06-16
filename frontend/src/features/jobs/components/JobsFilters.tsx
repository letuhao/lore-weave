import { useTranslation } from 'react-i18next';

// Known kinds across services (open-ended; the list still shows any kind). Values
// match the projection's `kind` column so the BE filter is exact.
const KINDS = ['extraction', 'glossary_extraction', 'translation', 'composition.generate', 'video_gen', 'campaign', 'enrichment_job'];

/** Filter bar (view): a kind select + a WIDENED search box (title · kind · service ·
 *  model · job ID — debounced upstream). Status is owned by the summary-card
 *  quick-filters, so it's deliberately not duplicated here. */
export function JobsFilters({
  kind,
  onKind,
  q,
  onQ,
}: {
  kind: string;
  onKind: (next: string) => void;
  q: string;
  onQ: (next: string) => void;
}) {
  const { t } = useTranslation('jobs');
  const sel = 'rounded-lg border bg-input px-2.5 py-1.5 text-sm outline-none focus:border-ring';

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <select
          className={sel}
          value={kind}
          onChange={(e) => onKind(e.target.value)}
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
          className={`${sel} min-w-[12rem] flex-1`}
          value={q}
          onChange={(e) => onQ(e.target.value)}
          placeholder={t('filters.searchWide', {
            defaultValue: 'Search title, kind, service, model or job ID…',
          })}
          aria-label={t('filters.searchWide', { defaultValue: 'Search jobs' })}
        />
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        {t('filters.searchHint', {
          defaultValue: 'Search spans title · kind · service · model · job ID (debounced).',
        })}
      </p>
    </div>
  );
}
