# 15a — Wiki dockable migration

**✅ BUILT (2026-07-04).** B1–B8 all shipped in one pass (no Phase A/B split needed — see
below). `wiki` and `wiki-editor` are real dock panels; both classic routes (`WikiTab`,
`WikiEditorPage`) are now thin callers of the same shared workspace components (DOCK-2). All 6
review findings (2 DOCK-9, the source-jump/Glossary-link DOCK-7 pair, the Edit/History DOCK-7
pair, the G7 dirty-guard, the dead History button) are fixed and covered by tests — see
"Post-BUILD `/review-impl`" at the bottom.

CLARIFY output (2026-07-04). Mirrors the shape of [`13_glossary_panels.md`](13_glossary_panels.md)
(Glossary) and [`14a_kg_panels.md`](14a_kg_panels.md) (Knowledge/KG) — read those first for the
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

## Live E2E (Playwright, 2026-07-04) — found and fixed 3 more real bugs

`frontend/tests/e2e/specs/wiki-panels.spec.ts` (mirrors `kg-panels.spec.ts`'s "open through the
real Command Palette against the real backend" LIVE gate). Seeds a fresh book + 2 real glossary
entities + 2 real wiki articles via API (`tests/e2e/helpers/wiki.ts` — verified live against the
dev stack before writing, since no existing TS client helper covers adopt/entity/wiki-article
creation). Ran against a local `vite --port 520x` dev server carrying this session's code (the
baked `:5174` docker image predates it, same staleness caveat `kg-panels.spec.ts` already hit).

**Why this mattered beyond the standard "does it mount" sweep:** the DOCK-10 dirty-guard fix
above was proven only by unit tests that mock `TiptapEditor` and call `unmount()` synchronously —
neither catches a REAL browser's React effect timing or a REAL rich-text editor's own teardown
behavior. Running the actual close→reopen flow against the real stack found three additional,
genuinely live-only bugs the unit tests structurally could not have caught:

1. **Title-refinement race (parent/child effect ordering).** `wiki-editor`'s dock tab stayed
   stuck on the generic "Wiki Editor" label forever — never refined to the article's name.
   Root cause: `WikiEditorWorkspace` (child) called an `onTitleChange` PROP CALLBACK up to
   `WikiEditorPanel` (parent) to refine the title once its own article query resolved, while
   `useStudioPanel`'s generic-title effect lived in the PARENT. Calling `props.api.setTitle()`
   triggers dockview to re-render the panel wrapper, which can re-fire the PARENT's own
   generic-title effect AFTER the refined title already landed, silently reverting it — an
   effect-ordering guarantee that only holds when BOTH effects live in the SAME component.
   **Fix:** moved title-refinement entirely into `WikiEditorPanel` (it now fetches the article
   itself via the same query key, deduped by React Query) — same shape as the existing,
   apparently-uninvestigated `BookReaderPanel` precedent, which already does self-title and
   refinement in one component for exactly this reason.
2. **`TiptapEditor.tsx` fires a spurious final `onUpdate` with a CLEARED doc during its own
   unmount teardown.** Closing the wiki-editor tab while dirty fired one more `onUpdate({})`
   after the real content, overwriting the survives-a-close cache with empty content moments
   before the panel fully unmounted. This is a bug in the SHARED `TiptapEditor.tsx` (also used by
   manuscript chapter editing) — `editor.isDestroyed` was checked but doesn't cover every
   occurrence (the DOM detachment that triggers the spurious dispatch can fire before
   `isDestroyed` flips true). Fixed with a documented guard; belt-and-suspenders hardening added
   in `wikiEditorDraftCache.ts` itself (both `setWikiEditorDraft`/`getWikiEditorDraft` now reject/
   ignore an empty draft, using Tiptap's own plain-text snapshot rather than parsing its JSON doc
   shape) so the cache is robust to this bug class regardless of exactly which teardown path
   trips it.
3. **The cache-restore effect wasn't idempotent against a double-fire of the SAME article
   version.** Even with (1) and (2) fixed, the restored draft was STILL being clobbered — because
   the "sync editor body when article data changes" effect genuinely fires TWICE per mount in
   this dev environment (StrictMode's double-effect-invoke), and a plain boolean "already
   consumed the cache" ref can't distinguish that from a real subsequent refetch (a save's own
   invalidation, a revision restore): on the 2nd firing the ref was already `true`, so it fell
   through to the "sync from server" branch and overwrote the just-restored draft with the
   stale (empty) server body. **Fix:** key the guard on `article.updated_at` instead of a
   boolean — re-firing with the SAME version is now a true no-op; a version that actually
   changed always re-syncs from the server, which is correct for both save and restore. This is
   a more fragile design than it looked in isolation — worth remembering for any future panel
   that mixes "restore from an out-of-band cache" with "sync from a query result."

**Verify:** 4/4 E2E specs pass live (palette-open, Edit→wiki-editor DOCK-7, DOCK-10 close/reopen
survival, G7 discard-confirm on retarget) against the real backend, real dockview, real
TiptapEditor — not mocks. `tsc --noEmit` clean; full FE suite re-run after all three fixes:
673/673 (`features/wiki` + `features/studio`), no regressions.

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

## Manual live smoke via Playwright MCP (2026-07-04) — 2 more responsive bugs, fixed

