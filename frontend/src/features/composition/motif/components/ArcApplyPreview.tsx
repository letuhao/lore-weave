// W10 §12.5 — the apply-PREVIEW surface. Choose a target chapter count, bind the
// arc_roster slots, and preview the deterministic plan: rescaled placements per thread,
// the §12.6 drop/merge report (a motif lost to a scale mismatch is NEVER silent), and
// any unbound roster slots. Render-only against the plan; the controller owns the call.
// PREVIEW-ONLY by design — committing the plan to outline rows is the tracked follow-up
// D-W10-APPLY-PLANNER-MATERIALIZE.
import { useTranslation } from 'react-i18next';
import type { ArcTemplate } from '../arcTypes';
import { useArcApplyPreview } from '../hooks/useArcApplyPreview';

export function ArcApplyPreview({ arc, token }: { arc: ArcTemplate; token: string | null }) {
  const { t } = useTranslation('composition');
  const ctrl = useArcApplyPreview(arc.id, token, arc.chapter_span ?? 10);
  const plan = ctrl.plan;

  return (
    <div data-testid="arc-apply-preview" className="flex flex-col gap-2 rounded border border-neutral-200 p-2 dark:border-neutral-700">
      <h4 className="text-xs font-medium text-neutral-600 dark:text-neutral-300">
        {t('motif.arc.apply.title', { defaultValue: 'Apply to a new book (preview)' })}
      </h4>

      <label className="flex items-center gap-2 text-[11px] text-neutral-500">
        {t('motif.arc.apply.targetChapters', { defaultValue: 'Target chapters' })}
        <input
          type="number"
          min={1}
          data-testid="arc-apply-target"
          className="w-20 rounded border border-neutral-300 px-1.5 py-0.5 text-xs dark:border-neutral-600 dark:bg-neutral-800"
          value={ctrl.targetChapters}
          onChange={(e) => ctrl.setTargetChapters(Number(e.target.value))}
        />
      </label>

      {arc.arc_roster.length > 0 && (
        <fieldset className="flex flex-col gap-1">
          <legend className="text-[11px] text-neutral-500">{t('motif.arc.apply.roster', { defaultValue: 'Bind the cast (once for the whole arc)' })}</legend>
          {arc.arc_roster.map((r) => (
            <label key={r.key} className="flex items-center gap-2 text-[11px]">
              <span className="w-24 shrink-0 truncate text-neutral-500">{r.label || r.key}</span>
              <input
                data-testid={`arc-apply-roster-${r.key}`}
                className="min-w-0 flex-1 rounded border border-neutral-300 px-1.5 py-0.5 text-xs dark:border-neutral-600 dark:bg-neutral-800"
                value={ctrl.rosterBindings[r.key] ?? ''}
                onChange={(e) => ctrl.setBinding(r.key, e.target.value)}
              />
            </label>
          ))}
        </fieldset>
      )}

      <button
        type="button"
        data-testid="arc-apply-run"
        disabled={ctrl.isPending}
        className="self-start rounded bg-amber-600 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-amber-700 disabled:opacity-50"
        onClick={ctrl.run}
      >
        {ctrl.isPending
          ? t('motif.arc.apply.running', { defaultValue: 'Previewing…' })
          : t('motif.arc.apply.run', { defaultValue: 'Preview plan' })}
      </button>

      {ctrl.isError && (
        <p role="alert" className="text-[11px] text-destructive">{t('motif.arc.apply.error', { defaultValue: 'Could not build the apply preview.' })}</p>
      )}

      {plan && (
        <div data-testid="arc-apply-plan" className="flex flex-col gap-2 border-t border-neutral-200 pt-2 dark:border-neutral-700">
          <p className="text-[11px] text-neutral-500">
            {t('motif.arc.apply.rescaled', {
              from: plan.source_chapter_span, to: plan.target_chapters,
              defaultValue: 'Rescaled {{from}} → {{to}} chapters',
            })}
          </p>

          <ul className="flex flex-col gap-0.5">
            {plan.placements.map((p, i) => (
              <li key={`${p.thread}-${p.motif_code}-${i}`} data-testid="arc-apply-placement" className="flex items-center gap-2 text-[11px]">
                <span className="w-20 shrink-0 truncate text-neutral-400">{p.thread}</span>
                <span className="font-medium">{p.motif_code}</span>
                <span className="text-neutral-500">{t('motif.arc.chapters', { from: p.span_start, to: p.span_end, defaultValue: 'ch {{from}}-{{to}}' })}</span>
                {p.merged_codes.length > 0 && (
                  <span data-testid="arc-apply-merged" className="rounded bg-neutral-200 px-1 text-[10px] text-neutral-600 dark:bg-neutral-700 dark:text-neutral-300">
                    +{p.merged_codes.length}
                  </span>
                )}
              </li>
            ))}
          </ul>

          {plan.unbound_roster_keys.length > 0 && (
            <p data-testid="arc-apply-unbound" className="text-[11px] text-amber-600">
              {t('motif.arc.apply.unbound', { keys: plan.unbound_roster_keys.join(', '), defaultValue: 'Unbound roles: {{keys}}' })}
            </p>
          )}

          {plan.drop_merge_report.length > 0 && (
            <div data-testid="arc-apply-dropmerge" className="flex flex-col gap-0.5">
              <p className="text-[11px] font-medium text-amber-600">{t('motif.arc.apply.dropMerge', { defaultValue: 'Scale reconciliation' })}</p>
              {plan.drop_merge_report.map((d, i) => (
                <p key={i} className="text-[10px] text-neutral-500">
                  <span className="uppercase">{d.kind}</span> {d.motif_code}: {d.reason}
                </p>
              ))}
            </div>
          )}

          <p className="text-[10px] italic text-neutral-400">
            {t('motif.arc.apply.previewOnly', { defaultValue: 'Preview only — nothing is written yet. Committing the plan to chapters is coming soon.' })}
          </p>
        </div>
      )}
    </div>
  );
}
