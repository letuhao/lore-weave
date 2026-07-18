# Writing Studio — cold-start first-use audit

> **Date:** 2026-07-17 · **Status: SEALED** after a 4-lens adversarial review (novelist · model-fidelity · frontend-implementability · adversary).
> **Method:** live cold-start walkthrough on the baked `:5174` prod build, driven as a first-time user.
> **Why it was run:** the Studio had never been used for real — only by tests, which seed fixtures and therefore never walk the zero-state.
>
> ⚠️ **This document was WRONG in two places on first draft.** The review corrected it. Corrections are marked ❌ **RETRACTED** / ✏️ **CORRECTED** and left visible on purpose — deleting them would hide the process failure that produced them (see §Process rule).

---

## The sealed verdict

| Decision | Outcome |
|---|---|
| **The reported blocker** | **REAL** — the Studio's Manuscript navigator cannot create a chapter. |
| **The proposed "Spine" redesign** (`design-drafts/structure-authoring/`) | **KILLED — unanimous, 4/4 lenses.** Its central premise is factually false. |
| **The fix** | **~1 day**, 4 items (§Minimal fix). Not a redesign. |
| **Open question for the PO** | Should arcs be allowed to **overlap**? Today the schema forbids it. Answering "yes" is a **backend epic**, not a GUI change. |

---

## ✏️ CORRECTED headline

**First draft said:** *"a first-time user cannot write a single word."*
**That is an overclaim.** `frontend/src/pages/book-tabs/ChaptersTab.tsx:63` creates a chapter with a plain JSON call and deep-links into the Studio:

```ts
const created = await booksApi.createChapterEditor(accessToken, bookId, {
  title: newTitle || undefined, original_language: newLang, body: newBody || undefined,
});
navigate(`/books/${bookId}/studio?chapter=${created.chapter_id}`);
```

**The honest headline:** **the Studio's navigator cannot create a chapter; the book's Chapters tab can.** It is a routing/discoverability bug in the flagship surface — real, but it does not justify a new authoring surface. The audit's walkthrough was interrupted before reaching the Chapters tab and never found this path.

---

## Findings that survive

### 🔴 BUG-1 — `New chapter` (`+`) is permanently disabled. Never wired. **[CONFIRMED]**

`frontend/src/features/studio/manuscript/ManuscriptNavigator.tsx:116` → `disabled={!onNewChapter}`.
`onNewChapter` is optional (`:33`). Its only consumer, `StudioSideBar.tsx:34`, never passes it. `grep -rn "onNewChapter" frontend/src` returns only the component's own declaration and use. **Disabled 100% of the time, every user, every book.**

### 🔴 BUG-2 — the green test locks the bug in. **[CONFIRMED]**

`ManuscriptNavigator.test.tsx:165` **injects its own `onNewChapter`**, then asserts it fires — and asserts `disabled === true` is correct. It proves the *mechanism* and can never prove the *app wires it*. Suite green, button dead. Repo's known class: *injecting a fake at the chokepoint cannot prove the chokepoint is wired.*

### 🟠 BUG-3 — dead-end empty states. **[CONFIRMED — and WORSE than reported]**

The Editor tells you to "Select a chapter in the manuscript navigator" while the navigator cannot make one. The review found the **same dead-end in three panels**, not one:
`EditorPanel.tsx:264` · `SceneComposePanel.tsx:65` · `ChapterAssemblePanel.tsx:57`.

### 🔴 BUG-8 — **NEW, and the deepest one: the zero-state has FOUR doors and all four are locked**

Found by the PO. The audit stopped at two doors; there are four, and the last two are locked in a way that changes the fix.

| Door | Why it's locked at zero-state |
|---|---|
| Manuscript `+` | **BUG-1** — disabled, never wired |
| Editor | **BUG-3** — "Select a chapter in the manuscript navigator" → the navigator has none → loop |
| plan-hub → **"Extract the plan from the manuscript"** | The decompiler reads **scenes already parsed from your chapters**. A new book has no chapters, so nothing to parse. `PlanEmptyState.tsx:98` even says it: *"Nothing to extract — this book has no parsed scenes yet."* |
| plan-hub → **"Plan from scratch"** | **Mislabelled — it is not from scratch.** It opens the `planner` (`PlanHubPanel.tsx:164`), whose Propose is hard-gated on a pre-written braindump: `PlannerPanel.tsx:120` — `canPropose = … && effectiveMarkdown.trim().length > 0 …`, placeholder *"Paste the novel-system markdown…"*. A first-time user has no novel-system markdown. |