After the automated E2E pass above, a manual live smoke through Playwright MCP (real browser,
real backend, real dockview — driven interactively rather than a scripted spec) resized the
studio viewport down to typical narrower dock widths (1024px, 768px) to answer a direct question
about whether the Wiki panels are responsive. Neither the automated E2E spec nor any unit test
exercises resize, so this was the first time either panel had been checked at a narrow width.
Found two real overflow bugs, both the same root cause (a `justify-between`/plain flex row with
no `min-w-0`/`shrink-0`/wrap boundaries, so content that doesn't fit isn't clipped or reflowed —
it silently renders past the container's right edge with no scrollbar to reach it):

1. **`WikiEditorWorkspace`'s top action bar** — at 768px the **Save** button (and part of the
   status toggle) rendered fully off-screen to the right; the only affected controls, worse, were
   the ones a user most needs mid-edit. **Fix:** split the bar into an identity cluster (kind
   badge + title + revision count — `min-w-0 flex-1`, title `truncate`s first, revision count
   hidden below `lg:`) and an action cluster (Delete/Status/Save — `shrink-0`, always fully
   visible) instead of one undifferentiated flex row.
2. **`WikiArticleView`'s header row** (the read-only Wiki panel, not the editor) — same missing
   boundaries meant the Regenerate/Edit/History button group rendered at `x > 900` in a
   ~466px-wide panel (verified via `getBoundingClientRect()`), fully inaccessible. **Fix:**
   `flex-wrap` on the header row so the button group drops to its own line below the title
   instead of overflowing invisibly; `flex-wrap` on the button group itself too, so History wraps
   to a second line if even Regenerate+Edit alone fill the row.

**Verify:** re-screenshotted + measured exact `getBoundingClientRect()` for the previously
off-screen elements at 768px/1024px/1568px after each fix (all controls confirmed within
viewport bounds); re-ran `wiki-panels.spec.ts` (4/4 still pass — the fixes are purely additive
flex classes, no markup/testid changes) and the full `features/wiki` unit suite (97/97, no
regressions).

**Correction (same session, minutes later):** the `WikiInfobox` float was initially checked with
a near-empty test article (only a `Name` attribute, no body prose) and looked fine — that test
was too easy. The user directly asked to re-check it, and a second pass with a realistic article
(6 infobox attributes + real prose paragraphs, seeded via the API) found it WAS broken, plus two
more bugs the first pass missed entirely. See the section below.

## Follow-up manual smoke (2026-07-04, same day) — 3 more bugs, all in the read-only Wiki panel

Re-tested with a realistic article (6 filled infobox attributes + 2 prose paragraphs, seeded via
direct API calls) instead of a near-empty one — the minimal first-pass fixture had accidentally
hidden all three of these:

1. **`WikiInfobox`'s fixed `float-right w-[260px]`** squeezed body prose into an unreadably
   narrow wrapped column (2-3 words/line) at narrow panel widths — NOT a pixel overlap, but bad
   enough to read as one. Floats wrap adjacent content for their FULL height regardless of how
   little room is left; there is no width at which a fixed-width float degrades gracefully, only
   not floating does. **Fix:** the infobox no longer floats below `lg:` — it renders as a normal
   full-width block ABOVE the prose (same pattern Wikipedia's own mobile view uses); the
   `lg:float-right lg:ml-5 lg:w-[260px]` float behavior is unchanged at wider widths.
2. **The workspace box's height was a `style={{ minHeight: 500 }}` floor, never a stretch** — in
   a dock panel taller than 500px it left dead space below; in a panel shorter than the content
   needed, it made the WHOLE box grow past the panel's actual height and let the outer
   `WikiPanel` wrapper's `overflow-auto` scroll the entire sidebar+content block AS ONE UNIT
   (scrollHeight 1862px measured on a modest article). **Fix:** `h-full min-h-[500px]` (stretch
   to the dock panel's real height, floor at 500 for a short/split panel) — BUT this alone
   regressed harder: pinning the row to a fixed height means its `overflow-hidden` now actually
   activates, and since neither it nor the article-view column had their own scroll, content
   taller than the pinned height was HARD-CLIPPED with **no scrollbar to reach it at all** —
   worse than the original bug. Caught immediately by comparing `scrollHeight`/`clientHeight` via
   `getBoundingClientRect`-adjacent `evaluate()` calls before declaring it fixed. **Real fix:**
   also add `overflow-y-auto` to the article-view column specifically (`min-w-0 flex-1
   overflow-y-auto`), so the OUTER row can be height-pinned to the dock panel while the tall
   INNER column scrolls independently — same shape as `WikiEditorWorkspace`'s existing
   editor/sidebar columns, which already did this correctly.
3. **The article-list sidebar's fixed `w-[220px]`** ate roughly half of a 466px-wide panel,
   leaving only ~220px for the article body — so even with (1) fixed, prose still wrapped at
   2-3 words/line, because the SIDEBAR, not the infobox, was the deeper cause of the narrow
   column. Asked the user how to prioritize (shrink sidebar vs. defer as a master-detail redesign
   vs. let the content column define its own min-width and scroll horizontally); user picked
   "shrink the sidebar." **Fix:** `w-[150px] lg:w-[220px]` — narrower below `lg:`, unchanged at
   `lg:`+ where there's room to spare.

**Verify:** re-tested with the SAME realistic article at 768px/1024px/1568px — prose now wraps at
5-8 words/line at 768px (was 2-3), infobox card renders full-width above prose below `lg:` and
unchanged floating card at `lg:`+, workspace box fills the dock panel's actual height with no
dead space AND the article column scrolls independently for tall content (verified
`scrollHeight`/`clientHeight` directly: outer panel 547/547 — no waste, no whole-panel scroll;
inner article column 1916/521 — scrolls on its own). Re-ran `wiki-panels.spec.ts` (4/4 pass) and
the full `features/wiki` unit suite (97/97, no regressions) after all three fixes. Still no
automated responsive-layout test exists for this panel — both rounds of these bugs were caught
by manual live-smoke resize only; a `toHaveCSS`/viewport-resize regression spec is the natural
next hardening step if this dock panel gets touched again, and this session is a concrete
argument for writing one rather than relying on a third manual pass next time.
