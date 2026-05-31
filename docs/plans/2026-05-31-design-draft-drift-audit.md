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

#### Glossary (audited 2026-05-31) — live in browser

Live GlossaryTab (richest book "封神演義 Lore Demo"): "11 entities · 9 kinds",
toolbar 抽出/ジャンル/種類/新エンティティ (Extract/Genre/Kinds/New), search+filter,
entity list (kind/status/chapter/evidence-count/delete). Entity editor (v2)
opens with tabs 属性/根拠/翻訳言語 (Attributes/Evidences/Translation-lang),
system+user attrs (name/aliases/description/...), status draft/active/inactive,
move-to-trash. = matches/exceeds the 6 glossary drafts (live is rich, PO was
right). No missing features.

| Draft | Live status | Verdict |
|---|---|---|
| `glossary-management` | BUILT — GlossaryTab + kinds editor (種類) + genre (ジャンル) | OK |
| `entity-editor-v2` | BUILT — `EntityEditorModal` (attrs/evidences/translations) | OK (had a live bug, fixed — see below) |
| `attr-editor-modal` | BUILT — `AttrEditorModal` | OK |
| `genre-groups` | BUILT — `GenreGroupsPanel` (i18n'd W9) | OK |
| `glossary-editor-integration` | BUILT — `GlossaryPanel/Tooltip/Autocomplete` (in-editor) | OK |
| `glossary_extraction_ui_draft` (old lowercase name) | superseded by `ExtractionWizard` | **OUTDATED** → archive draft |

🐛 **LIVE BUG FOUND + FIXED (2026-05-31): EntityEditorModal crashed on open.**
Clicking any entity threw *"Rendered more hooks than during the previous
render"* (React Rules-of-Hooks). Cause: `useMemo(availableLanguages)` +
`useCallback(handleTranslationChanged)` sat **after** two early returns
(`if (!entity && loading) return …` / `if (!entity) return null`). Entity loads
null→data, so the first render took the early return (fewer hooks) and the
post-load render ran the extra hooks → crash → **entity editor unusable**.
Static/i18n/tsc passes never caught it (TS doesn't check hook order; the unit
mock for react-i18next doesn't exercise the load sequence). Fix: hoisted both
hooks above the early returns, null-safe on `entity`. Verified live: editor now
opens clean, 0 console errors. **Meta-action:** enable
`react-hooks/rules-of-hooks` ESLint rule to catch this class pre-commit
(candidate — likely not running, else it'd have flagged).

**Glossary verdict: GREEN (built, live-verified) + 1 bug fixed.** Archive
`glossary_extraction_ui_draft`.

---

#### Rapid live console-error sweep (2026-05-31) — page-load crash check

Navigated every main screen logged-in (Playwright) and checked console errors
on load. **All 0 errors:**

| Screen | Errors |
|---|---|
| Chapter editor (`/…/edit`) | 0 |
| Chat (`/chat`) | 0 |
| Knowledge (`/knowledge`) | 0 |
| Settings — Providers (`/settings/providers`) | 0 |
| Usage (`/usage`) | 0 |
| Leaderboard (`/leaderboard`) | 0 |
| Notifications (`/notifications`) | 0 |
| Browse (`/browse`) | 0 |
| Translation matrix (`/…/translation`) | 0 |
| Chapter translations viewer (`/…/translations`) | 0 |
| Wiki tab (`/…/wiki`) | 0 |
| Profile (`/users/:id`) | 0 |
| Trash (`/trash`) | 0 |
| Book sharing / settings tabs | 0 |
| Reader (`/…/read`) + TTS | 0 |
| Glossary tab + **entity editor** | 0 *(after the hooks fix; was crashing)* |

**Caveat:** this is page-LOAD. The entity-editor crash was *interaction*-
triggered (clicking an entity) — so load-clean ≠ bug-free for modals/dialogs
opened by clicks. Exhaustively clicking every modal is impractical → see the
meta-finding below for the systematic catch.

#### META-FINDING — no ESLint in the project (root cause of the hook crash class)

`frontend/` has **no ESLint** (no `eslint.config.*`/`.eslintrc`, no eslint in
`package.json`). That's why the EntityEditorModal Rules-of-Hooks crash (and any
sibling conditional-hook bug) was never caught — TypeScript doesn't check hook
order, and there's no linter. **Recommendation (PO decision needed):** add a
minimal ESLint with `eslint-plugin-react-hooks`:
- `react-hooks/rules-of-hooks: "error"` — catches the *exact* crash class
  statically across ALL components (low noise; only fires on real violations).
- `react-hooks/exhaustive-deps: "warn"` — optional, noisier (would flag many
  existing `useCallback`/`useEffect` dep gaps, incl. some `t` deps).
This is the single highest-leverage fix to prevent recurrence of the live bug
just found. Tooling/L decision — not done unilaterally.

**✅ DONE (PO-approved 2026-05-31):** added `eslint` + `eslint-plugin-react-hooks`
+ `typescript-eslint`, minimal flat config (`eslint.config.js`) scoped to
**`react-hooks/rules-of-hooks: error`** only (exhaustive-deps left off). Added
`npm run lint`. The scan **immediately found a SECOND latent crash of the same
class**:
- 🐛 `features/chat/components/ThinkingBlock.tsx` — `useState` / `useRef`×2 /
  `useEffect`×2 all called **after** the `if (!reasoning && !isStreaming)
  return null` early return → would crash when an instance flips
  empty↔streaming. Fixed: hoisted all 5 hooks above the early return.
  tsc 0, chat tests 24/24, `eslint` exit 0.
(Also surfaced stale `// eslint-disable react-hooks/exhaustive-deps` comments
across the codebase → a prior eslint setup was removed at some point; silenced
via `reportUnusedDisableDirectives: off` for this focused pass.)

**Net: the live audit + ESLint found & fixed 2 real Rules-of-Hooks crashes
(EntityEditorModal, ThinkingBlock) that tsc + the unit suite never caught.**

---

#### Translation (audited 2026-05-31) — live in browser

Verified all 3 drafts on the running stack (matrix book = demo 封神演義 empty-state;
viewer/workbench book = Dracula 3c with a real vi translation, 2 versions).

| Draft | Live status | Verdict |
|---|---|---|
| `screen-translation-matrix` | **BUILT** — `TranslationTab`: 翻訳マトリックス, chapter×target-lang grid, per-cell status (完了), select-all, footer count, empty-state + 翻訳を開始 CTA. 0 console errors. | OK |
| `screen-chapter-translations` (viewer) | **BUILT** — `ChapterTranslationsPage`: lang selector (en 原文 / vi 2版), version selector (v1/v2 with 使用中 in-use badge + timestamps), 再翻訳/比較モード, ブロック(40), コピー/レビュー, full block render. 0 errors. | OK |
| `screen-translation-workbench` (block review) | **BUILT** — `TranslationReviewPage`/block-aligned: 戻る, en→vi, version combobox, "39/40 ブロック（1 件空）", すべて filter, 原文/翻訳 side-by-side block alignment w/ index+type tags. 0 errors. | OK |

**Translation verdict: GREEN (all 3 built & work live).** No drift. (Note: the
E2E test book's vi "translation" content mirrors the source — a test-data
artifact, not a UI bug; structure renders correctly.)

#### Chat (audited 2026-05-31) — live in browser

| Draft facet | Live status | Verdict |
|---|---|---|
| `screen-chat` (base) | **BUILT** — `ChatPage`: conversation list (会話/新規/search), date-grouped (昨日/それ以前), per-convo model + actions (ピン留め/名前変更/アーカイブ/削除), empty-state. | OK |
| `screen-chat-enhanced` | **BUILT** — thread render, 音声モード (voice mode), 音声設定, エクスポート, セッション設定, format selector (自動/簡潔/詳細/箇条書き/表), 熟考/高速 (thinking/fast) toggle, 音声入力 (STT), keyboard hints. | OK |
| `screen-chat-context` | **BUILT** — ナレッジインジケーター (knowledge scope = グローバル) + コンテキストを添付 (attach context). | OK |

**Chat verdict: GREEN (all 3 facets built & work live).** 0 console errors.
(The 熟考 thinking-mode reasoning stream renders via `ThinkingBlock` — the
component whose hook-order crash was fixed earlier this session.)

#### Editor (audited 2026-05-31) — live in browser

| Draft | Live status | Verdict |
|---|---|---|
| `screen-chapter-editor` | **BUILT** — `ChapterEditorPage`: title, TipTap rich editor (39 paragraphs), full toolbar (block types, marks, sub/sup, lists, quote, image/video/audio, code block, hr, undo/redo), char/word/paragraph counts, save-note, autosave status, status bar. | OK |
| `screen-editor-modes` / `-classic` / `-mixed-media` | **BUILT** — クラシック/AI mode toggle (WA-1a) wired in header. | OK |
| `screen-editor-version-history` | **BUILT** — right-panel 履歴 tab → リビジョン履歴 list (現在 + entries w/ note + timestamp + 表示). | OK |
| `screen-editor-splitview` / `-workbench` (in-editor AI chat) | **AIチャット tab present but DISABLED** — = **ARCH-1** (rework to reuse canonical Chat component, not rebuild). Deferred, not in this pass. | DEFERRED (ARCH-1) |

**Editor verdict: GREEN structurally** (all non-AI-panel facets built & render).
AI-panel = ARCH-1 (deferred). **BUT found a backend/console finding ↓.**

🔴 **EDITOR FINDING — LanguageTool grammar-check has NO backend (38 console 500s on every editor load).**
The grammar feature is fully wired on the FE (vite proxy `/languagetool` →
`http://localhost:8875`, `GrammarPlugin.ts` TipTap extension, `features/grammar/api.ts`
client with a graceful-degrade circuit breaker) — but **no LanguageTool service
is provisioned anywhere**: not in `infra/docker-compose.yml` (no `languagetool`
service, no `8875`), no running container, port 8875 actively refuses
connections. So the grammar toggle (文法・スペルチェック, **on by default**) fires on
editor load and every check 500s.

Two distinct issues:
1. **INFRA/CONFIG GAP (PO decision)** — same class as worker-down / TTS-unregistered
   / LLM-402: a feature wired in FE with no backend. Options: (a) add a
   `languagetool` compose service (e.g. `erikvl87/languagetool` on :8010→8875) so
   grammar works; (b) default the toggle **off** + mark grammar post-MVP. The
   feature degrades *functionally* fine today (returns `[]`, no broken editing) —
   it's the console noise + a dead default-on toggle that's the problem.
2. **CODE SMELL (cheap fix, candidate now)** — `GrammarPlugin.runGrammarCheck`
   checks **all blocks in parallel** (`Promise.all(blocks.map(checkGrammar))`,
   line ~114). The circuit breaker in `api.ts` only opens *after the first
   response returns* — but all 38 requests are already in-flight by then, so the
   breaker (designed explicitly to stop "console-500 spam") **cannot suppress the
   cold-load burst** (it does correctly suppress the subsequent debounced
   edit-loop). Fix: probe ONE block first; if it fails, open the breaker and skip
   the rest (38 console errors → 1). Note: the browser logs `Failed to load
   resource` for any non-2xx fetch regardless of our `catch`, so 0 errors is only
   reachable by *not sending* requests (probe-first, or default-off when absent).

---

### Cluster summary (all clusters audited 2026-05-31)

| Feature | Canonical draft | Diff vs live | Verdict | Action |
|---|---|---|---|---|
| Reader (6) | reader-v2 parts 1–4 | v2 = extension of v1 | **GREEN** + v1 OUTDATED | archive `screen-reader.html`; register TTS model [config]; reader-social deferred |
| Glossary (6) | management/entity-v2/attr/genre/integration | live ≥ drafts | **GREEN** + 1 crash fixed | archive `glossary_extraction_ui_draft.html` |
| Translation (3) | matrix/viewer/workbench | extensions | **GREEN** | none |
| Chat (3) | base/enhanced/context | facets | **GREEN** | none |
| Editor (7) | chapter/modes/version-history | facets; AI-panel=ARCH-1 | **GREEN** struct. + LT finding | LanguageTool: PO decide infra vs default-off; probe-first fix candidate |
| Components (2) | `00. components-v2-warm` | warm = current | — | archive `components-v2.html` |
| Single-version (10) | 1:1 | — | **load-clean** (0 console err on sweep) | none |

**Overall: NO real design drift found.** The drafts are extensions/facets, as the
PO predicted. The audit's *value* was the live findings the status docs hid:
translator-worker down (fixed), 2 Rules-of-Hooks crashes (fixed), TTS model not
registered (config), and now **LanguageTool has no backend** (config + 1 code
smell). Plus archive 3 outdated drafts.

---

## 4. Live-run checklist (step 5 — per feature, after classify)

For each feature kept in scope, verify on the running stack (the worker lesson):
container(s) alive + has restart policy · the action actually produces output
(not 402/fallback/empty) · no console/network errors. Record pass/fail + the
"needs fix / needs supplement" list here.

| Feature | Runs live? | Needs fix / supplement |
|---|---|---|
| Reader (render/TTS/theme/review) | ✅ yes (0 err) | register local-tts-service as TTS model [config] |
| Glossary (tab/entity/attr/genre) | ✅ yes (0 err, after hook fix) | archive `glossary_extraction_ui_draft.html` |
| Translation (matrix/viewer/workbench) | ✅ yes (0 err) | — |
| Chat (base/enhanced/context) | ✅ yes (0 err) | — |
| Editor (editor/modes/version-history) | ✅ yes — editor works | **LanguageTool backend missing** (PO: add service OR default toggle off); probe-first code fix (38→1 console errs) |
| Editor AI-panel | ⏸ disabled (ARCH-1) | reuse canonical Chat component — deferred |
| Single-version ×10 | ✅ load-clean (0 err) | — |

### Outputs — "needs fix / supplement" list (final)

**Code (candidate fixes now):**
- `GrammarPlugin.runGrammarCheck` probe-first so a missing LanguageTool doesn't
  spam 38 console 500s on every editor load (38→1). Low-risk, S.

**Config / infra (PO + provider setup, not code):**
- LanguageTool: add a `languagetool` compose service, OR default the editor
  grammar toggle off + mark post-MVP. (PO decision.)
- Register `local-tts-service` (:9880, 55 voices) as a TTS model in
  provider-registry so reader AI voices work.
- Resolve LLM 402 "pricing not configured" on the model_ref (quota/pricing).

**Drafts to archive (PO-classified OUTDATED):**
- `screen-reader.html` (v1, superseded by reader-v2)
- `components-v2.html` (superseded by `00. components-v2-warm.html`)
- `glossary_extraction_ui_draft.html` (superseded by `ExtractionWizard`)

**Deferred (post-MVP / large):**
- ARCH-1 in-editor AI chat (reuse canonical Chat component) — editor AIチャット tab.
- `screen-reader-social.html` (ratings/reviews/comments) — PO deferred post-MVP.