**The only working door is outside the Studio** — the book's Chapters tab (`ChaptersTab.tsx:63`).

**This kills the "route `+` to plan-hub" fix.** Sending the `+` to plan-hub at zero-state only **relocates the dead end**: both of plan-hub's verbs are also locked. The `+` must **create something**.

**Consequence — the `+` is two different verbs, because the navigator has two sources** (`useManuscriptTree.ts:61`, `source = projectId ? 'outline' : 'chapters'`):

| Source | State | What `+` must do |
|---|---|---|
| **`chapters`** (no Work — the zero-state) | flat, book-service | **Create a chapter** via `booksApi.createChapterEditor`, then open the editor. This is the **only** door onto prose, and prose is what the user came for. |
| **`outline`** (a Work exists) | the spec tree | **Route to plan-hub** — structure authoring is a *spec* act and belongs on the rail that owns it (`StudioSideBar.tsx:42-48`: Manuscript = prose, Plan = spec). `host.openPanel('plan-hub', { focus: true })` is **already in scope in the very file where `onNewChapter` was dropped**. |

**Also fix the label.** "Plan from scratch" must either say what it needs (*"Paste a plan you've already written"*) or a genuine from-nothing path must exist. A button whose name promises the one thing it cannot do is worse than no button.

### 🔴 BUG-7 — **NEW**: `NodeKind` contract drift (found by the review, independent of the redesign)

Verified independently at both ends:

```python
# services/composition-service/app/db/models.py:37
NodeKind = Literal["arc", "chapter", "scene", "beat"]
```
```ts
// frontend/src/features/composition/types.ts:195
kind: 'arc' | 'chapter' | 'scene' | 'beat';
// …and :240 disagrees with itself — 'arc' | 'chapter' | 'scene' (no beat)
```

But post-lift the DB enforces `kind IN ('chapter','scene')` (`arc_lift.py:285-287`). So `kind:'arc'` **passes Pydantic and fails at the database** → 400 CONSTRAINT (`outline.py:574-575`). Anyone reading the types builds the wrong thing — as this audit's own author did. **Fix the types to match the DDL.**

---

## ❌ RETRACTED

### BUG-4 — "/onboarding bounces to /books" — **NOT A BUG. Test-account contamination.**

`OnboardingPage.tsx:13-14`:

```tsx
if (isLoading) return null;                    // ← already guards the flash
if (!shouldShow) return <Navigate to="/books" replace />;
```

The redirect fires **only when the server-side seen-flag is set**. The test account has 20 pre-existing fixture books — to the server it is a **veteran**, not a new user. A genuinely new user gets `IntentScreen`. `OnboardingPage.test.tsx:50` asserts the skip is *intended*.

**The audit role-played a first-time user on an account that was not one, then reported the veteran path as the new-user bug.** Any future cold-start audit must run on a **clean account**.

### BUG-5 — "two competing entry points" — **downgraded to a copy nit.** A designed distinction exists: `/onboarding/new` is the intent fork (`forceShow`, `App.tsx:159`); `+ New Book` is direct create.

---

## ❌ RETRACTED — the design-gap thesis

**First draft claimed:** *"the Work bootstrap already exists behind the Compose panel and creates a guided first run — the route in exists, it's just undiscoverable."*

**False.** `CompositionPanel.tsx:66` takes **`chapterId: string` — required** — and its bootstrap creates `{ kind: 'scene', chapter_id: chapterId }` (`:292`). It needs a chapter to **already exist**, and it creates a **scene**, not a chapter. **It cannot be the first-run path.** The audit oversold it and built its "route in already exists" thesis on it.

---

## Why the Spine was killed — 4/4 unanimous

The draft's load-bearing claim: *"an arc is a SPAN across chapters, and arcs OVERLAP; in a tree a chapter has ONE parent, so overlap is unrepresentable."*

