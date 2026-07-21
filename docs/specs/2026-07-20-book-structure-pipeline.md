# Book Structure Pipeline — centralize the scattered manuscript entity model

**Status:** DRAFT v2 — design cycle, 2026-07-20. Adversarially reviewed (3 cold-start reviewers:
data-flow, business/lifecycle, UI/UX → ~30 grounded findings, folded in below). For final review.
**No code in this pass.**

**Origin:** dogfood Bug 4 (a manuscript *Part* vanishes after reload). Root-caused to scattered
book-structure ownership + an implicit Work-coupling + a **silent read-skip**. Confirmed against the
user's real book `019f7719-…` (its `composition_work` — `project_id 019f772e-…` — survived the
data-loss incident and matches the chat session's `project_id`, proving the book was in outline mode).
**User directive:** *"centralize our logic — it's scattered and it causes this. A centralized pipeline
that auto-creates missing entities… no check and silent error — for humans and agents."*

**What the review changed (v1 → v2):** kept the core (a unified read fixes Bug 4 — all 3 reviewers
agree); **flipped the resolver owner** to book-service; **dropped** eager provision-at-book-create (a
category error — parts need no Work); **rescoped P4** (a description is a book field, not structure);
**added** lifecycle cascade + write-side/FE silent-seam coverage; **replaced** the "one big tree" with a
paginated skeleton; and settled the manuscript-rail model (mode-by-content + toggle).

---

## 1. The canonical symptom (Bug 4)

A user's LLM-authored book (co-writer chapters) groups Chapter 1 & 2 into "Part 1". It shows in-session;
on reload it is **gone**. The data is fine (API repro proved the part + chapter→part links persist). The
FE `useManuscriptTree` loads parts **only** in `'chapters'` mode (`if (source !== 'chapters') return;`,
useManuscriptTree.ts:188), and `rawSource = projectId ? 'outline' : 'chapters'` — so a book with a real
Work is in `'outline'` mode and its parts are **never fetched**. No error, no check — a silent vanish.

---

## 2. The fragmented model (map)

One conceptual "book manuscript" is split across two services with independent scope keys, a cross-service
FK-by-id, scattered auto-provision seams, and 5+ FE read paths.

| Entity | Service · table | Scope key | Notes |
|---|---|---|---|
| Book | book-service · `books` | `owner_user_id` | soft-delete lifecycle (active→trashed→purge_pending) |
| Chapter | book-service · `chapters` | `book_id` | **holds the join key** `structure_node_id` → a composition part; title, `sort_order`, lifecycle here |
| **Part (act)** | composition · `structure_node` kind=`part` | **`book_id`** (flat int rank) | **Work-INDEPENDENT**; import-origin today (Studio books have none) |
| Outline (arc/scene) | composition · `structure_node` kind=`arc`/`scene` | **Work** (`project_id`, LexoRank) | the planned structure; per-user *active* Work; C23 derivatives → N Works/book |
| Work | composition · `composition_work` | `book_id` (+ `project_id`) | **pending** (`project_id=null`, FE-invisible) vs **canonical/real** (`project_id` set, flips FE to outline) — *two different facts* |

**The three fault lines** (review-confirmed):
1. **Ownership vs data location.** The join key (`chapters.structure_node_id`), titles, order, and
   lifecycle are all in **book-service**; composition holds only the part title+rank. Composition's only
   chapter door (`BookClient.list_chapters`) **drops `structure_node_id` and silently truncates at 2000**
   (FE expects 6000). ⇒ book-service is the correct resolver owner.
2. **Independent scope keys the reader couples anyway.** Parts are `book_id`-scoped and Work-independent;
   the FE decides *whether to read them at all* from Work presence — the coupling that IS Bug 4.
3. **Silent seams on every side.** Reads skip parts on a mode guess; **writes are unvalidated**
   (`book_chapter_set_part` accepts any UUID — an arc id, a foreign-book part); the **FE swallows** every
   part-mutation error (`void partsApi.X()` → a failed create/move shows nothing, reverts on reload);
   **lifecycle** trash/purge/restore emits no event and orphans composition state; **import** best-efforts
   parts and silently flattens on a composition blip.

---

## 3. Root cause (one sentence)

