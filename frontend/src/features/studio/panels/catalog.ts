// The static catalog of buildable studio dock panels — every panel the studio CAN open, whether
// or not it's currently mounted. This is the source for:
//   • StudioDock's dockview component map (id → component)
//   • the Command Palette "Studio: Open …" commands (#06b) — a CLOSED panel must still be openable,
//     which a mount-scoped registry (useRegisteredTools) can't provide. The registry stays for the
//     AGENT rack (#07a — which tools are LIVE this turn); the catalog is what can be opened.
// Convention: `id` === the dockview component id (so host.openPanel adds `component: id`).
import type { FunctionComponent } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { WelcomePanel } from '../components/panels/WelcomePanel';
import { ComposePanel } from './ComposePanel';
import { SceneComposePanel } from './SceneComposePanel';
import { ChapterAssemblePanel } from './ChapterAssemblePanel';
import { EditorPanel } from './EditorPanel';
import { PlannerPanel } from '@/features/plan-forge/components/PlannerPanel';
import { PassRailPanel } from '@/features/plan-forge/components/PassRailPanel';
import { MotifLibraryPanel } from './MotifLibraryPanel';
import { QualityConformancePanel } from './QualityConformancePanel';
import { ArcInspectorPanel } from './ArcInspectorPanel';   /* owner: S2 */
import { ArcTemplatesPanel } from './ArcTemplatesPanel';   /* owner: S2 */
import { UsagePanel } from './UsagePanel';
import { NotificationsPanel } from './NotificationsPanel';
import { SettingsPanel } from './SettingsPanel';
import { TrashPanel } from './TrashPanel';
import { JsonEditorPanel } from './JsonEditorPanel';
import { ExtensionsPanel } from './ExtensionsPanel';
import { ProposalsPanel } from './ProposalsPanel';
import { SkillEditorPanel } from './SkillEditorPanel';
import { SteeringPanel } from './SteeringPanel';
import { GlossaryPanel } from './GlossaryPanel';
import { GlossaryOntologyPanel } from './GlossaryOntologyPanel';
import { GlossaryUnknownPanel } from './GlossaryUnknownPanel';
import { GlossaryAiSuggestionsPanel } from './GlossaryAiSuggestionsPanel';
import { GlossaryMergeCandidatesPanel } from './GlossaryMergeCandidatesPanel';
import { WikiPanel } from './WikiPanel';
import { WikiEditorPanel } from './WikiEditorPanel';
import { KnowledgeHubPanel } from './KnowledgeHubPanel';
import { KgOverviewPanel } from './KgOverviewPanel';
import { KgEntitiesPanel } from './KgEntitiesPanel';
import { KgTimelinePanel } from './KgTimelinePanel';
import { KgEvidencePanel } from './KgEvidencePanel';
import { KgGapReportPanel } from './KgGapReportPanel';
import { KgProposalsPanel } from './KgProposalsPanel';
import { KgSchemaPanel } from './KgSchemaPanel';
import { KgGraphPanel } from './KgGraphPanel';
import { KgInsightsPanel } from './KgInsightsPanel';
import { KgJobsPanel } from './KgJobsPanel';
import { KgGlobalBioPanel } from './KgGlobalBioPanel';
import { KgPrivacyPanel } from './KgPrivacyPanel';
import { JobsListPanel } from './JobsListPanel';
import { JobDetailPanel } from './JobDetailPanel';
import { BooksBrowserPanel } from './BooksBrowserPanel';
import { BookReaderPanel } from './BookReaderPanel';
import { LeaderboardBooksPanel } from './LeaderboardBooksPanel';
import { LeaderboardAuthorsPanel } from './LeaderboardAuthorsPanel';
import { LeaderboardTranslatorsPanel } from './LeaderboardTranslatorsPanel';
import { LeaderboardTrendingPanel } from './LeaderboardTrendingPanel';
import { ChapterBrowserPanel } from './ChapterBrowserPanel';
import { SceneBrowserPanel } from './SceneBrowserPanel';
import { SceneInspectorPanel } from './SceneInspectorPanel';
import { WhatIfCanvasPanel } from './WhatIfCanvasPanel';
import { DivergencePanel } from './DivergencePanel';
import { PlanHubPanel } from './PlanHubPanel';
import { BookImportPanel } from './BookImportPanel';
import { ContextInspectorPanel } from './ContextInspectorPanel';
import { MediaVersionHistoryPanel } from './MediaVersionHistoryPanel';
import { OriginalSourcePanel } from './OriginalSourcePanel';
import { SharingPanel } from './SharingPanel';
import { BookSettingsPanel } from './BookSettingsPanel';
import { TranslationPanel } from './TranslationPanel';
import { TranslationVersionsPanel } from './TranslationVersionsPanel';
import { TranslationReviewPanel } from './TranslationReviewPanel';
import { EnrichmentComposePanel } from './EnrichmentComposePanel';
import { EnrichmentProposalsPanel } from './EnrichmentProposalsPanel';
import { EnrichmentGapsPanel } from './EnrichmentGapsPanel';
import { EnrichmentSourcesPanel } from './EnrichmentSourcesPanel';
import { EnrichmentJobsPanel } from './EnrichmentJobsPanel';
import { EnrichmentSettingsPanel } from './EnrichmentSettingsPanel';
import { UserGuidePanel } from './UserGuidePanel';
import { AgentModePanel } from './AgentModePanel';
import { ChapterRevisionComparePanel } from './ChapterRevisionComparePanel';
import { QualityHubPanel } from './QualityHubPanel';
import { QualityPromisesPanel } from './QualityPromisesPanel';
import { QualityCriticPanel } from './QualityCriticPanel';
import { QualityCoveragePanel } from './QualityCoveragePanel';
import { QualityCanonPanel } from './QualityCanonPanel';
import { QualityCanonRulesPanel } from './QualityCanonRulesPanel';
import { QualityCorrectionsPanel } from './QualityCorrectionsPanel';
import { QualityHealPanel } from './QualityHealPanel';
import { ProgressStudioPanel } from './ProgressStudioPanel';
// ── S7 · Knowledge/World/Cast ── (integrator-wired; components owned by build groups A/B/C)
import { WorldMapEditorPanel } from './WorldMapEditorPanel';
import { PlaceGraphPanel } from './PlaceGraphPanel';
import { CastPanel } from './CastPanel';
import { CharacterArcPanel } from './CharacterArcPanel';

