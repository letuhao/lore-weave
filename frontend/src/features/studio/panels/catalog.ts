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
import { EditorPanel } from './EditorPanel';
import { PlannerPanel } from '@/features/plan-forge/components/PlannerPanel';
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
import { ContextInspectorPanel } from './ContextInspectorPanel';
import { MediaVersionHistoryPanel } from './MediaVersionHistoryPanel';
import { OriginalSourcePanel } from './OriginalSourcePanel';
import { SharingPanel } from './SharingPanel';
import { BookSettingsPanel } from './BookSettingsPanel';
import { TranslationPanel } from './TranslationPanel';
import { TranslationVersionsPanel } from './TranslationVersionsPanel';
import { EnrichmentComposePanel } from './EnrichmentComposePanel';
import { EnrichmentProposalsPanel } from './EnrichmentProposalsPanel';
import { EnrichmentGapsPanel } from './EnrichmentGapsPanel';
import { EnrichmentSourcesPanel } from './EnrichmentSourcesPanel';
import { EnrichmentJobsPanel } from './EnrichmentJobsPanel';
import { EnrichmentSettingsPanel } from './EnrichmentSettingsPanel';

/** #18 — domain-area grouping for the Command Palette. Required for every non-hidden panel
 *  (enforced at runtime by panelCatalogContract.test.ts — B6, not just a convention). */
export type StudioPanelCategory =
  | 'editor'
  | 'storyBible'
  | 'knowledge'
  | 'translation'
  | 'enrichment'
  | 'sharing'
  | 'platform'
  | 'discovery'
  | 'jobs';

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
}

