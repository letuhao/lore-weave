// A3 planner (cycle 13) — the editable arc→chapter→scene tree (render only).
// Chapters are fixed (mapped onto the book's existing chapters); scenes are
// add/remove/editable. Read-only hints (per-chapter warning, per-scene
// unresolved cast names) come from the original preview, index-aligned.
import { useTranslation } from 'react-i18next';
import type { DecomposePreview, PlannerChapterDraft, PlannerSceneDraft } from '../types';
import { PlannerSceneRow } from './PlannerSceneRow';

type Props = {
  draft: PlannerChapterDraft[];
  preview: DecomposePreview | null;
  onEditScene: (ci: number, si: number, patch: Partial<PlannerSceneDraft>) => void;
  onEditChapter: (ci: number, patch: Partial<Pick<PlannerChapterDraft, 'intent' | 'beat_role'>>) => void;
  onAddScene: (ci: number) => void;
  onRemoveScene: (ci: number, si: number) => void;
};

export function PlannerTree({ draft, preview, onEditScene, onEditChapter, onAddScene, onRemoveScene }: Props) {
  const { t } = useTranslation('composition');
  return (
    <div className="space-y-3">
      {draft.map((ch, ci) => {
        const warning = preview?.chapters[ci]?.warning ?? null;
        return (
          <div key={ch.chapter_id} className="rounded-md border border-border p-2 space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold">{ch.title || t('plan.untitled_chapter')}</span>
              {ch.beat_role && <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{ch.beat_role}</span>}
            </div>
            <input
              className="w-full bg-transparent text-xs text-muted-foreground outline-none"
              value={ch.intent}
              onChange={(e) => onEditChapter(ci, { intent: e.target.value })}
              placeholder={t('plan.chapter_intent')}
              aria-label={t('plan.chapter_intent')}
            />
            {warning && <div className="text-xs text-amber-600">⚠ {warning}</div>}
            <div className="space-y-2 pl-2">
              {ch.scenes.map((sc, si) => (
                <PlannerSceneRow
                  key={si}
                  scene={sc}
                  index={si}
                  unresolved={preview?.chapters[ci]?.scenes[si]?.present_entity_names_unresolved ?? []}
                  onEdit={(patch) => onEditScene(ci, si, patch)}
                  onRemove={() => onRemoveScene(ci, si)}
                />
              ))}
              <button
                type="button"
                className="text-xs text-primary hover:underline"
                onClick={() => onAddScene(ci)}
              >
                + {t('plan.add_scene')}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
