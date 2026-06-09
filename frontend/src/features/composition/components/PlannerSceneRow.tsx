// A3 planner (cycle 13) — one editable scene row (render only; edits bubble to
// usePlanner via onEdit). Cast is shown read-only (present_entity_ids flow
// through to commit unchanged); per-cast add/remove from the roster is a
// follow-up (needs the glossary roster, out of this slice).
import { useTranslation } from 'react-i18next';
import type { PlannerSceneDraft } from '../types';

type Props = {
  scene: PlannerSceneDraft;
  index: number;
  unresolved: string[]; // present_entity_names_unresolved (display hint)
  onEdit: (patch: Partial<PlannerSceneDraft>) => void;
  onRemove: () => void;
};

export function PlannerSceneRow({ scene, index, unresolved, onEdit, onRemove }: Props) {
  const { t } = useTranslation('composition');
  return (
    <div className="rounded border border-border p-2 space-y-1">
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">{index + 1}.</span>
        <input
          className="flex-1 bg-transparent text-sm font-medium outline-none"
          value={scene.title}
          onChange={(e) => onEdit({ title: e.target.value })}
          placeholder={t('plan.scene_title')}
          aria-label={t('plan.scene_title')}
        />
        <button
          type="button"
          className="min-h-[44px] min-w-[44px] text-muted-foreground hover:text-destructive"
          onClick={onRemove}
          aria-label={t('plan.remove_scene')}
        >
          ×
        </button>
      </div>
      <textarea
        className="w-full resize-y bg-transparent text-sm outline-none"
        rows={2}
        value={scene.synopsis}
        onChange={(e) => onEdit({ synopsis: e.target.value })}
        placeholder={t('plan.scene_synopsis')}
        aria-label={t('plan.scene_synopsis')}
      />
      <label className="flex items-center gap-2 text-xs">
        <span className="whitespace-nowrap">{t('plan.tension')}: {scene.tension ?? 0}</span>
        <input
          type="range"
          min={0}
          max={100}
          value={scene.tension ?? 0}
          onChange={(e) => onEdit({ tension: Number(e.target.value) })}
          aria-label={t('plan.tension')}
          className="flex-1"
        />
      </label>
      {(scene.present_entity_ids.length > 0 || unresolved.length > 0) && (
        <div className="text-xs text-muted-foreground">
          {t('plan.cast')}: {scene.present_entity_ids.length}
          {unresolved.length > 0 && <span className="opacity-70"> · {unresolved.join(', ')}?</span>}
        </div>
      )}
    </div>
  );
}
