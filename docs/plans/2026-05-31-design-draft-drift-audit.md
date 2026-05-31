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

**PO ruling 2026-05-31: the drafts are mostly EXTENSIONS / facets, not competing
drift versions.** So the audit reframes: find (a) designed extensions NOT built
live → *supplement*, (b) genuine divergences → *drift/fix*, (c) outdated drafts
→ *archive*. Per-cluster PO decisions:

| Feature | PO decision | Audit implication |
|---|---|---|
| **Editor (7)** | NOT competing versions — 3 facets of one feature (modes/classic/mixed-media). The AI-chat panel (splitview/workbench) is **NOT rejected** — it must be **reworked to REUSE the existing canonical Chat component** (chat page), *not* recoded. "Don't rebuild what already exists and is better." (= ARCH-1 framing: reuse, not rebuild.) | Verify mode-facets built; AI-panel = ARCH-1 reuse task (separate). version-history = built. |
| **Reader (6)** | v2 is an **EXTENSION** of v1, not a replacement: v1 = text-only support, v2 = rich features (renderer/audio-tts/review-modes/audio-blocks). | Check each v2 part actually built live; `reader-social` likely not built → supplement candidate. |
| **Translation (3)** | EXTENSIONS — 3 distinct screens (matrix / chapter-translations viewer / workbench block-review), not drift. | Verify all 3 exist + work (largely confirmed during i18n W8b). |
| **Glossary (6)** | **Suspected OUTDATED drafts** — PO recalls glossary expanded a lot live (lots of settings) → live is likely AHEAD of the drafts. | Confirm live richness vs draft; archive outdated drafts; low fix-value (live ahead). |
| **Components (2)** | `00. components-v2-warm` = **current**; `components-v2` = outdated. | Archive `components-v2`. |

### Live-classification log (fill during compare)

#### Reader (audited 2026-05-31) — code/wiring level

ReaderPage wires: `ContentRenderer`, `TOCSidebar`, `ThemeCustomizer`, `TTSBar`,
`TTSSettings`, `useTTS`, `useBlockScroll`, `useTTSShortcuts`, `useReadingTracker`,
translation-version reading (`versionsApi`). Blocks live: Paragraph, Heading,
Blockquote, Callout, Code, HorizontalRule, List, Image, Video, Audio (+ Inline).

| Draft | Live status | Verdict | Action |
|---|---|---|---|
| `screen-reader.html` (v1, text-only) | superseded — live renders rich v2 | **OUTDATED** | archive v1 draft |
| `reader-v2-part1-renderer` | **BUILT** — `ContentRenderer` + all 10 block types + themes + top bar, wired in ReaderPage | OK | none |
| `reader-v2-part2-audio-tts` | **BUILT (verify depth)** — `TTSBar`/`TTSSettings`/`useTTS`/`useBlockScroll` + active-block highlight + auto-scroll wired. *Verify live:* AI-TTS mode (vs browser) + "audio drifted" asset state | OK / ⚠️verify | live-run TTS |
| `reader-v2-part3-review-modes` | **BUILT** — this is the translation block-aligned review = `TranslationReviewPage`/`BlockAlignedReview` (cross-feature, not reader-only) | OK | none |
| `reader-v2-part4-audio-blocks` | **⚠️ PARTIAL?** — `AudioBlock` + `AudioGenerationCard` + `AudioOverview` exist; the per-block *attach recorded audio + subtitle + audio↔text mismatch* detection needs live confirmation | ⚠️verify | live-run audio attach |
| `reader-social` (ratings/reviews/comments/tag-vote/favorites) | **NOT BUILT** — no rating/review system (matches UI-2b DROP). | **DEFERRED post-MVP (PO 2026-05-31)** — not shipping in MVP; keep draft as future spec | none now |
| `screen-theme-customizer` | **BUILT** — `ThemeCustomizer` wired (app+reader themes, fonts, spacing, presets) | OK | none |

**Reader summary:** core rich reader (render + TTS + theme + translation review)
is built & wired. `reader-social` deferred post-MVP (PO). v1 draft = archive.

**LIVE-VERIFIED 2026-05-31 (Playwright + PO real browser):**
- Render: full chapter renders as blocks, header/footer/progress, i18n (ja),
  read-time estimate ("約25分で読了", "5,695 語"), **0 console errors**. ✅
- TTS: clicking 読み上げ starts playback — bar shows prev/pause/next, active-block
  highlight, mode=**ブラウザ**, speed 1x, **自動スクロール:オン** (UI-3b). PO confirms
  **audio actually plays** on real Chrome. ✅
- TTS設定 panel: speed slider, browser-voice select, **AI-TTS-model select**,
  behavior toggles, now-playing — part2 fully built. ✅
- **CONFIG GAP (not code):** AI-TTS dropdown = *"モデルが設定されていません"* — the
  running `local-tts-service` (:9880, 55 kokoro/piper voices) is **not registered
  as a TTS model** in provider-registry → AI voices unusable until added in
  Settings > Providers. Same class as the LLM-402: service up, not wired to the
  model registry. (Headless chromium also lacks Web Speech voices — expected; PO's
  real browser has them.)
- part4 per-block audio attach/subtitle/mismatch: components exist
  (`AudioBlock`/`AudioGenerationCard`); depth not deep-verified this pass (low
  priority — niche authoring feature).

**Reader verdict: GREEN (built & works live).** No real drift. Actionable items:
(1) register local-tts-service as a TTS model so AI voices work [config],
(2) archive `reader.html` v1 draft, (3) `reader-social` deferred post-MVP.

---

| Feature | Canonical draft | Diff vs live | Verdict (SUPPLEMENT/DRIFT/INTENTIONAL/OUTDATED) | Action |
|---|---|---|---|---|
| _(other clusters tbd)_ | | | | |

---

## 4. Live-run checklist (step 5 — per feature, after classify)

For each feature kept in scope, verify on the running stack (the worker lesson):
container(s) alive + has restart policy · the action actually produces output
(not 402/fallback/empty) · no console/network errors. Record pass/fail + the
"needs fix / needs supplement" list here.

| Feature | Runs live? | Needs fix / supplement |
|---|---|---|
| _(tbd)_ | | |
