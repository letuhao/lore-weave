# Plan — Design-Draft ↔ Live Drift Audit

- Document ID: LW-DRIFT-AUDIT
- Created: 2026-05-31
- Branch: `mvp-release-debt`
- Owner: PO (decisions) + Lead (audit execution)
- Premise: **status docs are unreliable** (the debt tracker claimed translator
  "SHIPPED" while the worker was dead). The HTML design drafts are *also*
  potentially unreliable — several features have **multiple draft versions** =
  the drafts themselves drifted / are outdated. So: compare each draft to the
  **live** implementation, and **the PO decides per item** whether a difference
  is (1) real drift to fix, (2) intentional/newer design, or (3) the HTML is
  outdated and should be archived. Where a feature has multiple drafts, the PO
  picks the canonical one first.

---

## Process (per the PO's instructions)

1. **Inventory** every `design-drafts/*.html` (below), grouped by feature, with
   **multi-version flagged**.
2. **Pick canonical draft** — for multi-version features, PO chooses which draft
   is the source of truth (others → archive/outdated).
3. **Compare draft ↔ live** — Lead diffs the canonical draft against the live
   page/component; lists concrete differences.
4. **PO classifies each diff**: `DRIFT` (fix live) · `INTENTIONAL` (live is the
   newer/right design — update/scrap the draft) · `OUTDATED-HTML` (archive draft).
5. **Run it** — live-exercise the feature on the running stack (not a status
   column) to confirm it actually works.
6. **Output** — a "needs fix / needs supplement" list with owners.

> Decisions table lives in §3; fill as we go. No code changes until a row is
> classified `DRIFT` by PO.

---

## 1. Draft inventory (45 files)