export const STUDIO_PANELS: StudioPanelDef[] = [
  { id: 'compose', component: ComposePanel, titleKey: 'panels.compose.title', descKey: 'panels.compose.desc', category: 'editor' },
  { id: 'editor', component: EditorPanel, titleKey: 'panels.editor.title', descKey: 'panels.editor.desc', category: 'editor' },
  { id: 'planner', component: PlannerPanel, titleKey: 'panels.planner.title', descKey: 'panels.planner.desc', category: 'editor' },
  // #11 W2 — user-scoped panels (dockable migration wave 1).
  { id: 'usage', component: UsagePanel, titleKey: 'panels.usage.title', descKey: 'panels.usage.desc', category: 'platform' },
  { id: 'notifications', component: NotificationsPanel, titleKey: 'panels.notifications.title', descKey: 'panels.notifications.desc', category: 'platform' },
  { id: 'settings', component: SettingsPanel, titleKey: 'panels.settings.title', descKey: 'panels.settings.desc', category: 'platform' },
  { id: 'trash', component: TrashPanel, titleKey: 'panels.trash.title', descKey: 'panels.trash.desc', category: 'platform' },
  // RAID C1 — per-book author steering rules (story-bible-as-steering). book-scoped, palette-openable.
  { id: 'steering', component: SteeringPanel, titleKey: 'panels.steering.title', descKey: 'panels.steering.desc', category: 'editor' },
  // #13 A3 — entity list/search/filter/bulk-actions (cycle-2 of the #12 per-tool queue).
  // Palette + agent openable (panelCatalogContract enforces openable-set == enum, so any
  // palette-visible panel must join `ui_open_studio_panel` — see frontend_tools.py + the
  // regenerated contracts/frontend-tools.contract.json).
  { id: 'glossary', component: GlossaryPanel, titleKey: 'panels.glossary.title', descKey: 'panels.glossary.desc', category: 'storyBible' },
  // 13_glossary_panels.md Phase B — the 4 capabilities GlossaryPanel used to internally
  // view-switch (a DOCK-8 exception) are now real sibling dock panels. Each is palette + agent
  // openable (panelCatalogContract enforces openable-set == enum) and reachable from the
  // `glossary` panel's own launcher buttons via host.openPanel — never a local view flag.
  { id: 'glossary-ontology', component: GlossaryOntologyPanel, titleKey: 'panels.glossary-ontology.title', descKey: 'panels.glossary-ontology.desc', category: 'storyBible' },
  { id: 'glossary-unknown', component: GlossaryUnknownPanel, titleKey: 'panels.glossary-unknown.title', descKey: 'panels.glossary-unknown.desc', category: 'storyBible' },
  { id: 'glossary-ai-suggestions', component: GlossaryAiSuggestionsPanel, titleKey: 'panels.glossary-ai-suggestions.title', descKey: 'panels.glossary-ai-suggestions.desc', category: 'storyBible' },
  { id: 'glossary-merge-candidates', component: GlossaryMergeCandidatesPanel, titleKey: 'panels.glossary-merge-candidates.title', descKey: 'panels.glossary-merge-candidates.desc', category: 'storyBible' },
  // 15_wiki_panels.md B1 — the wiki master-detail workspace (DOCK-2, same shared component the
  // classic WikiTab page renders). Palette + agent openable.
  { id: 'wiki', component: WikiPanel, titleKey: 'panels.wiki.title', descKey: 'panels.wiki.desc', category: 'storyBible' },
  // 15_wiki_panels.md B2 — params-retargeting singleton ({articleId, rightPanel?}), same
  // precedent as book-reader/json-editor/skill-editor: hidden from palette + outside the agent
  // enum (opened only via the `wiki` panel's Edit/History buttons — no wiki_* MCP tool exists
  // yet for an agent to target it with).
  { id: 'wiki-editor', component: WikiEditorPanel, titleKey: 'panels.wiki-editor.title', descKey: 'panels.wiki-editor.desc', hiddenFromPalette: true },
  // 14_kg_panels.md A2 — the KG launcher (DOCK-8 hub pattern): browse/open knowledge-graph
  // projects. Phase B adds the capability panels it currently opens via a new-tab fallback.
  { id: 'knowledge', component: KnowledgeHubPanel, titleKey: 'panels.knowledge.title', descKey: 'panels.knowledge.desc', category: 'knowledge' },
  // 14_kg_panels.md Phase B — the 12 KG capability panels the `knowledge` hub launcher
  // opens (today via a new-tab fallback until each lands; landing here makes it in-tab).
  // overview/gap/proposals/schema/graph are book-scoped (useBookKnowledgeProject);
  // entities/timeline/evidence take an optional params.scopedProjectId (K4, shared scope);
  // insights/jobs/bio/privacy are user-scoped (global, cross-book — same tier as usage/settings).
  { id: 'kg-overview', component: KgOverviewPanel, titleKey: 'panels.kg-overview.title', descKey: 'panels.kg-overview.desc', category: 'knowledge' },
  { id: 'kg-entities', component: KgEntitiesPanel, titleKey: 'panels.kg-entities.title', descKey: 'panels.kg-entities.desc', category: 'knowledge' },
  { id: 'kg-timeline', component: KgTimelinePanel, titleKey: 'panels.kg-timeline.title', descKey: 'panels.kg-timeline.desc', category: 'knowledge' },
  { id: 'kg-evidence', component: KgEvidencePanel, titleKey: 'panels.kg-evidence.title', descKey: 'panels.kg-evidence.desc', category: 'knowledge' },
  { id: 'kg-gap', component: KgGapReportPanel, titleKey: 'panels.kg-gap.title', descKey: 'panels.kg-gap.desc', category: 'knowledge' },
  { id: 'kg-proposals', component: KgProposalsPanel, titleKey: 'panels.kg-proposals.title', descKey: 'panels.kg-proposals.desc', category: 'knowledge' },
  { id: 'kg-schema', component: KgSchemaPanel, titleKey: 'panels.kg-schema.title', descKey: 'panels.kg-schema.desc', category: 'knowledge' },
  { id: 'kg-graph', component: KgGraphPanel, titleKey: 'panels.kg-graph.title', descKey: 'panels.kg-graph.desc', category: 'knowledge' },
  { id: 'kg-insights', component: KgInsightsPanel, titleKey: 'panels.kg-insights.title', descKey: 'panels.kg-insights.desc', category: 'knowledge' },
  { id: 'kg-jobs', component: KgJobsPanel, titleKey: 'panels.kg-jobs.title', descKey: 'panels.kg-jobs.desc', category: 'knowledge' },
  { id: 'kg-bio', component: KgGlobalBioPanel, titleKey: 'panels.kg-bio.title', descKey: 'panels.kg-bio.desc', category: 'knowledge' },
  { id: 'kg-privacy', component: KgPrivacyPanel, titleKey: 'panels.kg-privacy.title', descKey: 'panels.kg-privacy.desc', category: 'knowledge' },
  // 14_utility_panels.md Phase B — jobs-list is palette + agent openable; job-detail is a
  // params-retargeting singleton ({service, jobId}, json-editor/skill-editor precedent).
  { id: 'jobs-list', component: JobsListPanel, titleKey: 'panels.jobs-list.title', descKey: 'panels.jobs-list.desc', category: 'jobs' },
  { id: 'job-detail', component: JobDetailPanel, titleKey: 'panels.job-detail.title', descKey: 'panels.job-detail.desc', hiddenFromPalette: true },
  // 14_utility_panels.md Phase C — browse-then-read, no navigate-away: books lists the user's
  // OTHER books; book-reader is a params-retargeting singleton ({bookId, chapterId?}) opened via
  // host.openPanel from a books row click, never a route hop (the active studio never unmounts).
  { id: 'books', component: BooksBrowserPanel, titleKey: 'panels.books.title', descKey: 'panels.books.desc', category: 'discovery' },
  { id: 'book-reader', component: BookReaderPanel, titleKey: 'panels.book-reader.title', descKey: 'panels.book-reader.desc', hiddenFromPalette: true },
  // 14_utility_panels.md Phase D — the global leaderboard's 4-tab internal view-switch (DOCK-8
  // anti-pattern) becomes 4 sibling panels; each owns independent filter state.
  { id: 'leaderboard-books', component: LeaderboardBooksPanel, titleKey: 'panels.leaderboard-books.title', descKey: 'panels.leaderboard-books.desc', category: 'discovery' },
  { id: 'leaderboard-authors', component: LeaderboardAuthorsPanel, titleKey: 'panels.leaderboard-authors.title', descKey: 'panels.leaderboard-authors.desc', category: 'discovery' },
  { id: 'leaderboard-translators', component: LeaderboardTranslatorsPanel, titleKey: 'panels.leaderboard-translators.title', descKey: 'panels.leaderboard-translators.desc', category: 'discovery' },
  { id: 'leaderboard-trending', component: LeaderboardTrendingPanel, titleKey: 'panels.leaderboard-trending.title', descKey: 'panels.leaderboard-trending.desc', category: 'discovery' },
  // 15_chapter_browser.md — table/search surface for triage at scale (sort/filter/
  // multi-select bulk actions + a Title-vs-Content search-mode toggle), sibling to
  // the Manuscript Navigator (tree, for writing) not a replacement for it.
  { id: 'chapter-browser', component: ChapterBrowserPanel, titleKey: 'panels.chapter-browser.title', descKey: 'panels.chapter-browser.desc', category: 'editor' },
  // Context Budget Law §11 — the Context Compiler · Trace Inspector: per-turn context-build
  // observability (budget gauge · allocation map · Planner→Compiler waterfall). Palette + agent
  // openable (panelCatalogContract enforces openable-set == the ui_open_studio_panel enum);
  // self-contained (lists sessions + picks one), so it needs no book/studio context.
  { id: 'context-inspector', component: ContextInspectorPanel, titleKey: 'panels.context-inspector.title', descKey: 'panels.context-inspector.desc', category: 'editor' },
  // Agent Extensibility Registry (§13b) — extensions hub + proposals inbox are
  // palette-openable + in the agent enum; skill-editor is a params-retargeting
  // singleton (json-editor precedent), hidden from palette + outside the enum.
  { id: 'extensions', component: ExtensionsPanel, titleKey: 'panels.extensions.title', descKey: 'panels.extensions.desc', category: 'platform' },
  { id: 'proposals', component: ProposalsPanel, titleKey: 'panels.proposals.title', descKey: 'panels.proposals.desc', category: 'platform' },
  { id: 'skill-editor', component: SkillEditorPanel, titleKey: 'panels.skill-editor.title', descKey: 'panels.skill-editor.desc', hiddenFromPalette: true },
  // #12 R3/R4 — singleton, retargets via params {docType, resourceId}; opened by "Open as JSON"
  // affordances only (hidden from palette ⇒ outside the agent enum, no contract change this cycle).
  { id: 'json-editor', component: JsonEditorPanel, titleKey: 'panels.json-editor.title', descKey: 'panels.json-editor.desc', hiddenFromPalette: true },
  // #16 Phase 2 (2.7) — per-resource retargeting singleton (json-editor precedent), opened
  // only from the "history" button inside an image/video NodeView. hiddenFromPalette + outside
  // the agent enum — no contract change this cycle.
  { id: 'media-version-history', component: MediaVersionHistoryPanel, titleKey: 'panels.media-version-history.title', descKey: 'panels.media-version-history.desc', hiddenFromPalette: true },
  // #16 Phase 2 (2.11) — read-only original-source viewer, retargets via params
  // {bookId, chapterId}; opened only from EditorPanel's toolbar (json-editor precedent),
  // hidden from palette + outside the agent enum.
  { id: 'original-source', component: OriginalSourcePanel, titleKey: 'panels.original-source.title', descKey: 'panels.original-source.desc', hiddenFromPalette: true },
  // 17_translation_enrichment_sharing_settings_docks.md — Book Sharing: visibility
  // radio-cards, unlisted-link+rotate, collaborator invite/role-change/remove. DOCK-7/DOCK-9
  // were already clean on the classic page — no navigate/Link, no hand-rolled overlays.
  { id: 'sharing', component: SharingPanel, titleKey: 'panels.sharing.title', descKey: 'panels.sharing.desc', category: 'sharing' },
  // 17_...docks.md — Book Settings: title/description/language/summary, cover image, genre
  // tags, world link. Named `book-settings` (not `settings`) to avoid colliding with the
  // existing user-level account/providers/translation panel id.
  { id: 'book-settings', component: BookSettingsPanel, titleKey: 'panels.book-settings.title', descKey: 'panels.book-settings.desc', category: 'sharing' },
  // 17_...docks.md — Translation: coverage matrix, language filter, bulk translate/extract.
  // translation-versions is a params-retargeting singleton ({chapterId, lang}, json-editor/
  // original-source precedent) opened only from the matrix's per-cell click — hidden from
  // palette + outside the agent enum (meaningless without a chapterId).
  { id: 'translation', component: TranslationPanel, titleKey: 'panels.translation.title', descKey: 'panels.translation.desc', category: 'translation' },
  { id: 'translation-versions', component: TranslationVersionsPanel, titleKey: 'panels.translation-versions.title', descKey: 'panels.translation-versions.desc', hiddenFromPalette: true },
  // 17_...docks.md — Lore Enrichment: EnrichmentView's former 6-way internal tab switch
  // (DOCK-8 anti-pattern) becomes 6 sibling panels, no hub — each independently
  // palette + agent openable, mirroring the kg-* panels' shape.
  { id: 'enrichment-compose', component: EnrichmentComposePanel, titleKey: 'panels.enrichment-compose.title', descKey: 'panels.enrichment-compose.desc', category: 'enrichment' },
  { id: 'enrichment-proposals', component: EnrichmentProposalsPanel, titleKey: 'panels.enrichment-proposals.title', descKey: 'panels.enrichment-proposals.desc', category: 'enrichment' },
  { id: 'enrichment-gaps', component: EnrichmentGapsPanel, titleKey: 'panels.enrichment-gaps.title', descKey: 'panels.enrichment-gaps.desc', category: 'enrichment' },
  { id: 'enrichment-sources', component: EnrichmentSourcesPanel, titleKey: 'panels.enrichment-sources.title', descKey: 'panels.enrichment-sources.desc', category: 'enrichment' },
  { id: 'enrichment-jobs', component: EnrichmentJobsPanel, titleKey: 'panels.enrichment-jobs.title', descKey: 'panels.enrichment-jobs.desc', category: 'enrichment' },
  { id: 'enrichment-settings', component: EnrichmentSettingsPanel, titleKey: 'panels.enrichment-settings.title', descKey: 'panels.enrichment-settings.desc', category: 'enrichment' },
  { id: 'welcome', component: WelcomePanel, titleKey: 'welcome.tab', descKey: 'welcome.tab', hiddenFromPalette: true },
];

/** dockview component map (id → component) for StudioDock. */
export const STUDIO_PANEL_COMPONENTS: Record<string, FunctionComponent<IDockviewPanelProps>> =
  Object.fromEntries(STUDIO_PANELS.map((p) => [p.id, p.component]));

/** Panels offered in the Command Palette "Open" group. */
export const OPENABLE_STUDIO_PANELS = STUDIO_PANELS.filter((p) => !p.hiddenFromPalette);

export function getStudioPanelDef(id: string): StudioPanelDef | undefined {
  return STUDIO_PANELS.find((p) => p.id === id);
}
