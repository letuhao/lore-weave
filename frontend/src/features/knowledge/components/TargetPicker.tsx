import { useTranslation } from 'react-i18next';
import type { ExtractionTarget } from '../api';
import {
  ALL_TARGETS,
  entitiesExplicitlyRequested,
  isAutoIncluded,
} from '../lib/targetPicker';

// C12 — build-wizard Step-1 target picker. A controlled checkbox group over
// the extraction taxonomy. The dependent-auto-include + recovery/filter
// disable behaviour is surfaced as read-only hints (the BE/SDK enforce it);
// `entities` renders checked+disabled when a dependent target implies it.
interface Props {
  selected: ExtractionTarget[];
  onChange: (next: ExtractionTarget[]) => void;
}

export function TargetPicker({ selected, onChange }: Props) {
  const { t } = useTranslation('knowledge');

  const toggle = (target: ExtractionTarget) => {
    const set = new Set(selected);
    if (set.has(target)) set.delete(target);
    else set.add(target);
    // Preserve canonical order so the posted array is deterministic.
    onChange(ALL_TARGETS.filter((x) => set.has(x)));
  };

  const recoveryDisabled =
    selected.length > 0 && !entitiesExplicitlyRequested(selected);

  return (
    <fieldset className="flex flex-col gap-1" data-testid="build-target-picker">
      <legend className="text-xs font-medium text-muted-foreground">
        {t('projects.buildDialog.targets.label')}
      </legend>
      <div className="flex flex-col gap-1.5 pt-1">
        {ALL_TARGETS.map((target) => {
          const auto = isAutoIncluded(target, selected);
          const checked = selected.includes(target) || auto;
          return (
            <label key={target} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={checked}
                disabled={auto}
                onChange={() => toggle(target)}
                data-testid={`build-target-${target}`}
                aria-label={t(`projects.buildDialog.targets.${target}`)}
              />
              <span>{t(`projects.buildDialog.targets.${target}`)}</span>
              {auto && (
                <span
                  className="text-[10px] text-muted-foreground"
                  title={t('projects.buildDialog.targets.autoIncludedHint')}
                >
                  ({t('projects.buildDialog.targets.autoIncluded')})
                </span>
              )}
            </label>
          );
        })}
      </div>
      <span className="text-[11px] text-muted-foreground">
        {t('projects.buildDialog.targets.hint')}
      </span>
      {recoveryDisabled && (
        <span
          className="text-[11px] text-muted-foreground"
          data-testid="build-target-recovery-disabled"
        >
          {t('projects.buildDialog.targets.recoveryDisabledHint')}
        </span>
      )}
    </fieldset>
  );
}
