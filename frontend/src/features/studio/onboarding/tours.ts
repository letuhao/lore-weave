// #19 Wave 1 — the `core` guided tour. Steps target LIVE DOM via already-existing, stable
// `data-testid`s on the chrome and dock panels (never a screenshot) — the exact same testids
// this repo's own E2E specs already assert on, so a tour step can't silently drift from what's
// actually rendered without an existing test also catching it.
//
// #19 Wave 2 — the 5 role-specific tours (writer/worldbuilder/translator/enricher/manager) pull
// their `target` from each panel's catalog `tourAnchor` (via `roleStep` below) instead of
// hardcoding the selector a second time here, per the spec's own G4 note that per-role tours
// "are expected to pull target from a catalog tourAnchor once there are enough of them to
// justify it" — `core`'s 4 hardcoded steps are unchanged (2 of them are chrome-only, no panel).
import { getStudioPanelDef } from '../panels/catalog';

export type StudioTourId = 'core' | 'writer' | 'worldbuilder' | 'translator' | 'enricher' | 'manager';

export interface StudioTourStepDef {
  /** Panel to open before this step (host.openPanel is idempotent — open-or-focus). Omit for
   *  chrome-only steps (activity bar / command palette) that need no dock panel open. */
  panelId?: string;
  /** CSS selector for the live DOM anchor. */
  target: string;
  /** i18n keys (studio namespace). */
  titleKey: string;
  bodyKey: string;
}

/** Builds one role-tour step from a panel's catalog `tourAnchor` — throws at module-init time
 *  (not silently) if a role tour references a panel with no `tourAnchor`, since that's a
 *  spec-authoring mistake, not a runtime condition. */
function roleStep(panelId: string, tourKey: string): StudioTourStepDef {
  const def = getStudioPanelDef(panelId);
  if (!def?.tourAnchor) {
    throw new Error(`[studio-tour] panel "${panelId}" has no catalog tourAnchor (required by role tour step "${tourKey}")`);
  }
  return {
    panelId,
    target: `[data-testid="${def.tourAnchor}"]`,
    titleKey: `intro.tour.${tourKey}.title`,
    bodyKey: `intro.tour.${tourKey}.body`,
  };
}

export const STUDIO_TOURS: Record<StudioTourId, StudioTourStepDef[]> = {
  core: [
    {
      target: '[data-testid="studio-activity-manuscript"]',
      titleKey: 'intro.tour.core.manuscript.title',
      bodyKey: 'intro.tour.core.manuscript.body',
    },
    {
      target: '[data-testid="studio-command-palette"]',
      titleKey: 'intro.tour.core.palette.title',
      bodyKey: 'intro.tour.core.palette.body',
    },
    {
      panelId: 'compose',
      target: '[data-testid="studio-compose-panel"]',
      titleKey: 'intro.tour.core.compose.title',
      bodyKey: 'intro.tour.core.compose.body',
    },
    {
      panelId: 'editor',
      target: '[data-testid="studio-editor-panel"]',
      titleKey: 'intro.tour.core.editor.title',
      bodyKey: 'intro.tour.core.editor.body',
    },
  ],
  writer: [
    roleStep('compose', 'writer.compose'),
    roleStep('editor', 'writer.editor'),
    roleStep('planner', 'writer.planner'),
  ],
  worldbuilder: [
    roleStep('glossary', 'worldbuilder.glossary'),
    roleStep('wiki', 'worldbuilder.wiki'),
    roleStep('knowledge', 'worldbuilder.knowledge'),
  ],
  translator: [
    roleStep('translation', 'translator.translation'),
    roleStep('enrichment-compose', 'translator.enrichmentCompose'),
  ],
  enricher: [
    roleStep('enrichment-gaps', 'enricher.gaps'),
    roleStep('enrichment-sources', 'enricher.sources'),
  ],
  manager: [
    roleStep('sharing', 'manager.sharing'),
    roleStep('book-settings', 'manager.bookSettings'),
  ],
};