**No component owns "the book's manuscript structure"**, so every consumer reverse-engineers it from
scattered, independently-scoped reads — and when the guess skips an independently-scoped entity, it
**silently disappears**.

---

## 4. Design (v2)

### 4.1 Owner: **book-service** (flipped from v1)
Book-service holds the chapter SSOT + the join key + lifecycle in one indexed query
(`idx_chapters_structure_node`); it calls composition only for the **small, bounded** part list
(`GET /v1/composition/books/{id}/parts`). The agent `book_get_structure` tool (P4) also lives here
(book-service already hosts the manuscript MCP tools). Composition stays the SSOT *writer* of part nodes;
book-service composes the tree.

### 4.2 The unified read — a **skeleton**, not one unbounded tree
`GET /v1/books/{book_id}/structure?work_id=<active|explicit>` →
```
{ book_id, kinds_present: { parts: bool, outline: bool },   // drives the rail model (4.3)
  parts:  [ { part_id, title, sort_order, chapter_count } ],          // headers + counts, NOT inline chapters
  unassigned_count,
  outline?: { arcs: [ { arc_id, title, chapter_count } ] },           // present iff the active Work has one
  active_work: { work_id, project_id|null } }
```
- **Parts are always resolved** (they are `book_id`-scoped; Work presence is irrelevant to reading them)
  → Bug 4 cannot recur.
- **Paginated by design.** The resolver returns headers + counts; a part's/arc's chapters are
  cursor-loaded on expand (reuse today's `loadPage`) — preserving the lazy behavior + the 6000-cap the FE
  already relies on. **No single unbounded payload.**
- **Work-aware, not book-keyed-only.** The read takes the caller's **active Work** (per-user, per-book
  pref; explicit `work_id` for a derivative). Two collaborators with different active derivatives get
  different `outline` from the same `book_id`.
- **Join safety.** Grouping is `LEFT JOIN structure_node ON id=chapters.structure_node_id AND kind='part'
  AND book_id=$ AND NOT is_archived`. A chapter whose link points at an arc / foreign / archived / missing
  node falls to **Unassigned** — never dropped, never filed under an arc.

### 4.3 Manuscript-rail model — **mode-by-content + toggle** (the settled UX)
Driven by `kinds_present`:
- **parts only** → parts-view (`Part → chapters`); **no** "Unassigned" bucket header if there are zero
  real parts (a partless book stays a flat list — never an amber "unfiled" banner).
- **outline only** (today's co-writer book) → the existing arc→chapter→scene view, **unchanged** (no
  regression — this was the v1 land-mine).
- **both** → a small **[Parts | Outline]** lens toggle (per-device pref); each lens groups the same
  chapters by its axis. Bug 4's book (arcs + a Part) now shows the toggle → Part 1 is reachable.
- **neither** → flat chapter list.

