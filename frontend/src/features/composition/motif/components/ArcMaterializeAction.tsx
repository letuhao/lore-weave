// W10 — the MATERIALIZE action (D-W10-APPLY-PLANNER-MATERIALIZE). Commits the arc onto
// THIS work's book (a real arc→chapter→scene outline + binding ledger), closing the loop
// from the apply-preview. Distinct from "Preview plan" (pure): this WRITES. A 409 (a
// chapter already has a plan) surfaces a "Replace existing" affordance; the result
// summarizes the committed tree + any unresolved / scale-folded motifs (§12.6).
import { useTranslation } from 'react-i18next';
import { useArcMaterialize } from '../hooks/useArcMaterialize';
import type { ArcTemplate } from '../arcTypes';

type Props = {
  arc: ArcTemplate;
  projectId: string;
  token: string | null;
  rosterBindings: Record<string, string>;
};

export function ArcMaterializeAction({ arc, projectId, token, rosterBindings }: Props) {
  const { t } = useTranslation('composition');
  const mat = useArcMaterialize(projectId, token);
  const result = mat.result;

  const run = (replace: boolean) =>
    mat.run({ arc_template_id: arc.id, roster_bindings: rosterBindings, replace });

  return (
    <div data-testid="arc-materialize-action" className="flex flex-col gap-2 border-t border-neutral-200 pt-2 dark:border-neutral-700">
      <p className="text-[11px] text-neutral-500">
        {t('motif.arc.materialize.blurb', {
          defaultValue: 'Commit this arc onto the current book — creates the chapters’ scene outline + motif bindings.',
        })}
      </p>

      {!result && (
        <button
          type="button"
          data-testid="arc-materialize-run"
          disabled={mat.isPending}
          className="self-start rounded bg-emerald-600 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          onClick={() => run(false)}
        >
          {mat.isPending
            ? t('motif.arc.materialize.running', { defaultValue: 'Materializing…' })
            : t('motif.arc.materialize.run', { defaultValue: 'Materialize to this book' })}
        </button>
      )}

      {mat.conflict && !result && (
        <div data-testid="arc-materialize-conflict" className="flex flex-col gap-1 rounded border border-amber-400 bg-amber-50 p-2 dark:border-amber-700 dark:bg-amber-900/20">
          <p className="text-[11px] text-amber-700 dark:text-amber-300">
            {t('motif.arc.materialize.conflict', { defaultValue: 'Some chapters already have a plan. Replace their scenes with this arc?' })}
          </p>
          <button
            type="button"
            data-testid="arc-materialize-replace"
            disabled={mat.isPending}
            className="self-start rounded border border-amber-500 px-2 py-0.5 text-[11px] text-amber-700 hover:bg-amber-100 disabled:opacity-50 dark:text-amber-300"
            onClick={() => run(true)}
          >
            {t('motif.arc.materialize.replace', { defaultValue: 'Replace existing scenes' })}
          </button>
        </div>
      )}

      {mat.isError && !mat.conflict && (
        <p role="alert" className="text-[11px] text-destructive">
          {t('motif.arc.materialize.error', { defaultValue: 'Could not materialize this arc.' })}
        </p>
      )}

      {result && (
        <div data-testid="arc-materialize-result" className="flex flex-col gap-1">
          <p className="text-[11px] font-medium text-emerald-700 dark:text-emerald-400">
            {t('motif.arc.materialize.done', {
              scenes: result.scenes_total, chapters: result.chapter_ids.length,
              defaultValue: 'Committed {{scenes}} scenes across {{chapters}} chapters.',
            })}
          </p>
          {result.unresolved_placements.length > 0 && (
            <p data-testid="arc-materialize-unresolved" className="text-[10px] text-amber-600">
              {t('motif.arc.materialize.unresolved', {
                count: result.unresolved_placements.length,
                defaultValue: '{{count}} motif(s) could not be resolved and were skipped.',
              })}
            </p>
          )}
          {result.drop_merge_report.length > 0 && (
            <p data-testid="arc-materialize-folded" className="text-[10px] text-amber-600">
              {t('motif.arc.materialize.folded', {
                count: result.drop_merge_report.length,
                defaultValue: '{{count}} motif(s) were folded by the chapter-count rescale.',
              })}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