**Every part of that is false.**

| Claim | Reality |
|---|---|
| Arcs overlap | `migrate.py:1242` — `outline_node.structure_node_id UUID REFERENCES structure_node(id)` is a **scalar FK**, `CHECK (structure_node_id IS NULL OR kind='chapter')`. **One chapter → at most one arc.** No join table exists. |
| `assign-chapters` models span | `structure.py:635` — `UPDATE outline_node SET structure_node_id = $1`. A **destructive re-home**: assigning ch3 to Auger *silently unassigns it from Vesna*. `null` = unassign. |
| The model isn't a tree | It **is** a tree. `structure_node.parent_id` (`:1162`), `kind IN ('saga','arc')`, `depth 0–2`. `migrate.py:1254`: *"a chapter node has parent_id NULL and attaches to its arc via structure_node_id"* — a parent pointer in a second column. |
| 4 kinds = 4 lanes | Post-lift `outline_node.kind IN ('chapter','scene')` (`arc_lift.py:285`). **`arc` and `beat` are not legal kinds.** The service **refuses to boot** if the 4-kind CHECK still stands (`_assert_lift_applied`, `migrate.py:1891`). |
| `migrate.py:196` proves 4 kinds | **Stale citation.** Line 196 is the fresh-DB `CREATE TABLE` text, later ALTERed. The running code will not serve it. |
| Beats are a lane | `beat_role` is a **field on a scene/chapter** (`:214`), not a node. |
| "Just type in the lane" | `outline_chapter_required` (`:212`) makes a **book-service chapter row a precondition**. Composition doesn't own chapter creation. |

**Three more independent kills:**

1. **It doesn't fit.** `StudioSideBar.tsx:29` is `w-[250px] flex-shrink-0`, **not resizable**. The spine needs **512px minimum** — 2.2×. Its own `@media (max-width:760px)` abandons the lane concept at the width it would actually run at.
2. **It duplicates a shipped surface.** `plan-hub` **already is the spine** — `LaneBandLayer.tsx`, `laneLayout.ts` with `span:{from_order,to_order}` + `is_contiguous`, segmented bands, `UnplannedTray`, `PlanEmptyState` with two verbs. And `laneLayout.ts`'s header forbids exactly this: *"never a second 'where does a node go' impl."* Worse, `StudioSideBar.tsx:42-48` defines the rail contract — **Manuscript = prose, Plan = spec** — and the spine puts the spec in the prose rail, destroying the one rule that keeps them unambiguous.
3. **It doesn't scale, and it doesn't fix the bug.** The navigator is virtualized (`@tanstack/react-virtual`, `PAGE=100`, built for 10k chapters). `subgrid` + absolute `grid-column` spans **cannot window** — at 120 chapters it's ~7,200px of live DOM. And as a *new panel* it leaves the dead `+` and all three dead-end empty states untouched: **it does not fix the bug it was commissioned for.**

**The novelist's kill, independent of all the above:** at real scale (7 arcs, 61 chapters) *everything* overlaps — that's what a novel is. The band would be a uniform red hatch. It renders the best moment in the book (`--destructive`, dashed, `Vesna × Auger`) as a **merge conflict**. And nothing on the spine has a name: chapters are numbers, scenes are anonymous 16px bars, beats are 5px dots. *"The fix has the same symptom as the bug — there is not one sentence of prose in any of its four states."*

---

## What survives from the design

| Idea | Verdict |
|---|---|
| **`status` as colour** (`empty·outline·drafting·done`) | **Keep.** Real enum (`migrate.py:203`, `:1171`). Scrivener-proven. Put it on the **tree**. |
| **Provenance: mine vs machine** | **Keep the idea, kill the mechanism.** Real data: `source CHECK IN ('authored','mined','imported')`; the decompiler never overwrites an authored node. But amber/teal **collides with live meanings** — amber `--primary` already = *selected*, teal `--accent` already = **arc** in the very same navigator (`:281,299,313`). Ship a **badge bound to `source`** (~5 lines), not a typeface nobody decodes. |
| **Inline typing, not a modal** | **Keep.** Right instinct, wrong surface — apply to a binder row. |
| **Honest `87.2s · $0.00`** | **Keep.** A spinner that lies about 87 seconds is worse than a number that doesn't. |
| The lane timeline as the primary surface | **Killed.** |

