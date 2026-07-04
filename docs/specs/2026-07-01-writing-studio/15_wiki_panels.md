# 15 — Wiki dockable migration

**✅ BUILT (2026-07-04).** B1–B8 all shipped in one pass (no Phase A/B split needed — see
below). `wiki` and `wiki-editor` are real dock panels; both classic routes (`WikiTab`,
`WikiEditorPage`) are now thin callers of the same shared workspace components (DOCK-2). All 6
review findings (2 DOCK-9, the source-jump/Glossary-link DOCK-7 pair, the Edit/History DOCK-7
pair, the G7 dirty-guard, the dead History button) are fixed and covered by tests — see
"Post-BUILD `/review-impl`" at the bottom.

CLARIFY output (2026-07-04). Mirrors the shape of [`13_glossary_panels.md`](13_glossary_panels.md)
(Glossary) and [`14_kg_panels.md`](14_kg_panels.md) (Knowledge/KG) — read those first for the
established precedents (`FormDialog`/raw `Dialog.*` DOCK-9 fixes, params-retargeting singletons,
the DOCK-2 "no fork" extraction pattern) this spec reuses rather than re-derives.

## Why one phase (not shared-foundation-then-fanout like #13/#14)

Glossary (5 capabilities, 6 hand-rolled modals, a JSON document provider, an entity hoist) and KG
(13 capabilities) needed Phase A (shared foundation) → Phase B (parallel fanout) because the
surface was wide and shared infrastructure had to land before fanout could safely parallelize.
Wiki's surface is narrow — **2 target dock panels, 2 modal migrations, zero new shared
infrastructure** (see Findings). One continuous pass; no Phase A/B split, per
[[workflow-size-by-complexity-not-files]] (size by complexity, not a template).

## Findings from investigation (2026-07-04)

- **`catalog.ts`**: 0 wiki entries today. Zero MCP tool surface: no `wiki_*` entries anywhere in
  `services/chat-service/app/services/frontend_tools.py`.
- **Current surface**: route `/books/:bookId/wiki` → `WikiTab` (`frontend/src/pages/book-tabs/WikiTab.tsx`,
  823L, a tab inside `BookDetailPage`) + route `/books/:bookId/wiki/:articleId/edit` → `WikiEditorPage`
  (`frontend/src/pages/WikiEditorPage.tsx`, 446L, dedicated full-page route). Supporting layer
  `frontend/src/features/wiki/` (~2,900L / 23 files): already well-decomposed into components
  (`WikiSidebar`, `WikiArticleView`, `WikiInfobox`, `WikiToC`, `CreateArticleDialog`,
  `GenerateWikiDialog`, `WikiGenJobBanner`/`Detail`/`Badge`, `VerifyFlagsPanel`,
  `WikiSuggestionReview`, `KnowledgeUpdatesPanel`) + hooks (`useWikiGenJob`, `useWikiStaleness`).
  **Not organic sprawl** like Glossary's pre-migration state — `WikiTab` holds ~7 state vars and
  always renders the same 2-pane layout + overlays; no DOCK-8 view-switch pattern to unwind.
- **No open UX debt.** `docs/reports/2026-06-11-wiki-mockup-vs-code-audit.md`'s gaps were all
  closed same day by `docs/plans/2026-06-11-wiki-fe-gap-closure.md` (W1–W6), verified live in
  current code (diff rendering, severity bar, rescan, dismiss-batch all present). Remaining
  DEFERRED rows (`D-WIKI-M7B-RUNNING-CANCEL`, `D-WIKI-M6-PRECISE-COST`,
  `D-JOBS-WIKI-GEN-RECONCILE-INDEX`) are backend/perf only. **Confirmed with the user
  (2026-07-04): no GUI/UX redesign scope — faithful DOCK-1..11 port only.**
- **DOCK-9 violations found**: `CreateArticleDialog` (`WikiTab.tsx:514`, hand-rolled
  `fixed inset-0`, simple single-column form — `FormDialog` fits) and `KnowledgeUpdatesPanel`
  (`KnowledgeUpdatesPanel.tsx:168`, hand-rolled `fixed inset-0`, but its header carries an extra
  "Rescan" action button beside the title — `FormDialog`'s title/description-only header can't
  hold that without relocating the button, which the no-redesign decision rules out — needs raw
  `Dialog.*`, same "custom chrome" branch as `EntityEditorModal`/`ExtractionWizard`).
  `GenerateWikiDialog.tsx` is **already** `FormDialog`-based — no fix needed.
