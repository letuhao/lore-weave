# Implementation Plan — Writing Studio Newcomer Polish

Companion to [spec.md](spec.md) (root causes + options) and the [diary](../../dogfood/2026-07-18-newcomer-first-book.md)
(symptoms). Decisions are **sealed** (spec §"Sealed decisions"): Part/Arc rename, "Chapter {n}"
default title, add a real rail "New chapter" (reverses the 2026-07-17 rail-create stance).

**Effort size: L** (7+ semantic changes; side effects in book-service + auth; a cross-service seam).
→ this plan file is required; VERIFY needs cross-service **live-smoke** for M1 (FE ↔ book-service);
2-stage REVIEW + POST-REVIEW per milestone; i18n gap-fill (18 locales) for any new/changed string.

Build order is cheapest-highest-impact first, dependencies respected. Each milestone is independently
shippable (own commit + SESSION update).

---

## M1 — Kill the `editor-<uuid>.txt` title (F4)  · FS · size S–M

**Goal.** A new unnamed chapter reads "Chapter {n}" (localized), never a storage filename — from the
UI door *and* any other caller (MCP).

**Changes.**
1. **FE (primary, localized):** [PlanHubPanel.tsx `writeChapter`](../../../frontend/src/features/studio/panels/PlanHubPanel.tsx#L80-L86)
   — stop sending `title: ''`. Send `title: t('planHub.simple.defaultChapterTitle', 'Chapter {{n}}', { n })`
   where `n = (simpleChapters.total ?? 0) + 1`. Same for the new rail create (M3) and the editor
   empty-state door (M3) — all route through one shared `createChapterAndOpen` helper so the title
   logic has one home.
2. **Display guard (defensive):** wherever a chapter title renders (manuscript navigator row,
   `SimpleChapterRow`, jump results), never surface a `*.txt`/`editor-*` storage filename — fall back
   to a localized "Untitled chapter · {number}". Covers legacy rows already stored with empty titles.
3. **BE (safety net for title-less callers):** [book-service `createChapterRecord`](../../../services/book-service/internal/api/server.go#L1709)
   + [mcp_tools_write.go:290](../../../services/book-service/internal/api/mcp_tools_write.go#L290) —
   keep the filename internal, but when `title` is blank store a neutral human default ("Untitled
   chapter") as the **title** instead of leaving it to surface the filename. (FE supplies the nice
   "Chapter {n}"; this only catches callers that pass nothing.)

**Tests.** FE unit: `writeChapter` sends a non-empty localized title; display guard renders fallback
for a `.txt` title. BE: JSON create with empty title → stored title is not a filename. i18n: new
`defaultChapterTitle` + `untitledChapter` keys gap-filled 18 locales.

**Acceptance / live-smoke.** On the stack: create a chapter via Simple door → navigator shows
"Chapter 1", **no** `editor-*.txt` anywhere. Create via MCP write tool with no title → human title, not
filename. `live smoke: create chapter (FE→book-service) shows 'Chapter 1'`.

---

## M2 — "Saved but 0 chapters" → live refresh (F3)  · FE · size M

**Goal.** Any chapter CRUD reflects in the Manuscript navigator with no manual Reload.

**Changes.**
1. **Studio bus slice:** in `StudioHostProvider`, add a `manuscriptRevision: number` to the bus and a
   `bumpManuscriptRevision()` action (monotonic counter — the `focusManuscriptUnit` seam already lives
   here).
2. **Emit on every CRUD:** Plan-Hub `writeChapter` / `renameChapter` / `deleteChapter`
   ([PlanHubPanel.tsx:80-98](../../../frontend/src/features/studio/panels/PlanHubPanel.tsx#L80-L98)),
   the editor-create door (M3), and the drawer `childCreate` all call `bumpManuscriptRevision()` on
   success (alongside the existing react-query invalidations).
3. **Subscribe → reload:** [useManuscriptTree](../../../frontend/src/features/studio/manuscript/useManuscriptTree.ts#L63)
   reads `manuscriptRevision` from the bus and calls its existing `reload()` when it changes (a
   synchronization effect keyed on the counter — not event-handling; it's a genuine external-state sync).

**Tests.** Unit: bumping the revision triggers `reload()`; a `writeChapter` success bumps it. Guard
against double-reload on mount (revision starts at 0, effect skips the initial value).

**Acceptance.** Create from Simple mode → rail count goes "0 ch" → "1 ch" and the row appears with **no**
manual Reload. Rename/delete/move reflect live. (FE-only; unit-green sufficient, note in VERIFY.)

---

## M3 — Remove the create dead-ends (F2 + F5) · FE · size M

**Goal.** No path to "I want to write" ends in *"select a chapter"* with no chapter and no button.

**Changes.**
1. **Editor empty state:** [EditorPanel.tsx](../../../frontend/src/features/studio/panels/EditorPanel.tsx)
   — replace the bare *"Select a chapter…"* with a primary **"＋ Start your first chapter"** (create +
   open) when the book has no open unit, using the shared `createChapterAndOpen` helper (M1). Keep the
   "select a chapter" hint as secondary text when chapters *do* exist.
2. **Manuscript rail create (the sealed reversal):** [ManuscriptNavigator.tsx](../../../frontend/src/features/studio/manuscript/ManuscriptNavigator.tsx#L200-L213)
   — add a real **"＋ Chapter"** action (`data-testid="manuscript-chapter-new"`, new `onCreateChapter`
   prop) that creates + opens, distinct from the existing Plan entry point. Wire it in `StudioSideBar`
   to `createChapterAndOpen`. Update the code comment that documents the 2026-07-17 "creation lives on
   the Plan rail" stance to record this amendment.
3. **Empty-manuscript state:** the rail's "No chapters yet." gets the same "＋ Start your first chapter"
   primary door.
4. **F5/B planless→Simple guard:** [PlanHubPanel](../../../frontend/src/features/studio/panels/PlanHubPanel.tsx#L57-L58)
   — for a book with no plan **and** no chapters, land in Simple regardless of the stored pref
   (graduate to the user's pref once structure exists). Cheap hardening so a default-Advanced pref
   never drops a newcomer onto the empty canvas.

**Tests.** Editor empty state renders the create door and calls `createChapterAndOpen`; rail
`manuscript-chapter-new` present + wired; planless+chapterless book renders Simple even with
`plan_hub_mode_simple=false`.

**Acceptance.** New book → Editor shows "Start your first chapter" → one click = blank chapter open +
navigator updated (via M2). Rail has a working "＋ Chapter". Planless book opens Simple.

---

## M4 — Stop the "logged-in but broken" flash (F1) · FE · size M

**Goal.** A stale/booting backend never renders confident authed chrome throwing silent 401s.

**Changes.**
1. **Refresh-first:** on mount with a cached session, attempt token refresh before (or race-and-suppress
   with) the first data fetches in the auth provider.
2. **Reconnecting affordance:** while auth is unresolved, show a subtle "Reconnecting…" state in the top
   bar instead of firing preference/profile/notification calls that 401.
3. **Global transient-auth policy:** 401s that trigger a refresh never reach the toast/console as
   user-facing errors; a genuine hard failure (refresh fails, or first calls all error) shows ONE
   friendly "Can't reach LoreWeave — retrying" banner. (Also gracefully covers the dev boot-race
   `ERR_CONNECTION_REFUSED`.)

**Tests.** Expired-token mount → no error toasts, reconnecting shown, chrome after refresh resolves.
Dead-backend mount → single retry banner, not a broken authed shell.

**Acceptance.** Reproduce the diary's opening: load with an expired cached token → clean "Reconnecting…"
→ normal. No 401/500 flood surfaced to the user.

---

## M5 — Clarity polish: Part/Arc rename + tab casing + explainer (F6/A+B, F7a) · FE · size S

**Goal.** Kill the "Act" vs "Arc" homophone; fix small text nits.

**Changes.**
1. **Rename "Act" → "Part" (display only):** `en/studio.json` — `manuscript.actShort` 'Act'→'Part',
   `manuscript.actTag` 'ACT'→'PART', `manuscript.newAct`, `manuscript.renameAct`, `manuscript.trashAct`,
   `manuscript.moveActUp/Down`, `manuscript.actTrashed`, `manuscript.emptyActHint`, `manuscript.statActs`,
   `manuscript.trashedActs`, `manuscript.untitledAct`, `manuscript.renameActPlaceholder`,
   `manuscript.newActPlaceholder`. **Data model + testids (`manuscript-part-*`) unchanged** — they
   already say "part" internally. Gap-fill 18 locales.
2. **Explainer (F6/B):** a one-line note where both appear — Plan Hub empty state and/or the rail header
   tooltip: "Parts group your manuscript; Arcs are the plan."
3. **F7a tab casing:** the Studio tab reads lowercase "plan" — fix the label to "Plan" (find the
   `planHub`/tab label string; align casing with its Title-Case siblings). Gap-fill.

**Tests.** i18n parity gate green (18 locales, studio ns); a render test asserts "PART" tag / "Plan" tab.

**Acceptance.** No sibling surface shows both "Act" and "Arc"; the "plan" tab reads "Plan".

---

## M6 — Verify F7b, flag F7c · size XS + a tracked row

- **F7b (99+ badge):** verify a genuinely fresh account starts at 0 unread; if the badge can show stale
  seeded counts, cap/soften display. Likely test-data only — confirm, don't over-engineer.
- **F7c (chat context bloat):** the co-writer preloads 48 tools + 5 skills (~12.9k tok) per message.
  **Do not fold into this track** — open a row against the `context-budget-law` work: "lite context for
  plain creative chat / lazy tool-schema load." Record in SESSION_HANDOFF Deferred (gate #2, structural).

---

## Cross-cutting gates (apply per milestone)
- **VERIFY evidence:** paste the real test output; M1 also needs the cross-service live-smoke token.
- **2-stage REVIEW** (spec-compliance + quality) then **POST-REVIEW** human checkpoint per milestone.
- **i18n:** every new/changed user-facing string → `en` + `scripts/i18n_translate.py` gap-fill 18 locales.
- **Shared-checkout discipline:** commit only this track's files by explicit pathspec (4 parallel
  sessions edit i18n + studio files); grep-verify nothing foreign is staged before commit.
- **No new global `*_ENABLED` env for user-facing behavior** (F5 pref stays the per-user setting it is).

## Not in scope (separate tracks)
- F6/C — unify the Part/Arc hierarchies into one spine (XL design track).
- F7c — chat context budget (belongs to `context-budget-law`).

---

## Sealed edge cases & open-question resolutions (2026-07-18, from a code-grounded pass)

**M1 — title.**
- The leak is precise: `title || original_filename || '#'+sort_order` in **two pure mappers** —
  [`chapterToNode`](../../../frontend/src/features/studio/manuscript/useManuscriptTree.ts#L19-L30)
  (flat book) and [`chapterTitle`](../../../frontend/src/features/studio/manuscript/partsTree.ts#L18-L21)
  (parts mode). Fix both to `title || i18n.t('manuscript.chapterN', { number: sort_order })`, **never**
  `original_filename`. → **M1 is FE-only; no book-service change** (the earlier BE default-title idea is
  dropped: it would inject a non-localized English title for MCP callers, and the display layer is the
  right home for the fallback anyway).
- Localize inside pure functions via the **i18n singleton** (`import i18n from '@/i18n'` → `i18n.t`).
- `sort_order` is always present for a book chapter, so "Chapter {n}" is always well-formed; guard the
  (impossible-for-flat) null case → "Untitled chapter".
- **Consistency:** align `SimpleChapterRow`'s empty fallback (currently "Untitled chapter") to the SAME
  "Chapter {n}" so one chapter reads identically in the navigator and the Simple list. Update its test.
- **`.txt`-as-title paranoia:** we no longer render `original_filename` at all, so there's nothing to
  over-match; no regex guessing about "is this a filename". Simpler and safer.

**M2 — live refresh.**
- `reload()` is `resetAndLoad` → it **resets expansion**. Accepted for v1: showing the just-created
  chapter (correctness, kills the "looks like data loss" scare) outweighs preserving expanded acts. A
  surgical in-place patch is a future nicety, logged as debt — not built now.
- **No double-load on mount:** the navigator subscribes to `manuscriptRevision` and calls `reload()`
  only when the value *changes* from a mount-captured ref (initial value never triggers a reload).
- **Wiring seam:** `useManuscriptTree` stays pure (returns `reload`). The bus subscription lives in the
  component (`ManuscriptNavigator`/`StudioSideBar`, both inside `StudioHostProvider`). Emitters
  (`bumpManuscriptRevision`) are the panels that already use `useStudioHost`: Plan-Hub write/rename/
  delete, the editor-create door, the drawer `childCreate`.

**M3 — create doors.**
- Shared `createChapterAndOpen` helper needs **no chapter count** (M1's display owns "Chapter {n}"): it
  just creates (title `''`) → `focusManuscriptUnit` → `bumpManuscriptRevision`.
- **Editor empty state:** always offer "＋ Start your first chapter" (harmless when chapters exist);
  keep "or pick one from the manuscript" as secondary text.
- **Rail "＋ Chapter":** shown for `source === 'chapters'` (flat books — where newcomers live). For a
  Work/outline-source book, creation stays in the plan/drawer (the outline owns the hierarchy). Document
  the amendment to the 2026-07-17 "creation lives on the Plan rail" comment.
- **Planless→Simple (F5/B):** compute `showSimple = mode.simple || (view.specEmpty && chapters===0)`;
  render Simple when `showSimple`, and reflect it in the toggle's pressed state. Does **not** mutate the
  stored pref — a purely presentational override for the empty book.

**M4 — auth UX (scope-bounded).**
- The refresh mechanism already works (`api.ts` silent-refresh on 401 → `lw-auth-refreshed` →
  `auth.tsx` re-reads tokens). **Do NOT re-architect it.** Scope = UX only: (a) expose a "reconnecting"
  signal while a silent refresh is in flight; (b) stop the transient 401s (profile/prefs/notifications
  during refresh) from surfacing as user-facing error toasts. If wiring this cleanly requires broad
  `api.ts` surgery, **reduce to the reconnecting indicator + a tracked debt row** rather than risk a
  global-fetch regression in a polish pass. (Decision made when M4 is reached, after reading `api.ts`.)
- The dev-only boot-race `ERR_CONNECTION_REFUSED` (stack still starting) is **out of scope** for prod;
  the friendly "can't reach LoreWeave" banner covers it incidentally.

**M5 — rename.**
- "Act" → "Part" is a **display-string change only**: edit the VALUES of `manuscript.*` keys in
  `en/studio.json`; keys, testids (`manuscript-part-*`), and the data model are unchanged. Gap-fill 18
  locales. Scope strictly to `studio` ns `manuscript.*` (don't touch unrelated "act" strings elsewhere).
- Verify the lowercase "plan" tab's source string and Title-case it to "Plan".

**M6.** F7b = verify-on-fresh-account only. F7c = a tracked `context-budget-law` row; not built here.
