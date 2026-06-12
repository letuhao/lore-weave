// A3 planner (cycle 13; FD-15) — one editable scene row (render only; edits
// bubble to usePlanner via onEdit). FD-15: cast is now add/remove from the
// glossary roster, and an unresolved planner name that matches a roster entity
// can be resolved into the cast with one click.
import { useTranslation } from 'react-i18next';
import type { PlannerSceneDraft } from '../types';
import type { RosterOption } from '../hooks/useGlossaryRoster';

type Props = {
  scene: PlannerSceneDraft;
  index: number;
  unresolved: string[]; // present_entity_names_unresolved (display hint)
  roster: RosterOption[];
  onEdit: (patch: Partial<PlannerSceneDraft>) => void;
  onRemove: () => void;
};

export function PlannerSceneRow({ scene, index, unresolved, roster, onEdit, onRemove }: Props) {
  const { t } = useTranslation('composition');
  const labelFor = (id: string) => roster.find((o) => o.id === id)?.label ?? id;
  const inCast = new Set(scene.present_entity_ids);
  const addable = roster.filter((o) => !inCast.has(o.id));

  const addCast = (id: string) => {
    if (!id || inCast.has(id)) return;
    onEdit({ present_entity_ids: [...scene.present_entity_ids, id] });
  };
  const removeCast = (id: string) =>
    onEdit({ present_entity_ids: scene.present_entity_ids.filter((x) => x !== id) });
  // An unresolved name is resolvable if a roster entity shares its (case-insensitive) label.
  const resolveId = (name: string) =>
    roster.find((o) => o.label.toLowerCase() === name.trim().toLowerCase())?.id ?? null;

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

      {/* Cast chips (removable) + add-from-roster + resolvable unresolved names. */}
      <div className="flex flex-wrap items-center gap-1 text-xs" data-testid="planner-cast">
        <span className="text-muted-foreground">{t('plan.cast')}:</span>
        {scene.present_entity_ids.map((id) => (
          <span key={id} data-testid="planner-cast-chip" className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5">
            {labelFor(id)}
            <button
              type="button"
              className="text-muted-foreground hover:text-destructive"
              onClick={() => removeCast(id)}
              aria-label={t('plan.remove_cast', { name: labelFor(id) })}
            >
              ×
            </button>
          </span>
        ))}
        {addable.length > 0 && (
          <select
            data-testid="planner-cast-add"
            className="rounded border border-border bg-transparent px-1 py-0.5"
            value=""
            onChange={(e) => { addCast(e.target.value); e.currentTarget.value = ''; }}
            aria-label={t('plan.add_cast')}
          >
            <option value="">+ {t('plan.add_cast')}</option>
            {addable.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
        )}
      </div>
      {unresolved.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground" data-testid="planner-unresolved">
          {unresolved.map((name) => {
            const rid = resolveId(name);
            return rid ? (
              <button
                key={name}
                type="button"
                data-testid="planner-resolve"
                className="rounded border border-primary/40 px-1.5 py-0.5 text-primary hover:bg-primary/10"
                onClick={() => addCast(rid)}
                aria-label={t('plan.resolve', { name })}
                disabled={inCast.has(rid)}
              >
                + {name}
              </button>
            ) : (
              <span key={name} className="opacity-70">{name}?</span>
            );
          })}
        </div>
      )}
    </div>
  );
}
