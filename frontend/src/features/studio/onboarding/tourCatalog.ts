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
  // #19 Wave 3 — editor "deep dive" tours (docs/specs/2026-07-06-editor-feature-inventory.md).
  | 'editorBasics' | 'editorAiTools' | 'editorDataSafety' | 'editorSceneRail' | 'editorGlossary'
  | 'editorMediaImage' | 'editorMediaVideo' | 'editorMediaAudio'
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