### 1.0 Non-screen (architecture / components / overviews) — context, not feature screens
| File | Kind |
|---|---|
| `00. components-v2-warm.html` | Design-system components (warm theme) — **multi-version w/** `components-v2.html` |
| `components-v2.html` | Design-system components |
| `agentic-ai-book-to-world-overview.html` | Overview / marketing |
| `loreweave-for-creators-overview.html` | Overview / marketing |
| `architecture-diagrams.html` | Architecture doc |
| `data-pipeline-architecture.html` | Architecture doc |
| `loreweave-technical-architecture-and-pipelines.html` | Architecture doc |

### 1.1 Editor — ⚠️ **7 drafts, heavy multi-version** (PO must pick canonical)
| Draft | Likely live counterpart |
|---|---|
| `screen-chapter-editor.html` | `pages/ChapterEditorPage.tsx` + `components/editor/*` |
| `screen-editor-classic.html` | classic mode (`hooks/useEditorMode.ts`) |
| `screen-editor-mixed-media.html` | AI/mixed-media mode |
| `screen-editor-modes.html` | the Classic/AI mode toggle (WA-1a) |
| `screen-editor-splitview.html` | split view (WA-1b territory → ARCH-1) |
| `screen-editor-workbench.html` | workbench layout (WA-1b territory → ARCH-1) |
| `screen-editor-version-history.html` | `components/editor/VersionHistoryPanel.tsx` |

### 1.2 Reader — ⚠️ **6 drafts, v1 vs v2 split** (PO must pick canonical)
| Draft | Likely live counterpart |
|---|---|
| `screen-reader.html` | `pages/ReaderPage.tsx` (v1 — superseded?) |
| `screen-reader-v2-part1-renderer.html` | `components/reader/ContentRenderer.tsx` |
| `screen-reader-v2-part2-audio-tts.html` | `components/reader/{TTSBar,TTSSettings,AudioOverview}.tsx` |
| `screen-reader-v2-part3-review-modes.html` | review modes |
| `screen-reader-v2-part4-audio-blocks.html` | `components/reader/blocks/AudioBlock.tsx` |
| `screen-reader-social.html` | social reading (likely NOT built) |
| `screen-theme-customizer.html` | `components/reader/ThemeCustomizer.tsx` |

### 1.3 Chat — ⚠️ **3 drafts** (PO must pick canonical)
| Draft | Likely live counterpart |
|---|---|
| `screen-chat.html` | `pages/ChatPage.tsx` (base) |
| `screen-chat-enhanced.html` | enhanced chat (voice mode etc.) |
| `screen-chat-context.html` | `features/chat/context/ContextBar/ContextPicker` |

### 1.4 Translation — ⚠️ **3 drafts** (PO must pick canonical)
| Draft | Likely live counterpart |
|---|---|
| `screen-translation-matrix.html` | `pages/book-tabs/TranslationTab.tsx` (matrix) |
| `screen-chapter-translations.html` | `pages/ChapterTranslationsPage.tsx` (viewer) |
| `screen-translation-workbench.html` | `pages/TranslationReviewPage.tsx` (block review) |

### 1.5 Glossary / Entity / Genre — ⚠️ **6 drafts** (PO must pick canonical)
| Draft | Likely live counterpart |
|---|---|
| `screen-glossary-management.html` | `pages/book-tabs/GlossaryTab.tsx` |
| `screen-glossary-editor-integration.html` | `components/editor/Glossary{Panel,Tooltip,Autocomplete}.tsx` |
| `screen-entity-editor-v2.html` | `components/entity-editor/EntityEditorModal.tsx` (v2) |
| `screen-attr-editor-modal.html` | `pages/book-tabs/AttrEditorModal.tsx` |
| `screen-genre-groups.html` | `features/glossary/components/GenreGroupsPanel.tsx` |
| `glossary_extraction_ui_draft.html` | `features/extraction/ExtractionWizard.tsx` (old lowercase name → likely outdated) |

### 1.6 Wiki — 2 drafts (complementary, likely not drift)
| Draft | Likely live counterpart |
|---|---|
| `screen-wiki.html` | `pages/book-tabs/WikiTab.tsx` (viewer/list) |
| `screen-wiki-editor.html` | `pages/WikiEditorPage.tsx` |

### 1.7 Single-version screens (1:1 — low drift risk, still verify)
| Draft | Live counterpart |
|---|---|
| `screen-browse-catalog.html` | `pages/BrowsePage.tsx` + `features/browse/*` |
| `screen-public-book-detail.html` | `pages/PublicBookDetailPage.tsx` |
| `screen-notifications.html` | `pages/NotificationsPage.tsx` (UI-1, recently built) |
| `screen-leaderboard.html` | `pages/LeaderboardPage.tsx` |
| `screen-user-profile.html` | `pages/ProfilePage.tsx` |
| `screen-settings.html` | `pages/SettingsPage.tsx` + `features/settings/*` |
| `screen-model-editor.html` | `features/settings/{AddModelModal,EditModelModal}.tsx` |
| `screen-usage-monitor.html` | `pages/UsagePage.tsx` + `features/usage/*` |
| `screen-knowledge-service.html` | `pages/KnowledgePage.tsx` + `features/knowledge/*` |
| `screen-recycle-bin.html` | `pages/TrashPage.tsx` |

---

## 2. Multi-version features needing a PO canonical-pick FIRST

Before any compare, PO decides the source-of-truth draft (others → archive):

1. **Editor** (7 drafts) — chapter-editor / classic / mixed-media / modes /
   splitview / workbench / version-history. *Note:* splitview + workbench are
   the WA-1b in-editor-chat designs already rejected → ARCH-1; likely OUTDATED.
2. **Reader** (6 drafts) — `screen-reader.html` (v1) vs `reader-v2-part1..4`.
   v2 is split into 4 parts; v1 likely superseded. `reader-social` likely
   not-built.
3. **Chat** (3) — base / enhanced / context.
4. **Translation** (3) — matrix / chapter-translations / workbench.
5. **Glossary** (6) — management / editor-integration / entity-editor-v2 /
   attr-editor / genre-groups / extraction(old).
6. **Components** (2) — `components-v2` vs `00. components-v2-warm` (warm theme
   likely the current one).

---

## 3. Decisions log (fill as we go)

| Feature | Canonical draft (PO) | Diff vs live | PO verdict (DRIFT/INTENTIONAL/OUTDATED) | Action |
|---|---|---|---|---|
| _(tbd)_ | | | | |

---

## 4. Live-run checklist (step 5 — per feature, after classify)

For each feature kept in scope, verify on the running stack (the worker lesson):
container(s) alive + has restart policy · the action actually produces output
(not 402/fallback/empty) · no console/network errors. Record pass/fail + the
"needs fix / needs supplement" list here.

| Feature | Runs live? | Needs fix / supplement |
|---|---|---|
| _(tbd)_ | | |
