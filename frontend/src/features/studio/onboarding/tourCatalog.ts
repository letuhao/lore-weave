// Split out of tours.ts to avoid a circular import: catalog.ts imports UserGuidePanel.tsx (its
// 'user-guide' STUDIO_PANELS entry), and UserGuidePanel.tsx needs EDITOR_TOUR_CATALOG for the
// tour-picker section — but tours.ts's role-tour steps call getStudioPanelDef from catalog.ts AT
// MODULE-INIT TIME (via roleStep()), so importing tours.ts from UserGuidePanel.tsx created
// catalog.ts → UserGuidePanel.tsx → tours.ts → catalog.ts, breaking on whichever module the cycle
// reached catalog.ts through first (getStudioPanelDef undefined mid-init). This file has NO
// dependency on catalog.ts, so UserGuidePanel.tsx can import it safely; tours.ts re-exports from
// here rather than defining these itself.

export type StudioTourId =
  | 'core' | 'writer' | 'worldbuilder' | 'translator' | 'enricher' | 'manager'
  | 'worldResearch' | 'factChecking' | 'glossaryWorkflow'
  // #19 Wave 3 — editor "deep dive" tours (docs/specs/2026-07-06-editor-feature-inventory.md).
  | 'editorBasics' | 'editorAiTools' | 'editorDataSafety' | 'editorSceneRail' | 'editorGlossary'
  | 'editorMediaImage' | 'editorMediaVideo' | 'editorMediaAudio' | 'structureTemplates'
  // #19 Wave 4 — composer "deep dive" tours (docs/specs/2026-07-06-composer-feature-inventory.md).
  | 'composerBasics' | 'composerSessions' | 'composerAgentTools' | 'composerContextBudget'
  | 'composerAiEditReview' | 'composerVoice' | 'composerPopout';

export interface StudioTourCatalogEntry {
  id: StudioTourId;
  labelKey: string;
  descKey: string;
}

/** The tours meant to be picked directly by the user, via UserGuidePanel's tour picker —
 *  excludes 'core' and the 5 role tours, which start automatically from onboarding or the
 *  Command Palette's role-aware "Start Guided Tour", not a standalone picker entry. */
export const EDITOR_TOUR_CATALOG: StudioTourCatalogEntry[] = [
  { id: 'editorBasics', labelKey: 'tourPicker.editorBasics.label', descKey: 'tourPicker.editorBasics.desc' },
  { id: 'editorAiTools', labelKey: 'tourPicker.editorAiTools.label', descKey: 'tourPicker.editorAiTools.desc' },
  { id: 'editorDataSafety', labelKey: 'tourPicker.editorDataSafety.label', descKey: 'tourPicker.editorDataSafety.desc' },
  { id: 'editorSceneRail', labelKey: 'tourPicker.editorSceneRail.label', descKey: 'tourPicker.editorSceneRail.desc' },
  { id: 'editorGlossary', labelKey: 'tourPicker.editorGlossary.label', descKey: 'tourPicker.editorGlossary.desc' },
  { id: 'editorMediaImage', labelKey: 'tourPicker.editorMediaImage.label', descKey: 'tourPicker.editorMediaImage.desc' },
  { id: 'editorMediaVideo', labelKey: 'tourPicker.editorMediaVideo.label', descKey: 'tourPicker.editorMediaVideo.desc' },
  { id: 'editorMediaAudio', labelKey: 'tourPicker.editorMediaAudio.label', descKey: 'tourPicker.editorMediaAudio.desc' },
  // NOT `structureTemplates`: this list renders under the "Editor" heading in UserGuidePanel,
  // and every one of its steps opens the editor panel (asserted in tours.test.ts). That tour
  // opens `structure-templates`, so listing it here offered an Editor tour that navigated
  // somewhere else. It reaches the user through PANEL_TOUR_IDS['structure-templates'] below,
  // which is the per-panel guide action it was written for.
];

/** #19 Wave 4 — Composer's own tour-picker entries (same "topic, not one long walkthrough" split). */
export const COMPOSE_TOUR_CATALOG: StudioTourCatalogEntry[] = [
  { id: 'composerBasics', labelKey: 'tourPicker.composerBasics.label', descKey: 'tourPicker.composerBasics.desc' },
  { id: 'composerSessions', labelKey: 'tourPicker.composerSessions.label', descKey: 'tourPicker.composerSessions.desc' },
  { id: 'composerAgentTools', labelKey: 'tourPicker.composerAgentTools.label', descKey: 'tourPicker.composerAgentTools.desc' },
  { id: 'composerContextBudget', labelKey: 'tourPicker.composerContextBudget.label', descKey: 'tourPicker.composerContextBudget.desc' },
  { id: 'composerAiEditReview', labelKey: 'tourPicker.composerAiEditReview.label', descKey: 'tourPicker.composerAiEditReview.desc' },
  { id: 'composerVoice', labelKey: 'tourPicker.composerVoice.label', descKey: 'tourPicker.composerVoice.desc' },
  { id: 'composerPopout', labelKey: 'tourPicker.composerPopout.label', descKey: 'tourPicker.composerPopout.desc' },
];

/** Research workflows: these tours connect the glossary, evidence and knowledge-graph
 * panels into repeatable investigation practices rather than teaching isolated controls. */
export const PANEL_TOUR_IDS: Partial<Record<string, StudioTourId[]>> = {
  editor: ['editorBasics', 'editorAiTools', 'editorDataSafety', 'editorSceneRail', 'editorGlossary', 'editorMediaImage', 'editorMediaVideo', 'editorMediaAudio'],
  'structure-templates': ['structureTemplates'],
  compose: ['composerBasics', 'composerSessions', 'composerAgentTools', 'composerContextBudget', 'composerAiEditReview', 'composerVoice', 'composerPopout'],
  glossary: ['glossaryWorkflow'],
  'world-setup': ['worldResearch'],
  'kg-entities': ['worldResearch'],
  'kg-timeline': ['worldResearch'],
  'kg-graph': ['worldResearch'],
  'kg-evidence': ['factChecking'],
  'kg-triage': ['factChecking'],
  'kg-gap': ['factChecking'],
  'glossary-unknown': ['factChecking'],
  'kg-proposals': ['factChecking'],
};

export const RESEARCH_TOUR_CATALOG: StudioTourCatalogEntry[] = [
  { id: 'worldResearch', labelKey: 'tourPicker.worldResearch.label', descKey: 'tourPicker.worldResearch.desc' },
  { id: 'factChecking', labelKey: 'tourPicker.factChecking.label', descKey: 'tourPicker.factChecking.desc' },
  { id: 'glossaryWorkflow', labelKey: 'tourPicker.glossaryWorkflow.label', descKey: 'tourPicker.glossaryWorkflow.desc' },
];
