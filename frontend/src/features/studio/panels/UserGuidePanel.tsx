// #19 Wave 1 — catalog-driven User Guide. Content is generated entirely from STUDIO_PANELS
// metadata (title/desc/category) — the same source that already feeds the dock and the Command
// Palette (#18) — so there is no second, hand-authored doc surface to keep in sync: editing a
// panel's catalog entry is the only maintenance action this guide ever needs.
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { ExternalLink, Compass } from 'lucide-react';
import { useStudioPanel } from './useStudioPanel';
import { useStudioHost } from '../host/StudioHostProvider';
import { OPENABLE_STUDIO_PANELS, type StudioPanelDef } from './catalog';
import { CATEGORY_ORDER } from '../palette/useStudioCommands';
// From tourCatalog.ts specifically (NOT tours.ts) — tours.ts's role-tour steps call
// getStudioPanelDef from catalog.ts at module-init time, and catalog.ts imports THIS component,
// so importing tours.ts here would be a circular import. See tourCatalog.ts's header comment.
import { EDITOR_TOUR_CATALOG, COMPOSE_TOUR_CATALOG, RESEARCH_TOUR_CATALOG, PANEL_TOUR_IDS, type StudioTourCatalogEntry } from '../onboarding/tourCatalog';

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

/** One tour-catalog list (Editor or Composer) — same row shape as the panel-open rows below,
 *  distinguished by the Compass icon instead of ExternalLink. */
function TourList({ tours, onStart }: { tours: StudioTourCatalogEntry[]; onStart: (tourId: string) => void }) {
  const { t } = useTranslation('studio');
  return (
    <ul className="space-y-1">
      {tours.map((tour) => (
        <li key={tour.id}>
          <button
            type="button"
            data-testid={`studio-user-guide-tour-${tour.id}`}
            onClick={() => onStart(tour.id)}
            className="flex w-full items-start justify-between gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-secondary"
          >
            <span>
              <span className="block text-sm font-medium text-foreground">
                {t(tour.labelKey, { defaultValue: tour.id })}
              </span>
              <span className="block text-xs text-muted-foreground">
                {t(tour.descKey, { defaultValue: '' })}
              </span>
            </span>
            <Compass className="mt-1 h-3.5 w-3.5 flex-shrink-0 text-muted-foreground/50" />
          </button>
        </li>
      ))}
    </ul>
  );
}

const WORKFLOW_KEYS = ['setup', 'lore', 'factChecking', 'jobs', 'translation'] as const;

export function UserGuidePanel(props: IDockviewPanelProps) {
  useStudioPanel('user-guide', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const groups = groupByCategory(OPENABLE_STUDIO_PANELS);

  const openPanel = (def: StudioPanelDef) => {
    host.openPanel(def.id, { title: t(def.titleKey, { defaultValue: def.id }) });
  };

  // #19 Wave 3/4 — the editor + composer deep-dive tours (docs/specs/2026-07-06-editor-feature-
  // inventory.md, 2026-07-06-composer-feature-inventory.md) are grouped by feature topic rather
  // than one long walkthrough; this is their ONE discoverable entry point (the animated tour was
  // previously reachable only via the Command Palette shortcut, with no visible list of what
  // tours even exist).
  const startTour = (tourId: string) => host.publish({ type: 'startGuidedTour', tourId });

  return (
    <div data-testid="studio-user-guide-panel" className="h-full min-h-0 overflow-y-auto p-4">
      <p className="mb-4 text-sm text-muted-foreground">
        {t('userGuide.intro', {
          defaultValue: 'Every tool Writing Studio can open, grouped the same way as the Command Palette.',
        })}
      </p>
      <section data-testid="studio-user-guide-tours" className="mb-6 space-y-4">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70">
          {t('userGuide.toursGroup', { defaultValue: 'Guided tours' })}
        </h3>
        <div>
          <h4 className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/50">
            {t('userGuide.toursEditor', { defaultValue: 'Editor' })}
          </h4>
          <TourList tours={EDITOR_TOUR_CATALOG} onStart={startTour} />
        </div>
        <div>
          <h4 className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/50">
            {t('userGuide.toursComposer', { defaultValue: 'Composer' })}
          </h4>
          <TourList tours={COMPOSE_TOUR_CATALOG} onStart={startTour} />
        </div>
        <div>
          <h4 className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/50">
            {t('userGuide.toursResearch', { defaultValue: 'World research' })}
          </h4>
          <TourList tours={RESEARCH_TOUR_CATALOG} onStart={startTour} />
        </div>
      </section>
      <section data-testid="studio-user-guide-workflows" className="mb-6 space-y-3">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70">
          {t('userGuide.workflowsTitle', { defaultValue: 'Workflows and practices' })}
        </h3>
        {WORKFLOW_KEYS.map((key) => (
          <article key={key} className="rounded-md border border-border/60 bg-secondary/20 p-3">
            <h4 className="text-sm font-semibold text-foreground">{t(`userGuide.workflows.${key}.title`)}</h4>
            <p className="mt-1 text-xs text-muted-foreground">{t(`userGuide.workflows.${key}.body`)}</p>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground/80">{t(`userGuide.workflows.${key}.steps`)}</p>
          </article>
        ))}
      </section>
      <div className="space-y-6">
        {groups.map(([category, panels]) => (
          <section key={category} data-testid={`studio-user-guide-group-${category}`}>
            <h3 className="mb-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70">
              {t(`palette.group.${category}`, { defaultValue: category })}
            </h3>
            <ul className="space-y-1">
              {panels.map((p) => (
                <li key={p.id}>
                  <div className="flex items-start gap-1 rounded-md px-2 py-1.5 transition-colors hover:bg-secondary">
                    <button
                      type="button"
                      data-testid={`studio-user-guide-open-${p.id}`}
                      onClick={() => openPanel(p)}
                      className="flex min-w-0 flex-1 items-start justify-between gap-2 text-left"
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
                    {PANEL_TOUR_IDS[p.id]?.[0] && (
                      <button
                        type="button"
                        data-testid={`studio-user-guide-tour-for-${p.id}`}
                        aria-label={t('userGuide.startPanelTour', { defaultValue: 'Start panel tour' })}
                        title={t('userGuide.startPanelTour', { defaultValue: 'Start panel tour' })}
                        onClick={() => startTour(PANEL_TOUR_IDS[p.id]![0])}
                        className="mt-0.5 rounded p-1 text-muted-foreground/60 transition-colors hover:bg-primary/10 hover:text-primary"
                      >
                        <Compass className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