---

## 🔴 THE ROOT FINDING — SEALED

> **The Studio has no origin point. The UX is a dead loop by construction.**

Every surface assumes content already exists:

| Surface | Assumes |
|---|---|
| Manuscript `+` | (dead — never wired) |
| Editor / SceneCompose / ChapterAssemble | a chapter already selected |
| `CompositionPanel` | **`chapterId` — required** (`:66`); creates a *scene*, not a chapter |
| plan-hub → Extract | chapters already parsed |
| plan-hub → "Plan from scratch" | a novel-system markdown **already written elsewhere** |

**Nothing in the Studio creates the first thing.** That is not a wiring bug — it is a hole in the design. Each surface was built assuming an upstream surface had already run, and no one owns "there is nothing yet".

**But the origin point already exists in the backend, and nobody gave it a button:**

```python
# services/composition-service/app/routers/arc.py:590
@router.post("/books/{book_id}/arcs", status_code=201)
async def create_arc(book_id, body: ArcCreate, ...):
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    node = await _structures().create_node(book_id, kind=body.kind, title=body.title, ...)
```

- Creates a `structure_node` (arc/saga) from **nothing** — only `book_id` + `kind` + `title`.
- **Book-scoped — it does NOT need a `composition_work`** (arcs live in `structure_node`, keyed by `book_id`, not `project_id`). So it works at true zero-state.

**And the frontend never wired it:**

| Layer | State |
|---|---|
| `plan-hub/api.ts:22` | `getArcs()` — **read only** |
| `plan-hub/api.ts` | **no `createArc`** — the only arc POST is `assign-chapters` (`:251`) |
| `usePlanNodeWrites.ts` | `edit` (`:66`) · `archive` (`:80`) · `restore` (`:86`) — **no create** |
| `PlanEmptyState.tsx` | two verbs, **both locked at zero-state** |

**This is the repo's own engines-gated-on-GUIs pattern, in its purest form: the create route has existed the whole time and has never had a caller.**

### Is there a second dead loop at Work + book + KG? — **NO. Checked.** (PO question, 2026-07-17)

The Work/KG chain is **clean, idempotent, and outage-resilient**. It is not the problem.

`POST /books/{book_id}/work` (`works.py:163`) — *"Confirm-create a Work (idempotent). **Ensures a book-typed knowledge project exists (resolve, else ProjectCreate)**, then get-or-creates the composition_work row."*

- **One call does book → Work → KG project.** It needs only `book_id` + an EDIT grant. **No chapters. No pre-existing KG.**
- **Idempotent + race-safe** — a duplicate click never mints a second Work.
- **C16 outage seam:** if knowledge-service is down, a greenfield Work is created with a **null `project_id` + `pending_project_backfill`** marker (capped at one per book by a partial-unique index) *"so drafting + Generate keep working"*; `usePendingWorkResolver` polls `resolve-project` and backfills. Only a **derivative** Work 502s (C23 guard).

**So the Work origin exists — and so does a finished GUI for it.** `WorkSetupCta.tsx` is idempotent, race-safe, and already handles the pending/backfill poll. Its own header documents **this exact bug class, one layer up**:

> *"Every S6 quality panel gates on a composition Work (`useQualityWork` → `no-work`). The GUI-only affordance that CREATES one … **was mounted ONLY on the legacy `CompositionPanel`**, so a GUI-only user in the Studio hit `no-work` **with no self-service exit** (their only options were to talk to the agent or leave for /edit)."*

Someone hit this, diagnosed it correctly, and built the shared fix — **then mounted it in the Quality panels only**:

| Surface | Has `WorkSetupCta`? |
|---|---|
| `QualityHubPanel.tsx:51` · `QualityNoWorkState.tsx:74` | ✅ |
| **Manuscript navigator** | ❌ |
| **plan-hub / `PlanEmptyState`** | ❌ |
| **Editor / SceneCompose / ChapterAssemble** | ❌ |

