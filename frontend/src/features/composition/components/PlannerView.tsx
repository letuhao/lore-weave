// A3 decompose planner (cycle 13) — the "Planner" sub-tab view (render only;
// logic in usePlanner). Flow: pick template + premise → preview the
// arc→chapter→scene tree → inline edit → commit (409 CHAPTER_ALREADY_PLANNED →
// inline replace-confirm). Mounted always-on (CSS-hidden) by CompositionPanel so
// a half-edited tree survives a tab switch (CLAUDE.md no-ternary-unmount rule).
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ModelPicker } from '@/components/model-picker';
import { usePlanner, type PlannerError } from '../hooks/usePlanner';
import { useGlossaryRoster } from '../hooks/useGlossaryRoster';
import { PlannerTree } from './PlannerTree';
import { CommittedSceneBindings } from '../motif/components/CommittedSceneBindings';

type Props = {
  projectId: string;
  bookId: string;
  modelRef: string;
  modelSource?: 'user_model' | 'platform_model';
  token: string | null;
  /** D-MOTIF-FE-PLANNERVIEW-WIRING (Shape A) — route a scene's commit→generate to the
   *  compose tab (the W2 seam: CompositionPanel wires selectTab('compose')+setSceneId).
   *  Optional: when absent the binding cards still swap/bind; only the generate link no-ops. */
  onSelectScene?: (sceneId: string) => void;
  /** S-13 — pre-select a structure template on mount (the studio DecomposePanel's deep-link from
   *  "Use in decompose"). Legacy callers omit it → unchanged. Seeds once (usePlanner lives inside
   *  this view, so the host cannot call setTemplateId itself); remount (a new key) re-seeds. */
  initialTemplateId?: string;
};

function errorText(e: PlannerError, t: (k: string) => string): string {
  if (e.code === 'NO_CHAPTERS') return t('plan.err_no_chapters');
  if (e.code === 'TOO_MANY_CHAPTERS') return t('plan.err_too_many_chapters');
  if (e.code === 'BAD_ENTITY') return t('plan.err_bad_entity');
  if (e.code === 'BAD_CHAPTER') return t('plan.err_bad_chapter');
  return e.message;
}

export function PlannerView({ projectId, bookId, modelRef, modelSource, token, onSelectScene, initialTemplateId }: Props) {
  const { t } = useTranslation('composition');
  const p = usePlanner(projectId, token);
  // S-13 — seed the deep-linked template once on mount (before any preview). A remount via a new
  // `key` (the host keys on the deep-link id) re-runs this for a fresh "Use in decompose".
  const setTemplateId = p.setTemplateId;
  useEffect(() => {
    if (initialTemplateId) setTemplateId(initialTemplateId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- seed once from the open-param, not on every setter identity change
  }, []);
  const templates = p.templates.data ?? [];
  const roster = useGlossaryRoster(bookId, token);
  const committedChapterIds = p.committedChapterIds ?? [];
  // FD-15 — planner-local model override. '' = inherit the panel's model. A
  // local pick is always a user_model (the picker lists the user's chat models).
  const [localModel, setLocalModel] = useState('');
  const effRef = localModel || modelRef;
  const effSource: 'user_model' | 'platform_model' = localModel ? 'user_model' : (modelSource ?? 'user_model');

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
          <div data-testid="planner-model-picker">
            <ModelPicker
              capability="chat"
              compact
              allowNone
              value={localModel || null}
              onChange={(id) => setLocalModel(id ?? '')}
              placeholder={t('plan.inherit_model')}
              ariaLabel={t('plan.model')}
            />
          </div>
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
            disabled={!p.templateId || !p.premise.trim() || !effRef || p.previewing}
            onClick={() => p.runPreview({ modelRef: effRef, modelSource: effSource })}
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
            roster={roster.data ?? []}
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

      {/* D-MOTIF-FE-PLANNERVIEW-WIRING (Shape A) — post-commit per-scene motif binding.
          Conditionally mounted (the committed-outline read lives in the child so it runs
          only after a commit, not on every render). */}
      {committedChapterIds.length > 0 && (
        <CommittedSceneBindings
          projectId={projectId}
          bookId={bookId}
          chapterIds={committedChapterIds}
          roster={roster.data ?? []}
          token={token}
          onDismiss={p.dismissCommitted}
          onSelectScene={onSelectScene}
        />
      )}
    </div>
  );
}
