# Spec — Writing Studio Newcomer Polish & Bug Fixes

Source of truth for the *symptoms*: [the first-run diary](../../dogfood/2026-07-18-newcomer-first-book.md).
This doc is the *solutions* — root cause, options considered, the recommendation, acceptance test, size.

Guiding principle for all fixes: **an empty/first-run state must never look broken, never look like
data loss, and always offer the next action in plain language.** Two-thirds of the diary's pain was
not missing features — it was the app failing silently or speaking jargon at the exact moment a
newcomer is deciding whether to stay.

---

## F1 — The app rendered "logged in" while every backend call failed 🔴

**What the newcomer saw.** On first paint the sidebar showed my name + avatar while the network threw
`/v1/me/preferences`, `/v1/account/profile`, `/v1/notifications/*`, `/v1/auth/refresh` — first
`ERR_CONNECTION_REFUSED` (stack still booting), then `401/500` (cached token expired). It self-healed
via a token refresh seconds later, but for ~10s the UI confidently lied.

**Root cause.** The app shell renders identity from cached auth state and fires its data calls
immediately, with no "silent-refresh-first" gate and no global policy to suppress transient auth
errors while a refresh is in flight. The boot-race `ERR_CONNECTION_REFUSED` is a **dev-only** artifact
(the compose stack was still coming up) and is out of scope for a deployed environment; the **stale-token
401 flood + confident chrome** is the real defect.

**Options.**
- **A — Silent-refresh-first + reconnecting affordance (RECOMMENDED).** On mount with a cached
  session, attempt the token refresh *before* (or race-and-suppress alongside) the first data fetches;
  while unresolved, show a subtle "Reconnecting…" state instead of firing error toasts. Only surface a
  hard error if the refresh itself fails. Cheapest correct fix; no flash-of-spinner on the happy path.
- **B — Hard auth gate.** Block the entire authed shell behind a validated-token spinner. Correct but
  heavier and adds a load flash to *every* app open — worse happy-path UX.
- **C — Error-policy only.** Keep current render; just teach the global fetch layer to swallow 401s
  that trigger a refresh, and not paint the notification/preference errors. Smallest, but leaves the
  "looks logged in but isn't" gap on a genuinely dead backend.

**Recommendation:** **A + C.** Refresh-first, a "Reconnecting…" chip in the top bar while auth is
unresolved, and a global rule that transient-auth 401s during refresh never reach the toast/console as
user-facing errors. Add a single friendly "Can't reach LoreWeave — retrying" banner if the *first*
calls all fail outright (covers the dev boot-race gracefully too).

**Acceptance.** Load the app with an expired cached token → no error toasts, a brief "Reconnecting…",
then normal chrome once refresh lands. Kill the gateway → one friendly retry banner, not a confident
broken shell. **Size: M.** (Touches the auth provider + a global fetch error policy — a side-effect
area, so min M.)

---

## F2 — You can't create a chapter where you write 🔴

**What the newcomer saw.** Clicked **Editor** → *"Select a chapter…"* with no chapters and no way to
make one. The rail's only create button is **Act** (jargon); the rail "+" is titled *"Plan this book"*
and opens the planner. The actual write door (**＋ Write a new chapter**) is two clicks deep inside
Plan Hub → Simple mode.

