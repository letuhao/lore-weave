// #19 Wave 1 — the `core` guided tour. Steps target LIVE DOM via already-existing, stable
// `data-testid`s on the chrome and dock panels (never a screenshot) — the exact same testids
// this repo's own E2E specs already assert on, so a tour step can't silently drift from what's
// actually rendered without an existing test also catching it.
export type StudioTourId = 'core';

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
};