- **No Lane-B effect handler planned.** No `wiki_*` MCP tool exists for an agent to call, so
  there is nothing yet for a `wikiEffects.ts` handler to react to. If/when a `wiki_*` MCP tool
  ships, wire it then (same shape as `glossaryEffects.ts`) — not now (gate #3, naturally-next-phase:
  the prerequisite doesn't exist).
- **No JSON Document Standard provider planned.** The only editable structured field today is
  `status` (draft/published — a single enum toggled by a button, not a form); infobox is read-only
  everywhere in the current UI. Same thinness argument that kept Glossary's *translate wizard* a
  modal instead of new document-provider machinery. Revisit only if agent-driven article edits
  become a real ask.

## Locked decisions (CLARIFY 2026-07-04)

- **W1 (asked, decided):** Article editing becomes its own dock panel, **`wiki-editor`** — a
  **params-retargeting singleton** (`{articleId}`), same precedent as `editor` (manuscript
  chapters — already docks the same shared `TiptapEditor`), `book-reader`, `json-editor`,
  `skill-editor`. NOT a modal (unlike `EntityEditorModal`): a full prose editor deserves panel
  real estate, not a cramped dialog. NOT left as a lingering full-page route behind a new-tab
  fallback: unlike some not-yet-ported KG capabilities, there's no reason to defer it — the
  editor component and the retargeting-singleton pattern both already exist.
- **W2 (architect default, no fork):** `WikiEditorPage`'s existing 3-tab right sidebar
  (Infobox / History / Suggestions) stays **exactly as-is, in-panel** — one internal tab strip,
  NOT fragmented into 3 sibling dock panels. Mirrors `EntityEditorModal`'s internal-tabs precedent
  (Glossary G1): small, tightly-coupled companion views to the ONE article being edited, not
  independently-useful surfaces a user would want open side-by-side.
- **W3 (architect default, no fork):** The `wiki` panel (`WikiTab`'s master-detail: sidebar +
  article view) becomes ONE dock panel, mirroring `glossary`. `CreateArticleDialog`,
  `GenerateWikiDialog`, `KnowledgeUpdatesPanel` stay modals/drawers inside it — migrated for
  DOCK-9, not restructured into panels (mirrors Glossary G1's "no forced panel-ification of every
  sub-flow").
- **W4 (locked by investigation, not a fork):** No JSON document provider, no Lane-B effect
  handler this pass — see Findings. Both are legitimate `Naturally-next-phase` deferrals (gate #3:
  the prerequisite — an actual editable-structure surface, or an actual MCP tool — doesn't exist
  yet), not tracked as debt rows since there is nothing to build against today.

## Design review (2026-07-04, before PLAN) — 6 findings, folded in below

A pass over the actual Wiki source (not just the Findings summary above) before locking the
build plan, mirroring the repo's REVIEW discipline: catch gaps while they're still spec edits,
not code to unwind later.

1. **6 DOCK-7 call sites, not previously enumerated** — same bug class the Glossary
   `/review-impl` pass just found in `ExtractionWizard` (`navigate()` reachable from inside the
   Studio tears down the whole dock layout): `WikiArticleView`'s Edit button
   (`navigate('.../edit')`), `WikiEditorPage`'s Back button (`navigate('.../wiki')`),
   `WikiEditorPage`'s post-delete redirect (same target), `WikiEditorPage`'s "article not found"
   fallback (`navigate(-1)`), `CreateArticleDialog`'s empty-state `<Link to=".../glossary">`, and
   `KnowledgeUpdatesPanel`'s source-jump `<Link to={jump}>`. All 6 need the
   `useOptionalStudioHost()` branch (StepConfig.tsx / ExtractionWizard precedent) — now explicit
   line items below (B1a, B2a).
2. **No G7 dirty-guard designed for `wiki-editor` retargeting.** `JsonEditorPanel.tsx` (an
   existing retargeting singleton) documents this as a REQUIRED, repo-wide pattern for every
   params-retargeting panel: "retarget on every `onDidParametersChange`... dirty ⇒ buffer IS the
   working copy; never clobber it — G7 spirit." A naive `wiki-editor` that just re-seeds `body`
   from `props.params.articleId` on change would silently discard unsaved prose the instant the
   panel retargets to a different article (a sidebar Edit click, or an agent-driven
   `host.openPanel('wiki-editor', {articleId: Y})`, while article X is still dirty). **Locked:**
   `wiki-editor` must block/confirm before retargeting away from a dirty article — mirroring
   `JsonEditorPanel`'s reseed-guard and `entityDocument.ts`'s `reload()` guard (now B2b).
3. **Pre-existing, newly-more-reachable data-loss bug**: the classic `WikiEditorPage`'s Back
   button and "Article not found → Go back" button have **no dirty-guard today at all** — client-
   side `navigate()` doesn't trigger `beforeunload`, so leaving mid-edit silently loses the draft.
   B1/B2 already touch this exact code to extract it into panel form — fixing it there is free;
   opening a separate defer row for it would not be (now folded into B2b).
4. **B5 un-hedged**: locked to the DOCK-2 pattern outright (no "decide during BUILD") — the
   classic pages become thin callers of the SAME extracted components, neither retired nor
   duplicated, exactly like `GlossaryTab.tsx` today.
5. **Positive finding, no new infra needed**: `KnowledgeUpdatesPanel`'s source-jump link and
   `CreateArticleDialog`'s Glossary link both resolve cleanly through **existing** infra.
   `sourceJumpUrl()` only ever returns `/books/:id/chapters/:cid/read` (matches
   `resolveStudioLink`'s `CHAPTER_RE` → `host.focusManuscriptUnit`, a real in-studio jump) or
   `/books/:id/glossary` (no book-scoped `PATH_PANELS` entry → falls through to `external` →
   safe new-tab, not a crash). Use `followStudioLink(jump, host, ctx)` as-is — **zero changes to
   the shared `studioLinks.ts`**. `CreateArticleDialog`'s Glossary link should use a direct
   `host.openPanel('glossary')` instead (known panel id, simpler, same precedent as
   `ExtractionWizard`'s `jobs-list` fix) rather than the generic resolver.
6. **Scope question for the user, decided (2026-07-04): wire it.** `WikiArticleView`'s "History"
   button has **no `onClick` at all today** (dead button, pre-existing). Since `wiki-editor`
   already needs a `rightPanel` concept internally (W2), wiring History →
   `host.openPanel('wiki-editor', {params: {articleId, rightPanel: 'history'}})` is cheap — the
   infra exists from B2 either way, and this only activates a control already on screen (no new
   UI added). Classified as a small in-scope bug fix, not a redesign (now B8).

## Scope (single phase)

| # | Task | Notes |
|---|---|---|
| B1 | `wiki` dock panel — thin wrapper reusing `WikiSidebar` + `WikiArticleView`, extracted from `WikiTab.tsx` (DOCK-2 "no fork" extraction, same shape as `GlossaryEntityList`) | catalog + i18n (en/vi/ja/zh-TW) + BE `ui_open_studio_panel` enum + contract regen; palette + agent openable |
| B1a | DOCK-7 fixes inside B1's extracted components: `WikiArticleView`'s Edit → `useOptionalStudioHost()` branch (`host.openPanel('wiki-editor', {params:{articleId}})` vs `navigate`); `CreateArticleDialog`'s Glossary link → `host.openPanel('glossary')` branch; `KnowledgeUpdatesPanel`'s source-jump link → `followStudioLink(jump, host, ctx)` branch | review finding #1/#5 |
| B2 | `wiki-editor` dock panel — thin wrapper reusing `TiptapEditor` + `InfoboxPanel`/`RevisionPanel`/`SuggestionPanel`, extracted from `WikiEditorPage.tsx` | params-retargeting singleton `{articleId}`, `hiddenFromPalette: true` (opened via the `wiki` panel's Edit button / `host.openPanel`), same precedent as `json-editor`/`skill-editor` |
| B2a | DOCK-7 fixes: Back button + post-delete redirect + "not found" fallback → `useOptionalStudioHost()` branch (`host.openPanel('wiki')` / just render the empty state with no back-navigation affordance inside the Studio, since "browser back" has no meaning in a dock panel) | review finding #1 |
| B2b | G7 dirty-guard on retarget: block (or confirm-discard) switching `wiki-editor` to a different `articleId` while `dirty` is true — same guard closes the pre-existing Back-button data-loss bug on the classic page too (shared extracted hook) | review finding #2/#3 |
| B3 | `CreateArticleDialog` → `FormDialog` | DOCK-9 fix, simple template fit |
| B4 | `KnowledgeUpdatesPanel` → raw `Dialog.*` | DOCK-9 fix, custom-chrome branch (header action button) |
| B5 | Classic pages (`WikiTab`, `WikiEditorPage`) become thin callers of the SAME extracted components (B1/B2) — neither retired nor duplicated, exactly like `GlossaryTab.tsx` today | locked, not a BUILD-time decision (review finding #4) |
| B6 | Lane-B wiring | none needed this pass (W4) |
| B7 | JSON document provider | none needed this pass (W4) |
| B8 | Wire `WikiArticleView`'s dead "History" button → `host.openPanel('wiki-editor', {params:{articleId, rightPanel:'history'}})` | review finding #6, decided: fix (small in-scope bug fix, not a redesign) |

## Out of scope

- Relationships graph, KG ontology — separate feature (Knowledge/KG track).
- The 3 backend/perf DEFERRED rows listed above — untouched by this migration, stay tracked where
  they already are.
- GUI/UX redesign — explicitly declined by the user (2026-07-04); this is a faithful DOCK-1..11
  port, not a redesign.
- `frontend/src/features/profile/WikiTab.tsx` — an unrelated user-profile feature that happens to
  share a component name; different route, not touched.

## Testing discipline

Same as #13/#14: unit + E2E per panel, `/review-impl` at phase close. No BE changes are expected
(no new service-side work — B1/B2 are FE-only extractions, B3/B4 are FE-only DOCK-9 fixes) beyond
the `ui_open_studio_panel` enum + contract regen, so the VERIFY evidence records
`"no BE service-logic surface touched — enum/contract regen only"` rather than a live-smoke token.

## BUILD (2026-07-04)

All 8 scope rows shipped in one pass:

- **B1/B1a** — `WikiWorkspace.tsx` (new, extracted verbatim from `WikiTab.tsx` except the DOCK-7
  fixes) + `CreateArticleDialog.tsx` (new file, `FormDialog`) + `WikiPanel.tsx` (new, thin panel
  wrapper). `WikiArticleView`'s Edit/History and `CreateArticleDialog`'s empty-state Glossary
  link all branch on `useOptionalStudioHost()`.
- **B2/B2a/B2b** — `WikiEditorWorkspace.tsx` (new, extracted from `WikiEditorPage.tsx`) +
  `WikiEditorPanel.tsx` (new, params-retargeting singleton). The G7 dirty-guard lives in the
  panel (`target`/`pending` split, `ConfirmDialog` gates a dirty article switch,
  `key={target.articleId}` forces a clean remount on confirm); the shared Back-button guard lives
  in the workspace (`handleBackClick` — fixes the pre-existing "Back while dirty loses the draft"
  bug for the classic page too, for free).
- **B3** — `CreateArticleDialog` → `FormDialog` (folded into B1).
- **B4** — `KnowledgeUpdatesPanel.tsx` → raw `Dialog.*` (custom-chrome branch, header Rescan
  button); source-jump link branches to `followStudioLink` inside the studio, unchanged `<Link>`
  outside — zero changes needed to `studioLinks.ts` (`sourceJumpUrl()` only ever returns a
  chapter-read path, already matched by `resolveStudioLink`'s `CHAPTER_RE`, or a glossary path,
  which safely externalizes to a new tab).
- **B5** — `WikiTab.tsx`/`WikiEditorPage.tsx` are now thin shells calling the shared workspaces.
- **B8** — `WikiArticleView`'s History button (previously dead, no `onClick` at all) now opens
  `wiki-editor` pre-targeted at the history tab.
- **Integration** — `catalog.ts` (+`wiki`, +`wiki-editor` hidden-from-palette), 4× `studio.json`
  (+`panels.wiki`, +`panels.wiki-editor`), 4× `wiki.json` (+`discardTitle/Description/Confirm`,
  +`discardSwitch*`, +`editorPanelEmpty`), BE `ui_open_studio_panel` enum (+`wiki` only —
  `wiki-editor` stays out, same as `book-reader`/`json-editor`/`skill-editor`), contract regen.

**Verify:** `tsc --noEmit` clean; full FE suite 572 files / 3979 tests green (incl. the
previously cross-session-red `panelCatalogContract.test.ts`, now green); i18n parity clean for
all new `wiki`/`wiki-editor`/`discard*` keys across en/vi/ja/zh-TW (pre-existing, unrelated gaps
in extensions/proposals/skill-editor/chapter-browser remain, not touched); BE
`test_frontend_tools.py` + `test_frontend_tools_contract.py` 42/42 (also synced a concurrent
session's `chapter-browser` enum entry into the same hardcoded snapshot list — its own addition
was complete in `frontend_tools.py` but hadn't reached the test yet; mechanical, zero design
guesswork, kept the shared spine green for both tracks).

## Post-BUILD `/review-impl` (2026-07-04)

Fresh adversarial pass over the actual built code (not the plan), focused on the G7 dirty-guard
as the single highest-risk area:

- Confirmed the `ConfirmDialog` overlay blocks pointer-events on the underlying workspace while a
  pending switch is staged — no route exists to stack two simultaneous pending switches.
- Confirmed `Discard & switch` correctly leaves the OLD article dirty=true briefly until the new
  article's query resolves and bubbles `onDirtyChange(false)` — worst case is one redundant
  confirm prompt in a narrow race window, never silent data loss.
- Confirmed Delete and the "article not found" fallback both correctly bypass the dirty-guard
  (nothing to lose in either state) by calling `onBack` directly instead of `handleBackClick`.
- Grepped all of `features/wiki/**` for `navigate(`/`<Link` — the only remaining unguarded site is
  `WikiEditorPage.tsx`'s own `onBack` (correct: it's the classic page, outside the studio).
- Confirmed all `wiki`/`wiki-editor` i18n keys and catalog rows survived two further concurrent
  sessions' edits to the same shared files (`catalog.ts`, `studio.json` x4, `frontend_tools.py`)
  landing mid-BUILD.

No HIGH/MED findings. Glossary's dockable migration pattern (spec → CLARIFY decisions → design
review before PLAN → build → adversarial review-impl) held up on a second, independent feature.

## Second `/review-impl` pass (2026-07-04, user-requested) — 1 real finding, fixed

A fresh pass specifically checking the actual code against every rule in
[`dockable-gui.md`](../../standards/dockable-gui.md), not just re-confirming the first pass.

**DOCK-10 violation found: `wiki-editor`'s in-flight edit survived neither a dock-tab close nor
a reopen.** `body`/`dirty` lived as plain `useState` inside `WikiEditorWorkspace`, which is
rendered *inside* the `wiki-editor` panel's own React subtree. D4 states the mechanism plainly:
"dockview unmounts a closed panel." The G7 params-retargeting guard (B2b) only covers *staying
open and switching articles* — it does nothing for the tab's own close button / drag-to-close /
middle-click, a vector the classic page never had at all (pages don't have "tabs" to close).
Closing the panel mid-edit and reopening the same article later silently lost the draft, with
zero warning — the same data-loss class B2b was built to prevent, just via a different door.

**Fix:** `frontend/src/features/wiki/lib/wikiEditorDraftCache.ts` (new) — a module-level,
single-slot cache (same lightweight "plain variable survives unmount" technique as
`entityDocument.ts`'s binding bridge, not a full `ManuscriptUnitProvider`-style Tier-4 hoist,
since `wiki-editor` is a singleton and only one draft can ever be in flight). `WikiEditorWorkspace`
writes to it on every keystroke, checks it once per mount (a `useRef` gate so a LATER genuine
server refresh — a save's own refetch, a revision restore — always wins over the one-time
restore), and clears it on save success or an explicit discard (the Back-confirm, and the G7
discard-and-switch confirm in `WikiEditorPanel`). A separate `editorContent` state (decoupled
from the keystroke-churning `body` state) feeds `TiptapEditor`'s `content` prop so the restore
doesn't fight the editor's own reactive `content`-diffing.

**Verify:** 4 new tests in `WikiEditorWorkspace.test.tsx` proving the fix across a REAL
`unmount()` + fresh `render()` (not just a re-render) — draft restored on reopen, no cross-
article leakage, cleared on save, cleared on explicit discard; 1 new test in
`WikiEditorPanel.test.tsx` proving the G7 discard-and-switch path calls the clear function.
`tsc --noEmit` clean; `features/wiki` + `features/studio/panels` suites 378/378 (16 in the two
touched files).