**Root cause (by design, and that's the problem).** [ManuscriptNavigator.tsx:200-213](../../../frontend/src/features/studio/manuscript/ManuscriptNavigator.tsx#L200-L213)
— the `manuscript-new` "+" is *deliberately* wired to open Plan Hub ("structure authoring is a spec
act and lives on the Plan rail", 2026-07-17). The **Editor empty state**
([EditorPanel.tsx](../../../frontend/src/features/studio/panels/EditorPanel.tsx)) offers no create.
So the one screen named after writing, and the sidebar, both dead-end a newcomer whose only goal is to
type Chapter One. The friendly create *does* exist — `writeChapter` in
[PlanHubPanel.tsx:80-86](../../../frontend/src/features/studio/panels/PlanHubPanel.tsx#L80-L86)
(`createChapterEditor` → `focusManuscriptUnit`) — it's just not reachable from where the newcomer looks.

**Options.**
- **A — Write doors on the empty states (RECOMMENDED).** Put a primary **"＋ Start your first chapter"**
  on the **Editor empty state** and the **manuscript-empty state**, reusing the exact `writeChapter`
  behavior (create book chapter → open in editor). No jargon, no detour. This is the smallest change
  that removes the dead-ends the newcomer actually hit.
- **B — Real create in the rail header.** Add a genuine "New chapter (write now)" action to the
  manuscript rail (a caret menu beside "Act", or repurpose the "+"). This is a **conscious reversal**
  of the 2026-07-17 "creation lives on the Plan rail" decision → needs PO sign-off.
- **C — Make "Plan this book" land soft.** Ensure the planner opens in **Simple** for a planless book
  (see F5) so even the detour path shows the write door immediately, and relabel the rail "+" from an
  ambiguous "+" to something that reads as planning, not chaptering.

**Recommendation:** **A now** (write doors on both empty states — highest impact, no policy reversal),
**C alongside** (planless → Simple). Offer **B** to the PO as a follow-up: a lightweight rail affordance
that many writers will still expect, but only with an explicit decision to reverse the prior stance.

**Acceptance.** New book → open Editor → a primary "Start your first chapter" that creates + opens a
blank chapter in one click. Same door on the empty manuscript rail. No path to "I want to write" that
ends in *"select a chapter"* with no chapter and no button. **Size: M.**

---

## F3 — "I saved a chapter and the sidebar still said 0 chapters" 🔴

**What the newcomer saw.** After *Write a new chapter* → type → Save ("saved" ✓, footer *43 words*),
the Manuscript rail still read **"1 act · 0 ch"**. The chapter appeared only after a manual **Reload**.
To a first-timer, "I saved and it shows nothing" reads as **lost work** — the scariest possible signal.

**Root cause (confirmed).** The Manuscript navigator's data hook
[useManuscriptTree.ts:74-79](../../../frontend/src/features/studio/manuscript/useManuscriptTree.ts#L74-L79)
holds its tree in **hand-rolled `useState`**, not the react-query cache. The Plan-Hub create mutation
([PlanHubPanel.tsx:82-86](../../../frontend/src/features/studio/panels/PlanHubPanel.tsx#L82-L86))
does `qc.invalidateQueries({ queryKey: ['plan-hub','simple-chapters', …] })` — which **cannot reach**
the navigator's local state. Different panels, no shared cache, no cross-panel signal. (This is exactly
the *invalidateQueries-cannot-reach-hand-rolled-state* bug-class.)

**Options.**
- **A — Studio-bus "manuscript revision" signal (RECOMMENDED).** Add a bus slice (a monotonically
  bumped `manuscriptRevision` counter) to the studio host. Every chapter CRUD — Plan-Hub `writeChapter`
  / `renameChapter` / `deleteChapter`, the editor's create, the drawer's `childCreate` — bumps it.
  `useManuscriptTree` subscribes and calls its existing `reload()` on change. Surgical, uses the seam
  the studio already has (`focusManuscriptUnit` already crosses this bus), no data-layer rewrite.
- **B — Migrate `useManuscriptTree` to react-query.** Then `invalidateQueries` reaches it for free.
  Correct long-term, but a real refactor of a virtualized, paged, gen-guarded hook with parts/outline
  dual sources — high risk for a polish pass.

**Recommendation:** **A.** The bus revision counter is the right-sized fix and matches how the Studio
already coordinates panels. (Track B as a future consolidation if the hand-rolled hook keeps costing us.)

**Acceptance.** Create a chapter from Simple mode → it appears in the Manuscript rail and the "N ch"
count updates **without a manual Reload**. Rename/delete/move likewise reflect live. **Size: M.**

---

## F4 — First chapter auto-named `editor-2d0fc71f-…​.txt` 🟠

**What the newcomer saw.** My opening scene's chapter is titled with a raw storage filename/UUID, and
it **persists server-side** (survived reload). It also filed under "Unassigned" rather than my Act.

**Root cause (confirmed).** FE sends `title: ''`
([PlanHubPanel.tsx:81](../../../frontend/src/features/studio/panels/PlanHubPanel.tsx#L81)). Book-service
then mints the storage filename and, with an empty title, that filename is what surfaces:
[server.go:1709](../../../services/book-service/internal/api/server.go#L1709)
`filename := fmt.Sprintf("editor-%s.txt", uuid.NewString())`. The same pattern is in the MCP write path
[mcp_tools_write.go:290](../../../services/book-service/internal/api/mcp_tools_write.go#L290) — so any
caller that omits a title hits it.

**Options.**
- **A — FE passes a friendly default.** `writeChapter` sends `"Untitled chapter"` (localized) or
  `"Chapter {n}"`. Quick, but only fixes this one caller.
- **B — Book-service defaults the title when empty (RECOMMENDED).** In `createChapterRecord`, when
  `title` is blank, store a human default ("Untitled chapter") instead of leaking the filename as the
  display title. Fixes **every** caller (editor create + MCP) in one place. The filename stays an
  internal storage detail.
- **C — Display guard.** The navigator/lists never render a `*.txt` storage filename as a title — fall
  back to "Untitled chapter · {number}". Belt-and-suspenders against any legacy rows.

**Recommendation:** **B (canonical home) + C (defensive display)**. Optionally A too (a numbered
"Chapter {n}" reads nicer than "Untitled" when the ordinal is known) — but B is the one that must ship,
since the filename-as-title is the actual leak and MCP hits it too. New chapters remain inline-renameable.

**Note on "filed under Unassigned":** that's *correct* for the content-first door (no act chosen), but
combined with the ugly title it read as broken. Fixing the title largely resolves the perception; a
later nicety could offer "add to current act" from Simple mode.

**Acceptance.** Create a chapter with no title (UI or MCP) → it shows as "Untitled chapter" (or
"Chapter N"), never `editor-*.txt`. No storage filename appears anywhere in the UI. **Size: S–M**
(book-service change = a side effect → min S; cross-service live-smoke required since FE + book-service
both move).

---

## F5 — Planner opened in Advanced, not the friendly Simple 🟡

**What the newcomer saw.** Plan Hub came up in the jargon-heavy **Advanced** canvas; **Simple** was one
toggle away but unfound.

**Root cause — NOT a code bug.** The code default is Simple: `readCached()` returns `true` and the hook
defaults `simple=true`
([usePlanHubMode.ts:20-28](../../../frontend/src/features/plan-hub/hooks/usePlanHubMode.ts#L20-L28)).
What I hit was the **shared test account** carrying a persisted `plan_hub_mode_simple=false` server
preference from earlier redesign testing. A genuinely new account gets Simple.

**Options.**
- **A — Verify + move on.** Confirm on a fresh account that Simple is the landing default (expected
  pass). Low effort, likely no change.
- **B — Planless-book guard (RECOMMENDED nicety).** For a book with **no plan and no chapters**, land
  in **Simple** regardless of the stored pref (Advanced on a planless book shows the intimidating empty
  canvas — the worst first impression). Graduate to the user's pref once structure exists. This also
  reinforces F2/C.

**Recommendation:** **A to confirm, B to harden.** B is cheap and directly prevents a newcomer with a
default-Advanced pref (or a shared machine) from face-planting into the empty canvas.

**Acceptance.** Fresh account → planner lands in Simple. Any account opening a planless+chapterless book
→ Simple, even if their global pref is Advanced. **Size: XS–S.**

---

## F6 — "Act" vs "Arc": two structure systems, colliding names 🔴 (structural)

**What the newcomer saw.** Made an **Act** ("Part One") in the manuscript rail; the **Plan Hub** then
said *"No plan for this book yet."* Two hierarchies — manuscript **parts/acts** vs plan **arcs** — with
near-homophone names and no visible relationship. Could not tell which is "the real outline."

**Root cause.** These are genuinely **two different layers**: manuscript *parts/acts* are a book-service
grouping over chapters (S-02); *arcs* are composition-outline spec nodes (the plan). They serve
different purposes and legitimately coexist — but "Act" vs "Arc" is a naming trap, and nothing in the UI
explains how they relate.

**Options.**
- **A — Rename to kill the homophone (RECOMMENDED, cheap).** Manuscript grouping → "**Part**" /
  "**Section**" (never "Act", which collides with "Arc" phonetically and conceptually); keep plan
  "**Arc**", or go further to "**Storyline**" (already used in Simple-mode copy: *"Organise into
  storylines →"*). Mostly i18n + a couple of labels/tooltips.
- **B — In-UI explainer.** A one-line "what's the difference" affordance where both appear (rail header
  tooltip; Plan Hub empty state note: "Parts group your manuscript; Arcs are the plan").
- **C — Unify into one spine.** Big design + data question (do acts *become* arcs? is there one
  hierarchy?). This is a **separate structural track** (defer-gate #2), not a polish fix — flag, don't
  force.

**Recommendation:** **A + B now** (rename + explain — high clarity for low cost), and **open C as a
separate design decision** with the PO. Do not attempt C in this track.

**Acceptance.** No two sibling concepts named "Act" and "Arc" in the same product surface; wherever both
can appear, a one-line explainer states the relationship. **Size: S** (A+B). *C is out of scope (XL).*

---

## F7 — Polish bundle 🟡

- **7a — Lowercase "plan" tab.** The Studio tab bar reads *Manuscript / plan / Story Bible / …* — only
  "plan" is lowercase. Fix the i18n string casing → "Plan". **Size: XS.**
- **7b — "99+" notifications on a fresh-feeling account.** Inherited seeded/test data, but a genuinely
  new account should start at 0, and the badge could cap/soften. Mostly verify-on-fresh-account +
  ensure no default noise. **Size: XS** (low priority).
- **7c — A 2-sentence AI ask cost ~22,600 input tokens.** The co-writer preloads "48 tools · 5 skills ·
  ~12,900 tok" of context for *every* message, including a throwaway creative question. Free on the
  local model; a quiet money-burner on paid BYOK. Options: a "light" context mode for plain creative
  chat, or lazy-load tool/skill schemas only when the turn actually needs them. **This ties directly to
  the `context-budget-law` work and is likely its own task — flag, don't fold in.** **Size: M+ (spins
  out).**

---

## Sizing & sequencing

Whole-effort classification ≈ **L** (7+ semantic changes; side effects in auth, book-service, and a
cross-service seam) → **a plan file is required before BUILD**, and cross-service live-smoke is
mandatory for F3/F4 (FE ↔ book-service).

Suggested build order (cheapest-highest-impact first, dependencies respected):

1. **F4** (default title) — self-contained, removes the ugliest first impression. *BE + FE + display.*
2. **F3** (bus revision → live refresh) — kills the "looks like data loss" moment. *FE only.*
3. **F2/A + F5/B** (empty-state write doors + planless→Simple) — removes the dead-end maze. *FE only.*
4. **F1** (refresh-first + reconnecting) — stops the "logged-in but broken" flash. *FE auth layer.*
5. **F6/A+B** (rename + explain) + **F7a** (casing) — clarity polish, mostly i18n. *FE + 18-locale gap-fill.*
6. **Flag for separate tracks:** F2/B (rail-create reversal — PO decision), F6/C (unify hierarchies —
   design track), F7c (chat context budget — context-budget-law task).

## Sealed decisions (PO, 2026-07-18) — PLAN unblocked
1. **F2/B — YES, also add a rail "New chapter."** In addition to the empty-state write-doors (F2/A),
   add a real create-and-open action to the manuscript rail header. This **consciously reverses** the
   2026-07-17 "creation lives on the Plan rail" decision — recorded here as the amendment.
2. **F6/A — Rename to "Part / Arc."** Manuscript grouping "Act" → **"Part"**; plan keeps **"Arc"**.
   (Bonus: the code already uses `part`/`manuscript-part-*` internally — this is a **display-string /
   i18n-only** change, testids and data model unchanged.)
3. **F4 — Default title "Chapter {n}."** New unnamed chapters are titled "Chapter {n}" (localized,
   n = position), always inline-renameable. Never the storage filename.
