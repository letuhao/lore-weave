// LOOM Composition · M6 Polish (view) — the self-heal review-gate.
//
// Runs the cheap-stack PROPOSE pass and shows each edit as an accept/reject row
// (deterministic pre-checked, semantic unchecked). The author accepts a subset; "Apply"
// hands the healed text to the editor — the imperfect pass NEVER writes silently.
import { useTranslation } from 'react-i18next';

import { usePolishProposals } from '../hooks/usePolishProposals';
import { QualityReportSection } from './QualityReportSection';

interface Props {
  projectId: string;
  chapterId: string;
  token: string | null;
  modelRef: string;
  // The healed text PLUS the draft_version Polish read it at (E1 stale guard): a chapter-scoped
  // apply uses it as the OCC If-Match, so a chapter changed since Polish ran gets a 412 instead of
  // silently reverting the newer edits. The legacy editor caller can ignore the 2nd arg (it applies
  // to the live editor on the same chapter).
  onApply: (healedText: string, draftVersion: number | null) => void;
}

export function PolishPanel({ projectId, chapterId, token, modelRef, onApply }: Props) {
  const { t } = useTranslation('composition');
  const p = usePolishProposals(projectId, chapterId, token, modelRef);

  return (
    <div data-testid="composition-polish" className="flex flex-col gap-2 p-3 text-sm">
      <p className="text-xs text-neutral-500">
        {t('polishIntro', {
          defaultValue:
            'Review proposed fixes before they touch your prose. Deterministic edits (pronouns, typos) are pre-selected; semantic edits are shown unchecked for you to judge.',
        })}
      </p>

      <div className="flex items-center gap-2">
        <button
          type="button"
          data-testid="polish-run"
          disabled={!modelRef || p.loading}
          onClick={() => p.run()}
          className="rounded bg-indigo-600 px-2 py-1 text-xs text-white disabled:opacity-50"
        >
          {p.loading
            ? t('polishLoading', { defaultValue: 'Analyzing…' })
            : p.ran
              ? t('polishRerun', { defaultValue: 'Re-run Polish' })
              : t('polishRun', { defaultValue: 'Run Polish' })}
        </button>
        <label className="flex items-center gap-1 text-[11px] text-neutral-500" title={t('polishRerankHint', { defaultValue: 'Uses one extra AI call per edit to auto-tick the good ones (slower, costs more).' })}>
          <input
            type="checkbox"
            data-testid="polish-rerank-toggle"
            checked={p.rerank}
            disabled={p.loading}
            onChange={(e) => p.setRerank(e.target.checked)}
          />
          {t('polishRerank', { defaultValue: 'auto-tick (AI, costs more)' })}
        </label>
        {!modelRef && (
          <span className="text-xs text-amber-600">
            {t('polishNoModel', { defaultValue: 'Pick a model first.' })}
          </span>
        )}
      </div>

      {p.error && <Hint>{p.error}</Hint>}

      {p.ran && p.stats && (
        <p data-testid="polish-stats" className="text-xs text-neutral-500">
          {t('polishStats', {
            defaultValue: '{{edits}} edits · {{refuted}} dropped by verify',
            edits: p.stats.edits,
            refuted: p.stats.refuted,
          })}
        </p>
      )}

      {p.ran && !p.loading && p.proposals.length === 0 && (
        <Hint>{t('polishClean', { defaultValue: 'No issues found — the prose is clean.' })}</Hint>
      )}

      {p.proposals.length > 0 && (
        <>
          <div className="flex gap-3 text-[11px] text-neutral-500">
            <button type="button" className="underline" onClick={() => p.bulk(true)}>
              {t('polishAll', { defaultValue: 'all' })}
            </button>
            <button type="button" className="underline" onClick={() => p.bulk(true, 'deterministic')}>
              {t('polishAllDet', { defaultValue: 'all deterministic' })}
            </button>
            <button type="button" className="underline" onClick={() => p.bulk(false)}>
              {t('polishClear', { defaultValue: 'clear' })}
            </button>
          </div>

          <ul className="flex flex-col gap-1">
            {p.proposals.map((e) => (
              <li
                key={e.id}
                data-testid={`polish-edit-${e.id}`}
                className="flex gap-2 rounded border border-neutral-100 p-1.5 dark:border-neutral-800"
              >
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={p.acceptedIds.has(e.id)}
                  onChange={() => p.toggle(e.id)}
                  aria-label={e.issue}
                />
                <div className="flex flex-col gap-0.5">
                  <div className="flex items-center gap-1 text-[10px]">
                    <span
                      className={
                        'rounded px-1 ' +
                        (e.tier === 'deterministic'
                          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
                          : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300')
                      }
                    >
                      {e.tier === 'deterministic'
                        ? t('polishDeterministic', { defaultValue: 'auto' })
                        : t('polishSemantic', { defaultValue: 'semantic' })}
                    </span>
                    <span className="text-neutral-400">{e.type}</span>
                  </div>
                  <div className="text-xs">
                    <span className="text-rose-500 line-through">{e.before}</span>{' '}
                    <span className="text-emerald-600">{e.after}</span>
                  </div>
                  {e.issue && <div className="text-[11px] text-neutral-500">{e.issue}</div>}
                </div>
              </li>
            ))}
          </ul>

          <button
            type="button"
            data-testid="polish-apply"
            disabled={p.acceptedIds.size === 0}
            onClick={() => onApply(p.healedText, p.draftVersion)}
            className="mt-1 self-start rounded bg-emerald-600 px-2 py-1 text-xs text-white disabled:opacity-50"
          >
            {t('polishApply', {
              defaultValue: 'Apply {{count}} selected',
              count: p.acceptedIds.size,
            })}
          </button>
        </>
      )}

      <QualityReportSection
        projectId={projectId}
        chapterId={chapterId}
        token={token}
        modelRef={modelRef}
        proposals={p.proposals}
      />
    </div>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return <div className="p-2 text-xs text-neutral-500">{children}</div>;
}