/** #18 — domain-area grouping for the Command Palette. Required for every non-hidden panel
 *  (enforced at runtime by panelCatalogContract.test.ts — B6, not just a convention). */
export type StudioPanelCategory =
  | 'editor'
  | 'storyBible'
  | 'knowledge'
  | 'quality'
  | 'translation'
  | 'enrichment'
  | 'sharing'
  | 'platform'
  | 'discovery'
  | 'jobs';

/** X-2 — the runtime mirror of the union above, so a test can assert CATEGORY_ORDER
 *  (palette/useStudioCommands.ts) covers EXACTLY these. Kept adjacent to the union so the two
 *  can't drift unseen; the compile-time half of the guard lives on CATEGORY_ORDER itself.
 *  NOTE: this is deliberately NOT the home of CATEGORY_ORDER — catalog.ts imports UserGuidePanel,
 *  which imports CATEGORY_ORDER from useStudioCommands; a value import back the other way would
 *  close a real runtime cycle. */
export const ALL_CATEGORIES = [
  'editor', 'storyBible', 'knowledge', 'quality', 'translation',
  'enrichment', 'sharing', 'platform', 'discovery', 'jobs',
] as const satisfies readonly StudioPanelCategory[];
// A category added to the union but not to ALL_CATEGORIES is a TYPE ERROR here.
type _UnlistedCategory = Exclude<StudioPanelCategory, (typeof ALL_CATEGORIES)[number]>;
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const _ALL_CATEGORIES_IS_EXHAUSTIVE: [_UnlistedCategory] extends [never] ? true : never = true;

export interface StudioPanelDef {
  id: string;
  component: FunctionComponent<IDockviewPanelProps>;
  /** i18n keys (studio namespace) for the dock tab title + palette description. */
  titleKey: string;
  descKey: string;
  /** Omit from the Command Palette "Open" list (e.g. the default Welcome placeholder). */
  hiddenFromPalette?: boolean;
  /** Command Palette sub-group (#18). Omit only when hiddenFromPalette is true. */
  category?: StudioPanelCategory;
  /** #19 / X-3 — the i18n key for the User Guide body. **REQUIRED, not optional.**
   *
   *  It was `guideBodyKey?: string` with a "falls back to descKey when absent" contract, and that
   *  fallback is exactly how 5 panels shipped a SILENTLY BLANK guide row: UserGuidePanel.tsx:120
   *  renders `t(p.guideBodyKey ?? p.descKey, { defaultValue: '' })`, so a missing key OR missing
   *  copy renders an empty string — no warning, no crash. Making it required means "forgot the
   *  guide body" is a TYPE ERROR, not a blank row a user discovers.
   *
   *  `hiddenFromPalette` rows carry the key too (rather than forking the type into an
   *  openable/hidden union). Their copy is a forward-compat placeholder: they never render in the
   *  guide, but the moment one is un-hidden, panelCatalogContract's "resolves to non-empty English
   *  copy" test REDS until its `panels.<id>.guideBody` string is written. That is the guard working. */
  guideBodyKey: string;
  /** #19 Wave 2 — the panel's root `data-testid` selector (e.g. `[data-testid="studio-glossary-panel"]`),
   *  used by role-specific guided tours to target this panel without re-deriving `studio-${id}-panel`
   *  (which is wrong for the few panels whose testid doesn't match their id 1:1, e.g. `knowledge` →
   *  `studio-knowledge-hub-panel`). Only set on panels that are a step in a role tour. */
  tourAnchor?: string;
}

