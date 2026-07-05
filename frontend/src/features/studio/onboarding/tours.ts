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
// StudioTourId/EDITOR_TOUR_CATALOG live in tourCatalog.ts (no catalog.ts dependency) to avoid a
// circular import — see that file's header comment. Re-exported here so existing consumers of
// `tours.ts` are unaffected.
import type { StudioTourId } from './tourCatalog';
export type { StudioTourId, StudioTourCatalogEntry } from './tourCatalog';
export { EDITOR_TOUR_CATALOG, COMPOSE_TOUR_CATALOG } from './tourCatalog';

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
    {
      panelId: 'editor',
      target: '[data-testid="studio-editor-toggle-grammar"]',
      titleKey: 'intro.tour.core.grammar.title',
      bodyKey: 'intro.tour.core.grammar.body',
    },
    {
      panelId: 'editor',
      target: '[data-testid="studio-editor-toggle-heatmap"]',
      titleKey: 'intro.tour.core.heatmap.title',
      bodyKey: 'intro.tour.core.heatmap.body',
    },
  ],
  writer: [
    roleStep('compose', 'writer.compose'),
    roleStep('editor', 'writer.editor'),
    // Manual (not roleStep) — these target sub-anchors INSIDE the editor panel (its grammar/
    // heatmap toggle buttons), not the panel's own single catalog tourAnchor, so roleStep's
    // one-anchor-per-panel shape doesn't fit. Mirrors core's grammar/heatmap steps.
    {
      panelId: 'editor',
      target: '[data-testid="studio-editor-toggle-grammar"]',
      titleKey: 'intro.tour.writer.grammar.title',
      bodyKey: 'intro.tour.writer.grammar.body',
    },
    {
      panelId: 'editor',
      target: '[data-testid="studio-editor-toggle-heatmap"]',
      titleKey: 'intro.tour.writer.heatmap.title',
      bodyKey: 'intro.tour.writer.heatmap.body',
    },
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

  // #19 Wave 3 — editor deep-dive tours. All steps open the 'editor' panel first (their anchors
  // live inside EditorPanel/its children); a step whose anchor is conditionally rendered (e.g.
  // Checkpoints only appears once an AI edit exists) safely SKIPS via useStudioTour's existing
  // anchor-timeout — never blocks the rest of the tour.
  editorBasics: [
    { panelId: 'editor', target: '[data-testid="studio-editor-toggle-grammar"]', titleKey: 'intro.tour.editorBasics.grammar.title', bodyKey: 'intro.tour.editorBasics.grammar.body' },
    { panelId: 'editor', target: '[data-testid="studio-editor-toggle-heatmap"]', titleKey: 'intro.tour.editorBasics.heatmap.title', bodyKey: 'intro.tour.editorBasics.heatmap.body' },
    { panelId: 'editor', target: '[data-testid="studio-editor-toggle-glossary"]', titleKey: 'intro.tour.editorBasics.glossary.title', bodyKey: 'intro.tour.editorBasics.glossary.body' },
    { panelId: 'editor', target: '[data-testid="studio-editor-toggle-focus"]', titleKey: 'intro.tour.editorBasics.focus.title', bodyKey: 'intro.tour.editorBasics.focus.body' },
    { panelId: 'editor', target: '[data-testid="studio-editor-toggle-scenes"]', titleKey: 'intro.tour.editorBasics.scenes.title', bodyKey: 'intro.tour.editorBasics.scenes.body' },
    { panelId: 'editor', target: '[data-testid="studio-editor-open-json"]', titleKey: 'intro.tour.editorBasics.openJson.title', bodyKey: 'intro.tour.editorBasics.openJson.body' },
    { panelId: 'editor', target: '[data-testid="studio-editor-open-original-source"]', titleKey: 'intro.tour.editorBasics.originalSource.title', bodyKey: 'intro.tour.editorBasics.originalSource.body' },
    { panelId: 'editor', target: '[data-testid="studio-editor-open-reader"]', titleKey: 'intro.tour.editorBasics.reader.title', bodyKey: 'intro.tour.editorBasics.reader.body' },
    { panelId: 'editor', target: '[data-testid="studio-editor-open-translate"]', titleKey: 'intro.tour.editorBasics.translate.title', bodyKey: 'intro.tour.editorBasics.translate.body' },
    { panelId: 'editor', target: '[data-testid="studio-editor-save"]', titleKey: 'intro.tour.editorBasics.save.title', bodyKey: 'intro.tour.editorBasics.save.body' },
  ],
  editorAiTools: [
    { panelId: 'editor', target: '[data-testid="inline-mode-ai"]', titleKey: 'intro.tour.editorAiTools.mode.title', bodyKey: 'intro.tour.editorAiTools.mode.body' },
    { panelId: 'editor', target: '[data-testid="inline-continue"]', titleKey: 'intro.tour.editorAiTools.continueStep.title', bodyKey: 'intro.tour.editorAiTools.continueStep.body' },
  ],
  editorDataSafety: [
    { panelId: 'editor', target: '[data-testid="studio-manuscript-checkpoints"]', titleKey: 'intro.tour.editorDataSafety.checkpoints.title', bodyKey: 'intro.tour.editorDataSafety.checkpoints.body' },
    { panelId: 'editor', target: '[data-testid="studio-revision-history"]', titleKey: 'intro.tour.editorDataSafety.revisionHistory.title', bodyKey: 'intro.tour.editorDataSafety.revisionHistory.body' },
    { panelId: 'editor', target: '[data-testid="editorial-badge"]', titleKey: 'intro.tour.editorDataSafety.publish.title', bodyKey: 'intro.tour.editorDataSafety.publish.body' },
  ],
  editorSceneRail: [
    { panelId: 'editor', target: '[data-testid="studio-scene-rail"]', titleKey: 'intro.tour.editorSceneRail.rail.title', bodyKey: 'intro.tour.editorSceneRail.rail.body' },
    { panelId: 'editor', target: '[data-testid="scene-rail-anchor"]', titleKey: 'intro.tour.editorSceneRail.anchor.title', bodyKey: 'intro.tour.editorSceneRail.anchor.body' },
    { panelId: 'editor', target: '[data-testid="scene-rail-add"]', titleKey: 'intro.tour.editorSceneRail.add.title', bodyKey: 'intro.tour.editorSceneRail.add.body' },
  ],
  editorGlossary: [
    { panelId: 'editor', target: '[data-testid="studio-editor-toggle-glossary"]', titleKey: 'intro.tour.editorGlossary.toggle.title', bodyKey: 'intro.tour.editorGlossary.toggle.body' },
  ],
  editorMediaImage: [
    { panelId: 'editor', target: '[data-testid="format-toolbar-insert-image"]', titleKey: 'intro.tour.editorMediaImage.insert.title', bodyKey: 'intro.tour.editorMediaImage.insert.body' },
  ],
  editorMediaVideo: [
    { panelId: 'editor', target: '[data-testid="format-toolbar-insert-video"]', titleKey: 'intro.tour.editorMediaVideo.insert.title', bodyKey: 'intro.tour.editorMediaVideo.insert.body' },
  ],
  editorMediaAudio: [
    { panelId: 'editor', target: '[data-testid="format-toolbar-insert-audio"]', titleKey: 'intro.tour.editorMediaAudio.insert.title', bodyKey: 'intro.tour.editorMediaAudio.insert.body' },
  ],

  // #19 Wave 4 — composer deep-dive tours (docs/specs/2026-07-06-composer-feature-inventory.md).
  // All steps open the 'compose' panel first. Cards that only exist DURING a live agent turn
  // (propose-edit, confirm-action, activity strip) have no static anchor to spotlight while idle —
  // composerAiEditReview instead targets the always-mounted message list with a descriptive body,
  // rather than a step that would silently skip on every timeout.
  composerBasics: [
    { panelId: 'compose', target: '[data-testid="chat-input-textarea"]', titleKey: 'intro.tour.composerBasics.textarea.title', bodyKey: 'intro.tour.composerBasics.textarea.body' },
    { panelId: 'compose', target: '[data-testid="permission-mode-toggle"]', titleKey: 'intro.tour.composerBasics.permissionMode.title', bodyKey: 'intro.tour.composerBasics.permissionMode.body' },
    { panelId: 'compose', target: '[data-testid="effort-select"]', titleKey: 'intro.tour.composerBasics.effort.title', bodyKey: 'intro.tour.composerBasics.effort.body' },
    { panelId: 'compose', target: '[data-testid="chat-attach-context"]', titleKey: 'intro.tour.composerBasics.attachContext.title', bodyKey: 'intro.tour.composerBasics.attachContext.body' },
    { panelId: 'compose', target: '[data-testid="chat-send-button"]', titleKey: 'intro.tour.composerBasics.send.title', bodyKey: 'intro.tour.composerBasics.send.body' },
  ],
  composerSessions: [
    { panelId: 'compose', target: '[data-testid="session-switcher-trigger"]', titleKey: 'intro.tour.composerSessions.switcher.title', bodyKey: 'intro.tour.composerSessions.switcher.body' },
    { panelId: 'compose', target: '[data-testid="chat-rename-session"]', titleKey: 'intro.tour.composerSessions.rename.title', bodyKey: 'intro.tour.composerSessions.rename.body' },
    { panelId: 'compose', target: '[data-testid="chat-session-settings-button"]', titleKey: 'intro.tour.composerSessions.settings.title', bodyKey: 'intro.tour.composerSessions.settings.body' },
  ],
  composerAgentTools: [
    { panelId: 'compose', target: '[data-testid="agent-context-rack"]', titleKey: 'intro.tour.composerAgentTools.rack.title', bodyKey: 'intro.tour.composerAgentTools.rack.body' },
    { panelId: 'compose', target: '[data-testid="agent-rack-add"]', titleKey: 'intro.tour.composerAgentTools.add.title', bodyKey: 'intro.tour.composerAgentTools.add.body' },
    { panelId: 'compose', target: '[data-testid="agent-runtime-inspector"]', titleKey: 'intro.tour.composerAgentTools.inspector.title', bodyKey: 'intro.tour.composerAgentTools.inspector.body' },
  ],
  composerContextBudget: [
    { panelId: 'compose', target: '[data-testid="context-meter"]', titleKey: 'intro.tour.composerContextBudget.meter.title', bodyKey: 'intro.tour.composerContextBudget.meter.body' },
  ],
  composerAiEditReview: [
    { panelId: 'compose', target: '[data-testid="chat-message-list"]', titleKey: 'intro.tour.composerAiEditReview.review.title', bodyKey: 'intro.tour.composerAiEditReview.review.body' },
  ],
  composerVoice: [
    { panelId: 'compose', target: '[data-testid="chat-voice-mode-toggle"]', titleKey: 'intro.tour.composerVoice.mode.title', bodyKey: 'intro.tour.composerVoice.mode.body' },
    { panelId: 'compose', target: '[data-testid="chat-voice-settings-button"]', titleKey: 'intro.tour.composerVoice.settings.title', bodyKey: 'intro.tour.composerVoice.settings.body' },
  ],
  composerPopout: [
    { panelId: 'compose', target: '[data-testid="studio-compose-popout"]', titleKey: 'intro.tour.composerPopout.popout.title', bodyKey: 'intro.tour.composerPopout.popout.body' },
  ],
};