**The same bug, twice, one level apart: a correct, shared, self-service affordance mounted in exactly one place and invisible from everywhere a writer actually starts.** A first-time user would have to open the *Quality* panel — of an empty book with nothing to measure — to find the button that bootstraps their book.

**Consequence for the fix: `PlanEmptyState` should mount `WorkSetupCta`, not reinvent it.** The origin point is a *mounting* problem, not a building problem.

### The sealed design decision

**plan-hub owns the origin point.** It gets a genuine create-from-zero — the third verb `PlanEmptyState` is missing:

1. **`PlanEmptyState`** — add a real from-nothing verb (*"Start with your first arc"*) that calls `POST /books/{id}/arcs`. It is the only one of the three that works with an empty book. It should be the **primary**; the other two are for books that already have something.
2. **`plan-hub/api.ts`** — add `createArc(bookId, {kind:'arc', title}, token)`.
3. **`usePlanNodeWrites.ts`** — add the missing `create` verb.
4. **Relabel "Plan from scratch"** — it is not from scratch; it demands a pre-written markdown. Say what it needs, or don't promise it.

**The `+` in Manuscript is TWO verbs, by source** (`useManuscriptTree.ts:61`):

- **`source==='chapters'` (zero-state)** → **create a chapter** (`booksApi.createChapterEditor`) and open the editor. The only door onto *prose*, which is what the user came for. Routing to plan-hub here would only relocate the dead end.
- **`source==='outline'` (a Work exists)** → **route to plan-hub** — structure authoring is a *spec* act, and the rail contract (`StudioSideBar.tsx:42-48`) says Manuscript = prose, Plan = spec. `host.openPanel('plan-hub', {focus:true})` is **already in scope in the exact file where `onNewChapter` was dropped** (`StudioSideBar.tsx:24,51`).

---

## The minimal fix — SEALED (~1 day)

1. **`StudioSideBar.tsx:34`** — pass `onNewChapter`. **~10 lines, not 1**: in the zero-state `useManuscriptTree.ts:61` resolves `source = 'chapters'` (no Work), so the navigator is reading **book-service**. The handler must call `booksApi.createChapterEditor(...)` — **not** `compositionApi.createNode` — reusing ChaptersTab's proven call, then select the result.
2. **`ManuscriptNavigator.test.tsx:165`** — delete it. Replace with a test that renders **`StudioSideBar`** (the real consumer) and asserts the button is **enabled**. Only a test that mounts the chokepoint's *caller* can catch this class.
3. **Three empty states** — `EditorPanel.tsx:264`, `SceneComposePanel.tsx:65`, `ChapterAssemblePanel.tsx:57` — name the action and render the button. Same handler as (1).
4. **BUG-7** — fix `NodeKind` in `app/db/models.py:37` + `types.ts:195` (and the self-contradicting `:240`) to match the DDL (`'chapter'|'scene'`).

**Deferred, needs the PO:** whether arcs should overlap. If **no** → the tree was right; show arc membership as a badge bound to `structure_node_id`. If **yes** → schema migration (join table) + rewrite `assign_chapters`, `derived_blocks`, the decompiler, conformance, the MCP tool and `frontend-tools.contract.json` — **a backend epic**, rendered in `plan-hub`, never a rival canvas.

**The genuine GUI gap the redesign buried:** `plan-hub`'s `usePlanNodeWrites.ts` has `edit`/`archive`/`restore` but **no create**. Arc creation belongs there, on the canvas that already renders arcs.

---

## Process rule — SEALED

> **Quote the DDL, not the endpoint name.**

Two documents cited `migrate.py` and `assign-chapters`; neither opened the column definition. An endpoint called `assign-chapters` was read as many-to-many span semantics, written into a CSS comment as established fact, and a timeline was built on it. The schema said the opposite the whole time.

Compounding it: **`migrate.py:196` was quoted from the `CREATE TABLE` block while a later `ALTER` (`arc_lift.py:285`) superseded it.** Read *every* CHECK block, not the first one — the running code refuses to boot on the version that was cited.

**And: run cold-start audits on a clean account.** One finding here (BUG-4) was pure contamination from a 20-fixture veteran account.