export const STUDIO_PANELS: StudioPanelDef[] = [
  { id: 'compose', component: ComposePanel, titleKey: 'panels.compose.title', descKey: 'panels.compose.desc', category: 'editor', guideBodyKey: 'panels.compose.guideBody', tourAnchor: 'studio-compose-panel' },
  { id: 'editor', component: EditorPanel, titleKey: 'panels.editor.title', descKey: 'panels.editor.desc', category: 'editor', guideBodyKey: 'panels.editor.guideBody', tourAnchor: 'studio-editor-panel' },
  { id: 'planner', component: PlannerPanel, titleKey: 'panels.planner.title', descKey: 'panels.planner.desc', category: 'editor', guideBodyKey: 'panels.planner.guideBody', tourAnchor: 'studio-planner-panel' },
  // #11 W2 — user-scoped panels (dockable migration wave 1).
  { id: 'usage', component: UsagePanel, titleKey: 'panels.usage.title', descKey: 'panels.usage.desc', category: 'platform', guideBodyKey: 'panels.usage.guideBody' },
  { id: 'notifications', component: NotificationsPanel, titleKey: 'panels.notifications.title', descKey: 'panels.notifications.desc', category: 'platform', guideBodyKey: 'panels.notifications.guideBody' },
  { id: 'settings', component: SettingsPanel, titleKey: 'panels.settings.title', descKey: 'panels.settings.desc', category: 'platform', guideBodyKey: 'panels.settings.guideBody' },
  { id: 'trash', component: TrashPanel, titleKey: 'panels.trash.title', descKey: 'panels.trash.desc', category: 'platform', guideBodyKey: 'panels.trash.guideBody' },
  // RAID C1 — per-book author steering rules (story-bible-as-steering). book-scoped, palette-openable.
  { id: 'steering', component: SteeringPanel, titleKey: 'panels.steering.title', descKey: 'panels.steering.desc', category: 'editor', guideBodyKey: 'panels.steering.guideBody' },
  // #13 A3 — entity list/search/filter/bulk-actions (cycle-2 of the #12 per-tool queue).
  // Palette + agent openable (panelCatalogContract enforces openable-set == enum, so any
  // palette-visible panel must join `ui_open_studio_panel` — see frontend_tools.py + the
  // regenerated contracts/frontend-tools.contract.json).
  { id: 'glossary', component: GlossaryPanel, titleKey: 'panels.glossary.title', descKey: 'panels.glossary.desc', category: 'storyBible', guideBodyKey: 'panels.glossary.guideBody', tourAnchor: 'studio-glossary-panel' },
  // 13_glossary_panels.md Phase B — the 4 capabilities GlossaryPanel used to internally
  // view-switch (a DOCK-8 exception) are now real sibling dock panels. Each is palette + agent
  // openable (panelCatalogContract enforces openable-set == enum) and reachable from the
  // `glossary` panel's own launcher buttons via host.openPanel — never a local view flag.
  { id: 'glossary-ontology', component: GlossaryOntologyPanel, titleKey: 'panels.glossary-ontology.title', descKey: 'panels.glossary-ontology.desc', category: 'storyBible', guideBodyKey: 'panels.glossary-ontology.guideBody' },
  { id: 'glossary-unknown', component: GlossaryUnknownPanel, titleKey: 'panels.glossary-unknown.title', descKey: 'panels.glossary-unknown.desc', category: 'storyBible', guideBodyKey: 'panels.glossary-unknown.guideBody' },
  { id: 'glossary-ai-suggestions', component: GlossaryAiSuggestionsPanel, titleKey: 'panels.glossary-ai-suggestions.title', descKey: 'panels.glossary-ai-suggestions.desc', category: 'storyBible', guideBodyKey: 'panels.glossary-ai-suggestions.guideBody' },
  { id: 'glossary-merge-candidates', component: GlossaryMergeCandidatesPanel, titleKey: 'panels.glossary-merge-candidates.title', descKey: 'panels.glossary-merge-candidates.desc', category: 'storyBible', guideBodyKey: 'panels.glossary-merge-candidates.guideBody' },
  // 15_wiki_panels.md B1 — the wiki master-detail workspace (DOCK-2, same shared component the
  // classic WikiTab page renders). Palette + agent openable.
  { id: 'wiki', component: WikiPanel, titleKey: 'panels.wiki.title', descKey: 'panels.wiki.desc', category: 'storyBible', guideBodyKey: 'panels.wiki.guideBody', tourAnchor: 'studio-wiki-panel' },
  // 15_wiki_panels.md B2 — params-retargeting singleton ({articleId, rightPanel?}), same
  // precedent as book-reader/json-editor/skill-editor: hidden from palette + outside the agent
  // enum (opened only via the `wiki` panel's Edit/History buttons — no wiki_* MCP tool exists
  // yet for an agent to target it with).
  { id: 'wiki-editor', component: WikiEditorPanel, titleKey: 'panels.wiki-editor.title', descKey: 'panels.wiki-editor.desc', hiddenFromPalette: true, guideBodyKey: 'panels.wiki-editor.guideBody' },
  // 14_kg_panels.md A2 — the KG launcher (DOCK-8 hub pattern): browse/open knowledge-graph
  // projects. Phase B adds the capability panels it currently opens via a new-tab fallback.
  { id: 'knowledge', component: KnowledgeHubPanel, titleKey: 'panels.knowledge.title', descKey: 'panels.knowledge.desc', category: 'knowledge', guideBodyKey: 'panels.knowledge.guideBody', tourAnchor: 'studio-knowledge-hub-panel' },
  // 14_kg_panels.md Phase B — the 12 KG capability panels the `knowledge` hub launcher
  // opens (today via a new-tab fallback until each lands; landing here makes it in-tab).
  // overview/gap/proposals/schema/graph are book-scoped (useBookKnowledgeProject);
  // entities/timeline/evidence take an optional params.scopedProjectId (K4, shared scope);
  // insights/jobs/bio/privacy are user-scoped (global, cross-book — same tier as usage/settings).
  { id: 'kg-overview', component: KgOverviewPanel, titleKey: 'panels.kg-overview.title', descKey: 'panels.kg-overview.desc', category: 'knowledge', guideBodyKey: 'panels.kg-overview.guideBody' },
  { id: 'kg-entities', component: KgEntitiesPanel, titleKey: 'panels.kg-entities.title', descKey: 'panels.kg-entities.desc', category: 'knowledge', guideBodyKey: 'panels.kg-entities.guideBody' },
  { id: 'kg-timeline', component: KgTimelinePanel, titleKey: 'panels.kg-timeline.title', descKey: 'panels.kg-timeline.desc', category: 'knowledge', guideBodyKey: 'panels.kg-timeline.guideBody' },
  { id: 'kg-evidence', component: KgEvidencePanel, titleKey: 'panels.kg-evidence.title', descKey: 'panels.kg-evidence.desc', category: 'knowledge', guideBodyKey: 'panels.kg-evidence.guideBody' },
  { id: 'kg-gap', component: KgGapReportPanel, titleKey: 'panels.kg-gap.title', descKey: 'panels.kg-gap.desc', category: 'knowledge', guideBodyKey: 'panels.kg-gap.guideBody' },
  { id: 'kg-proposals', component: KgProposalsPanel, titleKey: 'panels.kg-proposals.title', descKey: 'panels.kg-proposals.desc', category: 'knowledge', guideBodyKey: 'panels.kg-proposals.guideBody' },
  { id: 'kg-schema', component: KgSchemaPanel, titleKey: 'panels.kg-schema.title', descKey: 'panels.kg-schema.desc', category: 'knowledge', guideBodyKey: 'panels.kg-schema.guideBody' },
  { id: 'kg-graph', component: KgGraphPanel, titleKey: 'panels.kg-graph.title', descKey: 'panels.kg-graph.desc', category: 'knowledge', guideBodyKey: 'panels.kg-graph.guideBody' },
  { id: 'kg-insights', component: KgInsightsPanel, titleKey: 'panels.kg-insights.title', descKey: 'panels.kg-insights.desc', category: 'knowledge', guideBodyKey: 'panels.kg-insights.guideBody' },
  { id: 'kg-jobs', component: KgJobsPanel, titleKey: 'panels.kg-jobs.title', descKey: 'panels.kg-jobs.desc', category: 'knowledge', guideBodyKey: 'panels.kg-jobs.guideBody' },
  { id: 'kg-bio', component: KgGlobalBioPanel, titleKey: 'panels.kg-bio.title', descKey: 'panels.kg-bio.desc', category: 'knowledge', guideBodyKey: 'panels.kg-bio.guideBody' },
  { id: 'kg-privacy', component: KgPrivacyPanel, titleKey: 'panels.kg-privacy.title', descKey: 'panels.kg-privacy.desc', category: 'knowledge', guideBodyKey: 'panels.kg-privacy.guideBody' },
  // 14_utility_panels.md Phase B — jobs-list is palette + agent openable; job-detail is a
  // params-retargeting singleton ({service, jobId}, json-editor/skill-editor precedent).
  { id: 'jobs-list', component: JobsListPanel, titleKey: 'panels.jobs-list.title', descKey: 'panels.jobs-list.desc', category: 'jobs', guideBodyKey: 'panels.jobs-list.guideBody' },
  { id: 'job-detail', component: JobDetailPanel, titleKey: 'panels.job-detail.title', descKey: 'panels.job-detail.desc', hiddenFromPalette: true, guideBodyKey: 'panels.job-detail.guideBody' },
  // 14_utility_panels.md Phase C — browse-then-read, no navigate-away: books lists the user's
  // OTHER books; book-reader is a params-retargeting singleton ({bookId, chapterId?}) opened via
  // host.openPanel from a books row click, never a route hop (the active studio never unmounts).
  { id: 'books', component: BooksBrowserPanel, titleKey: 'panels.books.title', descKey: 'panels.books.desc', category: 'discovery', guideBodyKey: 'panels.books.guideBody' },
  { id: 'book-reader', component: BookReaderPanel, titleKey: 'panels.book-reader.title', descKey: 'panels.book-reader.desc', hiddenFromPalette: true, guideBodyKey: 'panels.book-reader.guideBody' },
  // 14_utility_panels.md Phase D — the global leaderboard's 4-tab internal view-switch (DOCK-8
  // anti-pattern) becomes 4 sibling panels; each owns independent filter state.
  { id: 'leaderboard-books', component: LeaderboardBooksPanel, titleKey: 'panels.leaderboard-books.title', descKey: 'panels.leaderboard-books.desc', category: 'discovery', guideBodyKey: 'panels.leaderboard-books.guideBody' },
  { id: 'leaderboard-authors', component: LeaderboardAuthorsPanel, titleKey: 'panels.leaderboard-authors.title', descKey: 'panels.leaderboard-authors.desc', category: 'discovery', guideBodyKey: 'panels.leaderboard-authors.guideBody' },
  { id: 'leaderboard-translators', component: LeaderboardTranslatorsPanel, titleKey: 'panels.leaderboard-translators.title', descKey: 'panels.leaderboard-translators.desc', category: 'discovery', guideBodyKey: 'panels.leaderboard-translators.guideBody' },
  { id: 'leaderboard-trending', component: LeaderboardTrendingPanel, titleKey: 'panels.leaderboard-trending.title', descKey: 'panels.leaderboard-trending.desc', category: 'discovery', guideBodyKey: 'panels.leaderboard-trending.guideBody' },
  // 15_chapter_browser.md — table/search surface for triage at scale (sort/filter/
  // multi-select bulk actions + a Title-vs-Content search-mode toggle), sibling to
  // the Manuscript Navigator (tree, for writing) not a replacement for it.
  { id: 'chapter-browser', component: ChapterBrowserPanel, titleKey: 'panels.chapter-browser.title', descKey: 'panels.chapter-browser.desc', category: 'editor', guideBodyKey: 'panels.chapter-browser.guideBody' },
  { id: 'scene-browser', component: SceneBrowserPanel, titleKey: 'panels.scene-browser.title', descKey: 'panels.scene-browser.desc', category: 'editor', guideBodyKey: 'panels.scene-browser.guideBody' },
  { id: 'scene-inspector', component: SceneInspectorPanel, titleKey: 'panels.scene-inspector.title', descKey: 'panels.scene-inspector.desc', category: 'editor', guideBodyKey: 'panels.scene-inspector.guideBody' },
  // 24 Plan Hub v2 (H2.1) — the package explorer on the graph canvas (structure lanes +
  // keyset chapter/scene windows + scene-link edges, React Flow over the pure laneLayout).
  // Palette + agent openable (panelCatalogContract enforces openable-set == the
  // ui_open_studio_panel enum + regenerated contracts/frontend-tools.contract.json).
  { id: 'plan-hub', component: PlanHubPanel, titleKey: 'panels.plan-hub.title', descKey: 'panels.plan-hub.desc', category: 'editor', guideBodyKey: 'panels.plan-hub.guideBody' },
  // S3 · PlanForge — the 7-pass compiler rail (motifs→…→self_heal) + its 2 blocking checkpoints.
  { id: 'plan-passes', component: PassRailPanel, titleKey: 'panels.plan-passes.title', descKey: 'panels.plan-passes.desc', category: 'editor', guideBodyKey: 'panels.plan-passes.guideBody', tourAnchor: 'studio-plan-passes-panel' },
  { id: 'whatif-canvas', component: WhatIfCanvasPanel, titleKey: 'panels.whatif-canvas.title', descKey: 'panels.whatif-canvas.desc', category: 'editor', guideBodyKey: 'panels.whatif-canvas.guideBody' },
  // D-STUDIO-IMPORT-PANEL — the classic ChaptersTab's import toolbar (text/.docx/.epub +
  // PDF-with-vision-captioning) ported into the studio dock, reusing ImportDialog/PdfImportWizard
  // as-is (DOCK-2). Was reachable only from the pre-Studio /books/:bookId/chapters tab.
  { id: 'book-import', component: BookImportPanel, titleKey: 'panels.book-import.title', descKey: 'panels.book-import.desc', category: 'editor', guideBodyKey: 'panels.book-import.guideBody' },
  // Context Budget Law §11 — the Context Compiler · Trace Inspector: per-turn context-build
  // observability (budget gauge · allocation map · Planner→Compiler waterfall). Palette + agent
  // openable (panelCatalogContract enforces openable-set == the ui_open_studio_panel enum);
  // self-contained (lists sessions + picks one), so it needs no book/studio context.
  { id: 'context-inspector', component: ContextInspectorPanel, titleKey: 'panels.context-inspector.title', descKey: 'panels.context-inspector.desc', category: 'editor', guideBodyKey: 'panels.context-inspector.guideBody' },
  // Agent Extensibility Registry (§13b) — extensions hub + proposals inbox are
  // palette-openable + in the agent enum; skill-editor is a params-retargeting
  // singleton (json-editor precedent), hidden from palette + outside the enum.
  { id: 'extensions', component: ExtensionsPanel, titleKey: 'panels.extensions.title', descKey: 'panels.extensions.desc', category: 'platform', guideBodyKey: 'panels.extensions.guideBody' },
  { id: 'proposals', component: ProposalsPanel, titleKey: 'panels.proposals.title', descKey: 'panels.proposals.desc', category: 'platform', guideBodyKey: 'panels.proposals.guideBody' },
  { id: 'skill-editor', component: SkillEditorPanel, titleKey: 'panels.skill-editor.title', descKey: 'panels.skill-editor.desc', hiddenFromPalette: true, guideBodyKey: 'panels.skill-editor.guideBody' },
  // #12 R3/R4 — singleton, retargets via params {docType, resourceId}; opened by "Open as JSON"
  // affordances only (hidden from palette ⇒ outside the agent enum, no contract change this cycle).
  { id: 'json-editor', component: JsonEditorPanel, titleKey: 'panels.json-editor.title', descKey: 'panels.json-editor.desc', hiddenFromPalette: true, guideBodyKey: 'panels.json-editor.guideBody' },
  // #16 Phase 2 (2.7) — per-resource retargeting singleton (json-editor precedent), opened
  // only from the "history" button inside an image/video NodeView. hiddenFromPalette + outside
  // the agent enum — no contract change this cycle.
  { id: 'media-version-history', component: MediaVersionHistoryPanel, titleKey: 'panels.media-version-history.title', descKey: 'panels.media-version-history.desc', hiddenFromPalette: true, guideBodyKey: 'panels.media-version-history.guideBody' },
  // #16 Phase 2 (2.11) — read-only original-source viewer, retargets via params
  // {bookId, chapterId}; opened only from EditorPanel's toolbar (json-editor precedent),
  // hidden from palette + outside the agent enum.
  { id: 'original-source', component: OriginalSourcePanel, titleKey: 'panels.original-source.title', descKey: 'panels.original-source.desc', hiddenFromPalette: true, guideBodyKey: 'panels.original-source.guideBody' },
  // 17_translation_enrichment_sharing_settings_docks.md — Book Sharing: visibility
  // radio-cards, unlisted-link+rotate, collaborator invite/role-change/remove. DOCK-7/DOCK-9
  // were already clean on the classic page — no navigate/Link, no hand-rolled overlays.
  { id: 'sharing', component: SharingPanel, titleKey: 'panels.sharing.title', descKey: 'panels.sharing.desc', category: 'sharing', guideBodyKey: 'panels.sharing.guideBody', tourAnchor: 'studio-sharing-panel' },
  // 17_...docks.md — Book Settings: title/description/language/summary, cover image, genre
  // tags, world link. Named `book-settings` (not `settings`) to avoid colliding with the
  // existing user-level account/providers/translation panel id.
  { id: 'book-settings', component: BookSettingsPanel, titleKey: 'panels.book-settings.title', descKey: 'panels.book-settings.desc', category: 'sharing', guideBodyKey: 'panels.book-settings.guideBody', tourAnchor: 'studio-book-settings-panel' },
  // 17_...docks.md — Translation: coverage matrix, language filter, bulk translate/extract.
  // translation-versions is a params-retargeting singleton ({chapterId, lang}, json-editor/
  // original-source precedent) opened only from the matrix's per-cell click — hidden from
  // palette + outside the agent enum (meaningless without a chapterId).
  { id: 'translation', component: TranslationPanel, titleKey: 'panels.translation.title', descKey: 'panels.translation.desc', category: 'translation', guideBodyKey: 'panels.translation.guideBody', tourAnchor: 'studio-translation-panel' },
  { id: 'translation-versions', component: TranslationVersionsPanel, titleKey: 'panels.translation-versions.title', descKey: 'panels.translation-versions.desc', hiddenFromPalette: true, guideBodyKey: 'panels.translation-versions.guideBody' },
  // 16_chapter_editor_parity_and_retirement.md Phase 3 — the block-aligned review workspace
  // (legacy TranslationReviewPage), a params-retargeting singleton ({bookId, chapterId,
  // versionId}) opened only from TranslationViewer's "Review" button (DOCK-7 fix) — hidden from
  // palette + outside the agent enum (meaningless without a versionId).
  { id: 'translation-review', component: TranslationReviewPanel, titleKey: 'panels.translation-review.title', descKey: 'panels.translation-review.desc', hiddenFromPalette: true, guideBodyKey: 'panels.translation-review.guideBody' },
  // 17_...docks.md — Lore Enrichment: EnrichmentView's former 6-way internal tab switch
  // (DOCK-8 anti-pattern) becomes 6 sibling panels, no hub — each independently
  // palette + agent openable, mirroring the kg-* panels' shape.
  { id: 'enrichment-compose', component: EnrichmentComposePanel, titleKey: 'panels.enrichment-compose.title', descKey: 'panels.enrichment-compose.desc', category: 'enrichment', guideBodyKey: 'panels.enrichment-compose.guideBody', tourAnchor: 'studio-enrichment-compose-panel' },
  { id: 'enrichment-proposals', component: EnrichmentProposalsPanel, titleKey: 'panels.enrichment-proposals.title', descKey: 'panels.enrichment-proposals.desc', category: 'enrichment', guideBodyKey: 'panels.enrichment-proposals.guideBody' },
  { id: 'enrichment-gaps', component: EnrichmentGapsPanel, titleKey: 'panels.enrichment-gaps.title', descKey: 'panels.enrichment-gaps.desc', category: 'enrichment', guideBodyKey: 'panels.enrichment-gaps.guideBody', tourAnchor: 'studio-enrichment-gaps-panel' },
  { id: 'enrichment-sources', component: EnrichmentSourcesPanel, titleKey: 'panels.enrichment-sources.title', descKey: 'panels.enrichment-sources.desc', category: 'enrichment', guideBodyKey: 'panels.enrichment-sources.guideBody', tourAnchor: 'studio-enrichment-sources-panel' },
  { id: 'enrichment-jobs', component: EnrichmentJobsPanel, titleKey: 'panels.enrichment-jobs.title', descKey: 'panels.enrichment-jobs.desc', category: 'enrichment', guideBodyKey: 'panels.enrichment-jobs.guideBody' },
  { id: 'enrichment-settings', component: EnrichmentSettingsPanel, titleKey: 'panels.enrichment-settings.title', descKey: 'panels.enrichment-settings.desc', category: 'enrichment', guideBodyKey: 'panels.enrichment-settings.guideBody' },
  // 19_onboarding_and_user_guide.md Wave 1 — catalog-driven help: renders every openable panel
  // above, grouped by #18's category, using descKey as the guide body (Wave 2 adds dedicated
  // guideBodyKey copy per panel). Palette + agent openable like any other panel.
  { id: 'user-guide', component: UserGuidePanel, titleKey: 'panels.user-guide.title', descKey: 'panels.user-guide.desc', category: 'platform', guideBodyKey: 'panels.user-guide.guideBody' },
  // 20_agent_mode.md D1/D2 — Agent Mode mission control + its diff-panel wrapper.
  // `agent-mode` is palette+agent-openable (D1) — added 'agent-mode' to
  // chat-service's `ui_open_studio_panel` panel_id enum + regenerated
  // contracts/frontend-tools.contract.json so panelCatalogContract.test.ts's
  // palette-openable-set === backend-enum check stays green. Still also
  // reachable via the `planner` panel's "Autonomous Agent Runs" link.
  // `chapter-revision-compare` is a params-retargeting singleton (json-editor/
  // wiki-editor/translation-versions precedent) — meaningless without a
  // chapterId, so it stays hidden regardless, same as those panels.
  { id: 'agent-mode', component: AgentModePanel, titleKey: 'panels.agent-mode.title', descKey: 'panels.agent-mode.desc', category: 'editor', guideBodyKey: 'panels.agent-mode.guideBody' },
  { id: 'chapter-revision-compare', component: ChapterRevisionComparePanel, titleKey: 'panels.chapter-revision-compare.title', descKey: 'panels.chapter-revision-compare.desc', hiddenFromPalette: true, guideBodyKey: 'panels.chapter-revision-compare.guideBody' },
  // Quality tab (docs/plans/2026-07-06-studio-quality-tab.md) — DOCK-8 hub +
  // sibling panels, same shape as `knowledge`/kg-*: promise ledger, per-chapter
  // critic scores, book-wide promise coverage, and canon issues are 4 distinct
  // data sources, not one monolithic tabbed panel. All palette + agent openable
  // (added to chat-service's ui_open_studio_panel enum + regenerated
  // contracts/frontend-tools.contract.json).
  { id: 'quality', component: QualityHubPanel, titleKey: 'panels.quality.title', descKey: 'panels.quality.desc', category: 'quality', guideBodyKey: 'panels.quality.guideBody', tourAnchor: 'studio-quality-hub-panel' },
  { id: 'quality-promises', component: QualityPromisesPanel, titleKey: 'panels.quality-promises.title', descKey: 'panels.quality-promises.desc', category: 'quality', guideBodyKey: 'panels.quality-promises.guideBody' },
  { id: 'quality-critic', component: QualityCriticPanel, titleKey: 'panels.quality-critic.title', descKey: 'panels.quality-critic.desc', category: 'quality', guideBodyKey: 'panels.quality-critic.guideBody' },
  { id: 'quality-coverage', component: QualityCoveragePanel, titleKey: 'panels.quality-coverage.title', descKey: 'panels.quality-coverage.desc', category: 'quality', guideBodyKey: 'panels.quality-coverage.guideBody' },
  { id: 'quality-canon', component: QualityCanonPanel, titleKey: 'panels.quality-canon.title', descKey: 'panels.quality-canon.desc', category: 'quality', guideBodyKey: 'panels.quality-canon.guideBody' },
  { id: 'welcome', component: WelcomePanel, titleKey: 'welcome.tab', descKey: 'welcome.tab', hiddenFromPalette: true, guideBodyKey: 'panels.welcome.guideBody' },

  // ═══════════════════════════════════════════════════════════════════════════
  // WRITING-STUDIO COMPLETENESS — the 8-session build (2026-07-16 orchestration).
  // Each session adds its panels IN ITS OWN BLOCK below, so two sessions editing
  // this file concurrently touch different line-ranges. Registration is not done
  // until the row is here AND in chat-service's `ui_open_studio_panel` enum AND in
  // contracts/frontend-tools.contract.json (regen: WRITE_FRONTEND_CONTRACT=1 pytest)
  // AND has an `en` i18n guideBodyKey. Keep enum == openable == contract in sync.
  // Panel-id ledger + per-session ownership: docs/plans/2026-07-16-studio-completeness-8-session-orchestration.md §4/§8.0
  // ───────────────────────────────────────────────────────────────────────────
  // ── S1 · Manuscript & Compose ──  (scene-compose, chapter-assemble)
  { id: 'scene-compose', component: SceneComposePanel, titleKey: 'panels.scene-compose.title', descKey: 'panels.scene-compose.desc', category: 'editor', guideBodyKey: 'panels.scene-compose.guideBody', tourAnchor: 'studio-scene-compose-panel' }, /* owner: S1 */
  { id: 'chapter-assemble', component: ChapterAssemblePanel, titleKey: 'panels.chapter-assemble.title', descKey: 'panels.chapter-assemble.desc', category: 'editor', guideBodyKey: 'panels.chapter-assemble.guideBody', tourAnchor: 'studio-chapter-assemble-panel' }, /* owner: S1 */
  // ── S2 · Plan & Structure ──      (arc-inspector, arc-templates)
  { id: 'arc-inspector', component: ArcInspectorPanel, titleKey: 'panels.arc-inspector.title', descKey: 'panels.arc-inspector.desc', category: 'editor', guideBodyKey: 'panels.arc-inspector.guideBody' }, /* owner: S2 */
  { id: 'arc-templates', component: ArcTemplatesPanel, titleKey: 'panels.arc-templates.title', descKey: 'panels.arc-templates.desc', category: 'storyBible', guideBodyKey: 'panels.arc-templates.guideBody' }, /* owner: S2 */
  // ── S3 · PlanForge ──             (plan-passes)
  // ── S4 · Motif & craft ──         (motif-library, quality-conformance)
  { id: 'motif-library', component: MotifLibraryPanel, titleKey: 'panels.motif-library.title', descKey: 'panels.motif-library.desc', category: 'storyBible', guideBodyKey: 'panels.motif-library.guideBody' },
  { id: 'quality-conformance', component: QualityConformancePanel, titleKey: 'panels.quality-conformance.title', descKey: 'panels.quality-conformance.desc', category: 'quality', guideBodyKey: 'panels.quality-conformance.guideBody' },
  // ── S5 · What-If & Divergence ──  (divergence, + canonview home)
  { id: 'divergence', component: DivergencePanel, titleKey: 'panels.divergence.title', descKey: 'panels.divergence.desc', category: 'editor', guideBodyKey: 'panels.divergence.guideBody' }, /* owner: S5 */
  // ── S6 · Canon/Quality/Progress ──(quality-canon-rules, quality-corrections, quality-heal, progress, + flywheel home)
  { id: 'quality-canon-rules', component: QualityCanonRulesPanel, titleKey: 'panels.quality-canon-rules.title', descKey: 'panels.quality-canon-rules.desc', category: 'quality', guideBodyKey: 'panels.quality-canon-rules.guideBody' },
  { id: 'quality-corrections', component: QualityCorrectionsPanel, titleKey: 'panels.quality-corrections.title', descKey: 'panels.quality-corrections.desc', category: 'quality', guideBodyKey: 'panels.quality-corrections.guideBody' },
  { id: 'quality-heal', component: QualityHealPanel, titleKey: 'panels.quality-heal.title', descKey: 'panels.quality-heal.desc', category: 'quality', guideBodyKey: 'panels.quality-heal.guideBody' },
  { id: 'progress', component: ProgressStudioPanel, titleKey: 'panels.progress.title', descKey: 'panels.progress.desc', category: 'editor', guideBodyKey: 'panels.progress.guideBody' },
  // ── S7 · Knowledge/World/Cast ──  (world, world-map, place-graph, cast, character-arc)
  { id: 'world-map', component: WorldMapEditorPanel, titleKey: 'panels.world-map.title', descKey: 'panels.world-map.desc', category: 'storyBible', guideBodyKey: 'panels.world-map.guideBody' }, /* owner: S7 (Group B) */
  { id: 'place-graph', component: PlaceGraphPanel, titleKey: 'panels.place-graph.title', descKey: 'panels.place-graph.desc', category: 'storyBible', guideBodyKey: 'panels.place-graph.guideBody' }, /* owner: S7 (Group C) — OQ-5: storyBible, not 'knowledge' */
  { id: 'cast', component: CastPanel, titleKey: 'panels.cast.title', descKey: 'panels.cast.desc', category: 'storyBible', guideBodyKey: 'panels.cast.guideBody' }, /* owner: S7 (Group A) */
  { id: 'character-arc', component: CharacterArcPanel, titleKey: 'panels.character-arc.title', descKey: 'panels.character-arc.desc', category: 'storyBible', guideBodyKey: 'panels.character-arc.guideBody' }, /* owner: S7 (Group A) */
  // ── S8 · Translation ──           (translation-repair)
  // ═══════════════════════════════════════════════════════════════════════════
];

/** dockview component map (id → component) for StudioDock. */
export const STUDIO_PANEL_COMPONENTS: Record<string, FunctionComponent<IDockviewPanelProps>> =
  Object.fromEntries(STUDIO_PANELS.map((p) => [p.id, p.component]));

/** Panels offered in the Command Palette "Open" group. */
export const OPENABLE_STUDIO_PANELS = STUDIO_PANELS.filter((p) => !p.hiddenFromPalette);

export function getStudioPanelDef(id: string): StudioPanelDef | undefined {
  return STUDIO_PANELS.find((p) => p.id === id);
}
