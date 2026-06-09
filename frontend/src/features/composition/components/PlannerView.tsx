// A3 decompose planner (cycle 13) — the "Planner" sub-tab view (render only;
// logic in usePlanner). Flow: pick template + premise → preview the
// arc→chapter→scene tree → inline edit → commit (409 CHAPTER_ALREADY_PLANNED →
// inline replace-confirm). Mounted always-on (CSS-hidden) by CompositionPanel so
// a half-edited tree survives a tab switch (CLAUDE.md no-ternary-unmount rule).
import { useTranslation } from 'react-i18next';
import { usePlanner, type PlannerError } from '../hooks/usePlanner';
import { PlannerTree } from './PlannerTree';

type Props = { projectId: string; modelRef: string; modelSource?: 'user_model' | 'platform_model'; token: string | null };

function errorText(e: PlannerError, t: (k: string) => string): string {
  if (e.code === 'NO_CHAPTERS') return t('plan.err_no_chapters');
  if (e.code === 'TOO_MANY_CHAPTERS') return t('plan.err_too_many_chapters');
  if (e.code === 'BAD_ENTITY') return t('plan.err_bad_entity');
  if (e.code === 'BAD_CHAPTER') return t('plan.err_bad_chapter');
  return e.message;
}

export function PlannerView({ projectId, modelRef, modelSource, token }: Props) {
  const { t } = useTranslation('composition');
  const p = usePlanner(projectId, token);
  const templates = p.templates.data ?? [];

  return (
    <div className="space-y-3" data-testid="planner-view">
      {!p.draft && (
        <div className="space-y-2">
          <select
            className="w-full rounded border border-border bg-background p-1 text-sm"
            value={p.templateId}
            onChange={(e) => p.setTemplateId(e.target.value)}
            aria-label={t('plan.template')}
          >
            <option value="">{t('plan.pick_template')}</option>
            {templates.map((tm) => <option key={tm.id} value={tm.id}>{tm.name}</option>)}
          </select>
          <textarea
            className="w-full resize-y rounded border border-border bg-background p-1 text-sm"
            rows={3}
            value={p.premise}
            onChange={(e) => p.setPremise(e.target.value)}
            placeholder={t('plan.premise')}
            aria-label={t('plan.premise')}
          />
          <button
            type="button"
            className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
            disabled={!p.templateId || !p.premise.trim() || !modelRef || p.previewing}
            onClick={() => p.runPreview({ modelRef, modelSource })}
          >
            {p.previewing ? t('plan.previewing') : t('plan.preview')}
          </button>
          {p.error && <div className="text-sm text-destructive" role="alert">{errorText(p.error, t)}</div>}
        </div>
      )}

      {p.draft && (
        <div className="space-y-3">
          {(p.preview?.unmapped_beats?.length ?? 0) > 0 && (
            <div className="text-xs text-amber-600">{t('plan.unmapped_beats')}: {p.preview!.unmapped_beats.join(', ')}</div>
          )}
          <PlannerTree
            draft={p.draft}
            preview={p.preview}
            onEditScene={p.editScene}
            onEditChapter={p.editChapter}
            onAddScene={p.addScene}
            onRemoveScene={p.removeScene}
          />
          {p.error && <div className="text-sm text-destructive" role="alert">{errorText(p.error, t)}</div>}
          {p.needsReplace && (
            <div className="rounded border border-amber-400 bg-amber-50 p-2 text-sm dark:bg-amber-950/30" role="alertdialog" aria-label={t('plan.replace_title')}>
              <p>{t('plan.replace_prompt', { count: p.needsReplace.length })}</p>
              <div className="mt-2 flex gap-2">
                <button type="button" className="rounded bg-amber-600 px-2 py-1 text-xs text-white disabled:opacity-50" onClick={p.confirmReplace} disabled={p.committing}>
                  {t('plan.replace_confirm')}
                </button>
                <button type="button" className="rounded border border-border px-2 py-1 text-xs" onClick={p.cancelReplace}>
                  {t('plan.cancel')}
                </button>
              </div>
            </div>
          )}
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
              disabled={p.committing || !!p.needsReplace}
              onClick={p.commit}
            >
              {p.committing ? t('plan.committing') : t('plan.commit')}
            </button>
            <span className="text-xs text-muted-foreground">{t('plan.scene_count', { count: p.totalScenes })}</span>
          </div>
        </div>
      )}
    </div>
  );
}
