// LOOM Composition · Q3 Book-level promise coverage (view) — read-only, in the Quality dashboard.
//
// Answers "does the finished book pay off what the outline promised?": a stable promise set
// derived from the outline spec, scored over the whole book — paid / progressing / abandoned /
// absent, with the ABANDONED ones (introduced then dropped) called out. Diagnostic only.
import { useTranslation } from 'react-i18next';

import { useBookPromiseCoverage } from '../hooks/useBookPromiseCoverage';

interface Props {
  projectId: string;
  token: string | null;
  modelRef: string;
}

export function BookPromiseCoverageSection({ projectId, token, modelRef }: Props) {
  const { t } = useTranslation('composition');
  const q = useBookPromiseCoverage(projectId, token, modelRef);
  const c = q.coverage;
  const abandoned = c?.coverage.filter((p) => p.verdict === 'abandoned') ?? [];

  return (
    <div data-testid="composition-promise-coverage" className="mt-3 flex flex-col gap-2 border-t border-neutral-100 pt-3 dark:border-neutral-800">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-neutral-600 dark:text-neutral-300">
          {t('coverageTitle', { defaultValue: 'Story promises' })}
        </span>
        <button
          type="button"
          data-testid="coverage-run"
          disabled={!modelRef || q.loading}
          onClick={() => q.run()}
          className="rounded bg-sky-600 px-2 py-1 text-[11px] text-white disabled:opacity-50"
        >
          {q.loading
            ? t('coverageLoading', { defaultValue: 'Analyzing whole book…' })
            : q.ran
              ? t('coverageRerun', { defaultValue: 'Re-analyze' })
              : t('coverageRun', { defaultValue: 'Analyze story promises' })}
        </button>
      </div>
      <p className="text-[11px] text-neutral-400">
        {t('coverageIntro', {
          defaultValue: 'Advisory — which promises the outline sets up get paid off across the whole book. Read-only.',
        })}
      </p>

      {q.error && <div data-testid="coverage-error" className="text-[11px] text-amber-600">{q.error}</div>}

      {c?.error && (
        <span data-testid="coverage-na" className="text-[11px] text-neutral-400">
          {t('coverageNa', { defaultValue: 'Promise coverage unavailable.' })}
        </span>
      )}

      {c && !c.error && (
        <div className="flex flex-col gap-1" data-testid="coverage-body">
          <div className="flex flex-wrap gap-2" data-testid="coverage-counts">
            <Chip cls="bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
              {t('coveragePaid', { defaultValue: 'paid {{n}}', n: c.paid_count })}
            </Chip>
            <Chip cls="bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300">
              {t('coverageProgressing', { defaultValue: 'progressing {{n}}', n: c.progressing_count })}
            </Chip>
            <Chip cls="bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">
              {t('coverageAbandoned', { defaultValue: 'abandoned {{n}}', n: c.abandoned_count })}
            </Chip>
            <Chip cls="bg-neutral-100 text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400">
              {t('coverageAbsent', { defaultValue: 'absent {{n}}', n: c.absent_count })}
            </Chip>
          </div>

          {abandoned.length > 0 ? (
            <>
              <span className="text-[11px] font-medium text-rose-600">
                {t('coverageDropped', { defaultValue: 'Promised but abandoned:' })}
              </span>
              <ul className="flex flex-col gap-0.5">
                {abandoned.map((p, i) => (
                  <li key={i} className="text-[11px] text-rose-500">• {p.promise}</li>
                ))}
              </ul>
            </>
          ) : (
            q.ran && c.tracked_count > 0 && (
              <span className="text-[11px] text-emerald-600">{t('coverageClean', { defaultValue: 'No abandoned promises — the book pays off its setups.' })}</span>
            )
          )}
          {q.ran && c.tracked_count === 0 && (
            <span className="text-[11px] text-neutral-400">{t('coverageNoPromises', { defaultValue: 'No trackable promises found in the outline.' })}</span>
          )}
        </div>
      )}
    </div>
  );
}

function Chip({ cls, children }: { cls: string; children: React.ReactNode }) {
  return <span className={`rounded px-1.5 py-0.5 text-[10px] ${cls}`}>{children}</span>;
}
