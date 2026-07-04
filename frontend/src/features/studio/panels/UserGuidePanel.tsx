// #19 Wave 1 — catalog-driven User Guide. Content is generated entirely from STUDIO_PANELS
// metadata (title/desc/category) — the same source that already feeds the dock and the Command
// Palette (#18) — so there is no second, hand-authored doc surface to keep in sync: editing a
// panel's catalog entry is the only maintenance action this guide ever needs.
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { ExternalLink } from 'lucide-react';
import { useStudioPanel } from './useStudioPanel';
import { useStudioHost } from '../host/StudioHostProvider';
import { OPENABLE_STUDIO_PANELS, type StudioPanelDef } from './catalog';
import { CATEGORY_ORDER } from '../palette/useStudioCommands';

function groupByCategory(panels: StudioPanelDef[]): Array<[string, StudioPanelDef[]]> {
  const byCategory = new Map<string, StudioPanelDef[]>();
  for (const p of panels) {
    const key = p.category ?? 'platform';
    if (!byCategory.has(key)) byCategory.set(key, []);
    byCategory.get(key)!.push(p);
  }
  const ordered = CATEGORY_ORDER.filter((c) => byCategory.has(c));
  const rest = [...byCategory.keys()].filter((c) => !CATEGORY_ORDER.includes(c as (typeof CATEGORY_ORDER)[number]));
  return [...ordered, ...rest].map((c) => [c, byCategory.get(c)!]);
}

export function UserGuidePanel(props: IDockviewPanelProps) {
  useStudioPanel('user-guide', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const groups = groupByCategory(OPENABLE_STUDIO_PANELS);

  const openPanel = (def: StudioPanelDef) => {
    host.openPanel(def.id, { title: t(def.titleKey, { defaultValue: def.id }) });
  };

  return (
    <div data-testid="studio-user-guide-panel" className="h-full min-h-0 overflow-y-auto p-4">
      <p className="mb-4 text-sm text-muted-foreground">
        {t('userGuide.intro', {
          defaultValue: 'Every tool Writing Studio can open, grouped the same way as the Command Palette.',
        })}
      </p>
      <div className="space-y-6">
        {groups.map(([category, panels]) => (
          <section key={category} data-testid={`studio-user-guide-group-${category}`}>
            <h3 className="mb-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70">
              {t(`palette.group.${category}`, { defaultValue: category })}
            </h3>
            <ul className="space-y-1">
              {panels.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    data-testid={`studio-user-guide-open-${p.id}`}
                    onClick={() => openPanel(p)}
                    className="flex w-full items-start justify-between gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-secondary"
                  >
                    <span>
                      <span className="block text-sm font-medium text-foreground">
                        {t(p.titleKey, { defaultValue: p.id })}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {t(p.guideBodyKey ?? p.descKey, { defaultValue: '' })}
                      </span>
                    </span>
                    <ExternalLink className="mt-1 h-3.5 w-3.5 flex-shrink-0 text-muted-foreground/50" />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