The toggle makes the two orthogonal groupings (a chapter's part vs its arc) **user-visible on demand**
instead of silently divergent. Deep scene navigation stays in plan-hub.

### 4.4 Auto-provision — consolidate, never *eager* at book-create (rescoped from v1)
The review killed "provision a Work at book-create": **parts need no Work** (create_part provisions
nothing), a *pending* Work is FE-invisible (no-op), and a *real* Work at create-time flips every book to
outline mode + mints an owner-only knowledge project per book (harmful). So:
- **No provisioning is required for the manuscript-parts rail** — it already "just works."
- The genuine auto-provision surface is the **outline/Work** path, which *already* has `_ensure_work`
  (canonical-first, at-most-one, race-safe). **Consolidate the 3 divergent copies onto that
  canonical-first primitive**; never expose the pending-only shape as a callable at a new write-site (that
  reintroduces the F5 fork-Work bug). Ensure-**on-write** only (a read never mutates).
- **No "create X first" wall** for humans or agents: writing a part, an outline, or a description each
  self-provisions its (already-present-or-cheap) prerequisites — but none forces a Work onto a book that
  doesn't want one.
- **Kind-gate:** provisioning/structure applies to `kind='novel'` only — **never `diary`** (system
  workspace, hard-deleted, must not get a manuscript structure).

### 4.5 No silent seams — read **+ write + FE**
- **Read:** never drops an entity on a mode guess (4.2 removes the guess; the LEFT JOIN degrades to
  Unassigned).
- **Write:** `book_chapter_set_part` / `moveChapterToPart` **validate the target** (must be a live
  `kind='part'` in *this* book) and return a **typed error** on a bad target — no more "any UUID."
- **FE:** every part mutation surfaces its error (toast on create/rename/trash/reorder; a failed
  chapter-drag snaps back **and explains why**). Kill the `void partsApi.X()` swallow.

### 4.6 Lifecycle cascade — the omission v1 missed
Book trash/purge/restore must reach composition. Add a **`book.lifecycle_changed`** outbox event
(book-service) consumed by composition to soft-trash / restore / hard-delete the book's `structure_node`
+ `composition_work` + derivatives — **and** the resolver joins book lifecycle so it never renders live
parts over a trashed book. (Also re-emits the per-chapter `chapter.trashed` the bulk path currently
skips.) This closes the orphan/leak + the "live parts over a dead book" hole.

---

## 5. Delivery phases (revised)

| Phase | Delivers | Fixes / closes |
|---|---|---|
| **P1 — unified read + rail model** | book-service `/structure` skeleton (paginated, Work-aware, LEFT-JOIN-safe) + FE reads it once + the mode-by-content/toggle rail | **Bug 4**; the read-side silent skip; the unassigned-bucket mislabel |
| **P2 — write & FE silent-seams** | target validation + typed errors on the part writers; FE surfaces every mutation error; mobile "Move to part…" affordance | the "silent error" class on the write/FE side; the touch gap |
| **P3 — lifecycle cascade** | `book.lifecycle_changed` event + composition consumer; resolver joins book lifecycle; kind-gate | orphans/leaks; live-parts-over-dead-book |
| **P4 — agent + guidance (rescoped)** | `book_get_structure` (structure) **and** clear tool-selection guidance across structure vs `book_update_meta` (fields) — or a combined `book_get_overview` | **Bug 2** (correctly: metadata-vs-structure disambiguation, not structure-only) |
| **P5 — cleanup** | consolidate the 3 `ensure_work` copies; retranslate "part" in all 18 locales + fix the "Act One" arc seed; route `parts_import` + the arc-grouped Chapter Browser through the pipeline | the terminology + the remaining divergent reads |

P1 stays the shippable, self-contained Bug-4 fix and lays the resolver every later phase builds on.

---

## 6. Correctness must-fixes (independent of phase)

- **Migration id-equivalence (verify before trusting).** The C4 `DROP TABLE parts` assumes the composition
  part-mirror kept the **same UUIDs** as the old book-service parts. If it re-keyed, every pre-C4 grouped
  chapter points at a dead id → all fall to Unassigned (Bug 4 at migration scale). Add a verification test.
- **Chapter-count truncation.** Whatever chapter read the resolver uses must be **exhaustively paged with
  an explicit `truncated` signal** — never a silent 2000/limit ceiling.
- **`has_work` is two bits.** "A Work row exists" ≠ "project-backed `hasWork`". Define both; consumers
  (onboarding door, quality CTAs) key on the project-backed bit; the door reflects *pending* not *absent*.
- **Outline/part identity reconciliation.** A chapter's manuscript id (`chapter_id`) and its outline node
  id differ; the resolver stamps `chapter_id` onto outline chapter nodes so a consumer can correlate them.

---

## 7. Decisions (sealed with the user + review)

1. **Rail = mode-by-content + toggle** (§4.3).
2. **Resolver owner = book-service** (§4.1).
3. **No eager provision at book-create; ensure-on-write, consolidated, kind-gated to novel** (§4.4).
4. **Parts (manuscript) vs outline (planning) stay distinct axes**, made co-visible only via the toggle —
   never silently merged; "part" is the manuscript term in ALL locales.
5. **P4 is metadata-vs-structure disambiguation**, not a structure-only tool (§5 P4).
6. **Assume C-merge C4 write-cutover live**; do not re-open C-merge (but verify id-equivalence, §6).

## 8. Remaining open questions (small)

- Toggle persistence: per-device (localStorage) or per-book server pref (like reading position)? (Lean:
  per-device v1.)
- Grantee on a bare book: a grantee-triggered *pending* Work (owner must finish the real project) —
  acceptable UX, or surface "owner must set up writing first"? (Lean: pending is fine; surface it.)
