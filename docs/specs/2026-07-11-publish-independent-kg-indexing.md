# Spec: Publish-Independent KG Indexing

**Date:** 2026-07-11 · **Size:** L→XL (4 services: book-service, knowledge-service, **worker-infra**,
**composition-service**) · **Status:** CLARIFY/DESIGN **v2** — v1 was red-teamed and **failed** ("do not build
as written"): it modelled the world as *one predicate in one sweeper*, when **"canon = published" is
duplicated in ≥6 places across 4 services**. v2 fixes all 4 P0s + 5 P1s (§8 review record). Ready for PLAN.

**Priority: build BEFORE the Work Assistant feature.** The diary's "keep entry" is a consumer of this, and
this change stands alone for every writer.

**Origin:** spun out of [`2026-07-11-work-assistant-mode/00-overview.md`](2026-07-11-work-assistant-mode/00-overview.md)
§4.7/D15 because it is platform-wide. All facts below are code-verified (file:line).

---

## 1. The problem

Today a chapter reaches the knowledge graph **only by being published**: `mcpPublishChapter` pins a revision
into `chapters.published_revision_id`, sets `editorial_status='published'`, and emits `chapter.published`,
which knowledge-service extracts from (mcp_actions.go:576-609; handlers.py:136).

That is a *fiction* property ("canon = published; a novel's drafts aren't canon"). It doesn't generalize:

- **Writers draft without publishing** and still want their glossary/KG built.
- **Some book kinds have no publish at all** (`kind='diary'` — private, never published).
- **The content already exists**: draft saves already snapshot `chapter_revisions` (mcp_tools_write.go:656-676).

**Goal:** **publish** means *"this is the canonical/shareable version"* — nothing more. **Indexing**
("add this to my knowledge") becomes an explicit, independent act on any chapter of any kind, draft or published.

---

## 2. Current state — the coupling is NOT in one place (verified)

### 2.1 Six writers set `published_revision_id`. v1 knew about one.

| # | Site | Sets `last_parsed_revision_id`? | Service |
|---|---|---|---|
| 1 | `mcp_actions.go:582` (MCP publish) | yes (:595) | book |
| 2 | `server.go:2395` (REST publish) | yes (:2414) | book |
| 3 | `parse.go:291` (sync .txt import auto-publish) | yes | book |
| 4 | **`import.go:392`** (bulk import auto-publish) | **NO — relies on the sweeper** | book |
| 5 | `import_processor.go:304` | yes | **worker-infra** |
| 6 | `import_processor_pdf.go:180` | yes | **worker-infra** |

**worker-infra writes book-service's `chapters` table directly** — a second service in the blast radius that
v1 never named. And the sweeper is the **scenes-parser of last resort** for #4 (reparse_sweeper.go:21-23:
*"on first run every already-published chapter … is stale by predicate … so it gets indexed once"*).

### 2.2 Five *readers* independently re-implement "canon = published"

| Consumer | Gate | Where |
|---|---|---|
| Reparse sweeper | `editorial_status='published' AND published_revision_id IS NOT NULL AND last_parsed_revision_id IS DISTINCT FROM published_revision_id` | reparse_sweeper.go:74-84 |
| **worker-ai whole-book rebuild** | `list_chapters(book_id, editorial_status="published")` — *"CM3c — canon=published gate"* | runner.py:1116-1126 |
| **L3 passage backfill / ingester** | `editorial_status="published"` | passage_backfill.py:48; passage_ingester.py:574 |
| **Extraction cost estimate** | `editorial_status='published'` (so the preview matches the gated rebuild) | book_client.py:81-84 |
| **composition-service** (Python!) | hand-copied mirror of the sweeper's WHERE clause for the `index_stale` badge | arc_conformance_orchestrate.py:337-345 |

### 2.3 The cache-invalidation blast radius

`chapter.scenes_reparsed` → knowledge-service `handle_chapter_scenes_reparsed` → **`ExtractionLeavesRepo.delete_by_book(book_id)`**
— **book-scoped**, verified (handlers.py:609-660; and server.go:2418-2421 says so out loud: *"whose knowledge
consumer wipes the WHOLE book's extraction cache (a costly re-extract for zero index change)"*).

Today that's tolerable because **publish is rare and deliberate**. This spec makes indexing a *casual, frequent
click* — so this is now load-bearing (§3.3).

### 2.4 The `chapter.saved` trap (unchanged from v1 — still correct)

`chapter.saved` fires on **every autosave + restore**, payload `{book_id}` only (mcp_tools_write.go:585,674),
and knowledge-service **deliberately un-registered it** (main.py:246-251: *"so unreviewed draft prose never
canonizes"*). **This spec never touches it.** The new trigger is a distinct event.

---

## 3. Design

### 3.1 The pointer

```sql
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS kg_indexed_revision_id UUID;  -- no FK (mirrors last_parsed_revision_id)
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS kg_exclude BOOLEAN NOT NULL DEFAULT false;

-- Backfill: makes the new sweeper predicate behaviorally identical on today's corpus (proof in §6).
UPDATE chapters SET kg_indexed_revision_id = published_revision_id
 WHERE editorial_status = 'published' AND published_revision_id IS NOT NULL;
```

`kg_indexed_revision_id` = **the revision the knowledge layer (and the scene index it depends on) reflects.**
`kg_exclude` = the explicit replacement for the control publish-gating gave implicitly.

### 3.2 ALL SIX writers set the pointer (P0-1)

Every site in §2.1 that sets `published_revision_id` must set `kg_indexed_revision_id` **in the same
statement** — including the two in **worker-infra**.

**`import.go:392` is the dangerous one:** it publishes *without* setting `last_parsed_revision_id` and inserts
no scenes rows, relying on the sweeper. If it doesn't set the new pointer, the new sweeper predicate
(`kg_indexed_revision_id IS NOT NULL`) makes every **newly imported** book **invisible to the sweeper forever**
→ scenes never parsed → `extraction_leaves.scene_id` has nothing to key on → KG extraction silently degrades to
the no-scenes fallback. *The migration backfill hides this on existing books, so a smoke test on today's corpus
would pass while every future import is broken.*

**Hygiene test (required):** a grep-based test asserting every writer of `published_revision_id` also writes
`kg_indexed_revision_id` (the repo's "one name for one concept" drift class).

### 3.3 The action — and the real cost model (P0-4)

The **"index / add to knowledge"** action mirrors `mcpPublishChapter`'s Tx shape (mcp_actions.go:538-616):

1. Read the live draft; apply the **same empty-prose guard** publish uses (mcp_actions.go:562-574).
2. Snapshot into `chapter_revisions` — **reuse the latest revision if the draft is byte-identical** (compare
   `draft_version`/content hash) to avoid revision spam.
3. `UPDATE chapters SET kg_indexed_revision_id = <rev>`.
4. Parse scenes for that revision (`upsertChapterScenes`) and advance `last_parsed_revision_id`.
5. Emit **`chapter.kg_indexed`** `{book_id, chapter_id, revision_id}`.

**⚠️ The cache-wipe fix — v1 was self-contradictory here.** Steps 4's existing callers emit
`chapter.scenes_reparsed`, whose consumer runs **`delete_by_book`** (§2.3). On a 200-chapter book, indexing
*one* chapter would delete **all 200 chapters'** cached extraction leaves → the next extraction re-pays LLM
cost for the whole book. v1's claim that *"caches short-circuit the LLM"* was **false for the changed-draft
case — i.e. the normal case** — because the very event it emits **deletes that cache**.

**Required fix (do this first, it also improves today's publish path):** make the invalidation
**chapter-scoped** — add `ExtractionLeavesRepo.delete_by_chapter(chapter_id)` and have
`handle_chapter_scenes_reparsed` use it (the event already carries `chapter_id`). Book-wide invalidation
remains available for the explicit `/invalidate-cache/{book_id}` route.

> **⚠️ CORRECTION (2026-07-11, during WS-0.1 BUILD — this paragraph was wrong and the error was a trap).**
> "The event carries `chapter_id`" is true, but it made the fix *sound* like a trivial re-key. **The
> `extraction_leaves` TABLE had no `chapter_id` column.** Its only chapter-ish key was `scene_id`, which
> production writes as `scene_id := chapter_id` — an explicit **placeholder** (`pass2_orchestrator.py`:
> *"placeholder until per-scene fanout"*, D-P2-PER-SCENE-FANOUT). Keying the DELETE on `scene_id` passes
> every test today and silently matches **zero** rows the moment real per-scene fanout lands → a stale
> extraction cache the graph then re-derives from → a **correctness** bug, not merely a cost bug.
> **As built:** a real `extraction_leaves.chapter_id UUID NOT NULL` column, backfilled `:= scene_id`
> (correct by construction for every pre-existing row), set by **both** `claim_pending` callers.
> NOT NULL so a future writer that forgets it fails loudly instead of orphaning an unreachable leaf.

**Churn control:**
- Indexing fires **only** on the explicit action. **The idle-debounce is REMOVED from v1** (it was
  auto-indexing on a timer — precisely the thrash this spec claims to prevent). It may return only after
  the chapter-scoped invalidation lands, and then only opt-in per project. **Default: no debounce.**
- **Never** on autosave; `chapter.saved` stays unconsumed.
- Re-indexing an **unchanged** revision is a genuine no-op (pointer unchanged; scenes unchanged ⇒ no
  `scenes_reparsed` ⇒ no invalidation; knowledge's leaf cache hits).

### 3.4 The sweeper — the FULL query, not just the WHERE (P1-5)

v1 showed only the `WHERE`. The sweeper also **SELECTs and JOINs on `published_revision_id`**
(reparse_sweeper.go:74-84) and stamps `last_parsed = t.publishedRev` (:160-162). Re-keying only the WHERE
would (a) drop draft-indexed chapters at the inner JOIN — the exact case we're adding — and (b) for a
published-**and**-draft-indexed chapter, parse the *published* body and stamp `last_parsed = A`, which never
equals `kg_indexed = B` → **stale forever → an infinite re-parse loop**.

```sql
SELECT c.id, c.book_id, c.kg_indexed_revision_id, ..., r.body::text
  FROM chapters c
  JOIN chapter_revisions r ON r.id = c.kg_indexed_revision_id      -- ← re-keyed
 WHERE c.kg_indexed_revision_id IS NOT NULL
   AND c.kg_exclude = false
   AND c.lifecycle_state = 'active'
   AND c.last_parsed_revision_id IS DISTINCT FROM c.kg_indexed_revision_id
```

Rename `sweepTarget.publishedRev` → `indexedRev`; stamp `last_parsed_revision_id = indexedRev`. Re-key
`reparseOneChapter`'s concurrent guard (reparse_sweeper.go:144-151) from
`WHERE published_revision_id=$2 AND editorial_status='published'` → `WHERE kg_indexed_revision_id=$2`.

### 3.5 Generalize the publish gate in EVERY reader (P0-2)

Add a server-side **`kg_indexed`** filter to `GET /internal/books/{book_id}/chapters` (the `editorial_status`
filter lives at server.go:1105-1117, :2885-2893), meaning `kg_indexed_revision_id IS NOT NULL AND kg_exclude = false`,
and re-point every reader in §2.2 at it:

| Reader | Change |
|---|---|
| worker-ai whole-book rebuild (runner.py:1126) | `list_chapters(book_id, kg_indexed=True)`; **`ChapterInfo.revision_id` ← `kg_indexed_revision_id`** (not `published_revision_id`, runner.py:1118) |
| L3 passage backfill / ingester (passage_backfill.py:48; passage_ingester.py:574) | same filter |
| Cost estimate (book_client.py:81-84) | same filter — so the preview matches what the rebuild extracts |

**Why this is a P0:** without it, a user indexes 50 draft entries, then hits "Rebuild knowledge graph" — the
rebuild enumerates **zero** of them, reports success having extracted nothing, and the cost estimate says
"0 chapters". **The user's explicit act is silently undone by an unrelated button** (the repo's own
`silent-success-is-a-bug` class).

### 3.6 The composition-service mirror (P0-3)

`arc_conformance_orchestrate.py:337-345` hand-copies the sweeper's WHERE clause in Python to compute an
`index_stale` badge. Left alone, this produces a **permanently-stuck badge**: publish at rev A → index a draft
at rev B → composition sees `editorial_status='published' AND last_parsed(B) != published_revision_id(A)` →
*stale*; the sweeper sees `last_parsed(B) == kg_indexed(B)` → *not stale* → **never heals**. The arc's
conformance report stays dirty forever, and worse, the (LLM-judged, token-costly) conformance job now
evaluates **draft** prose while reporting against the published revision id.

Fixes:
1. Add `kg_indexed_revision_id` + `kg_exclude` to the **canon-markers contract**
   (`postInternalChapterCanonMarkers`, server.go:3429-3457) and to composition's `book_client.py:170-180` —
   **composition physically cannot compute the new predicate today.**
2. Re-key composition's `index_stale` to `kg_indexed_revision_id IS NOT NULL AND kg_exclude=false AND
   last_parsed != kg_indexed`.
3. Decide whether `prose_drift` also keys off the KG pointer (recommend: yes).

### 3.7 knowledge-service

- Register **`chapter.kg_indexed`** → `handle_chapter_kg_indexed`, mirroring `handle_chapter_published`
  (resolve project from `book_id`; enqueue via the existing `upsert_chapter_pending`). **No new table.**
- **Do NOT register `chapter.saved`** (§2.4).
- **Passages (P1-8):** `handle_chapter_published` does **two** writes — the graph enqueue *and*
  `_ingest_published_passages(..., canon=True)` (handlers.py:139-147). The new handler must **not** blindly
  mirror it: draft prose must not become `canon=True` passages (raw_search.py:212-215 documents a deliberate
  draft/canon split). **Rule: `canon = (revision_id == published_revision_id)`.**
- **`kg_exclude` is PRODUCER-side authoritative (P1-6).** knowledge-service cannot see it (it's a book-service
  column, not in the payload). So: **book-service simply does not set the pointer and does not emit the event
  when `kg_exclude=true`** — and exposes `kg_exclude` on `/internal/.../chapters` + canon-markers so every
  enumerator filters it. (v1's "handler skips when kg_exclude is set" was **unimplementable**.)

### 3.8 Retraction semantics (P1-7, P1-9) — the symmetry v1 omitted

- **Setting `kg_exclude=true` after indexing must retract.** Otherwise the toggle is a lie: facts extracted
  from a chapter the user later marks "keep out of my KG" would stay in the graph and the passage index.
  The primitive **already exists** and is wired for exactly this symmetry in `handle_chapter_unpublished`
  (`remove_evidence_for_natural_key`, `delete_passages_for_source` — handlers.py:404-410, 458-475).
  → `kg_exclude=true` clears `kg_indexed_revision_id`, deletes unprocessed `extraction_pending` rows, and
  emits a retraction reusing that path.
- **Unpublish must no longer retract the KG.** Today `handle_chapter_unpublished` retracts facts/passages and
  deletes pending rows *regardless of what enqueued them* — so a user who clicks "Add to knowledge" and then
  unpublishes for editorial reasons **silently loses the index request**, while book-service still says
  "indexed". Under this spec's own thesis ("publish means canonical, nothing more"), **retraction is
  `kg_exclude`'s job, not unpublish's.** This is a behavior change to an existing handler — it is in the
  rollout table and the acceptance list.

---

## 4. Rollout

| Step | Change | Service | Risk |
|---|---|---|---|
| 0 | **`delete_by_chapter` invalidation** (§3.3) — do this FIRST; it also fixes today's publish path | knowledge | Medium |
| 1 | Additive columns + backfill | book | Low (proof §6) |
| 2 | **All six** writers set the pointer + hygiene test | book, **worker-infra** | Medium |
| 3 | Index action (+ scenes parse for drafts) + `chapter.kg_indexed` | book | Medium |
| 4 | Sweeper: full query re-key + concurrent guard | book | Medium |
| 5 | `kg_indexed` filter on `/internal/.../chapters`; re-point rebuild, backfill, ingester, cost estimate | book, knowledge, worker-ai | **High** — silent-success class |
| 6 | canon-markers contract + composition `index_stale` re-key | book, **composition** | **High** — cross-service mirror |
| 7 | knowledge handler + passage `canon` rule + `kg_exclude` retraction + unpublish semantics | knowledge | High |
| 8 | FE "Add to knowledge" + an **indexed-state indicator** (the user must be able to see what's in their KG) | frontend | Low |

## 5. Acceptance (evidence gate)

**Live-smoke (real stack) — each maps to a red-team P0:**
1. Draft a chapter, **never publish**, click "Add to knowledge" → facts appear in the KG. *(the point)*
2. **Autosave does not extract** → zero jobs enqueued (the CM3b/CM3c guarantee holds).
3. **Published flow unchanged** (regression).
4. **Cache scope (P0-4):** index chapter 1 of a 200-chapter book → assert the **other 199 chapters'
   `extraction_leaves` survive**.
5. **Whole-book rebuild (P0-2):** index 5 draft chapters → run the rebuild → assert all 5 are enumerated and
   the cost estimate counts them.
6. **Import (P0-1):** bulk-import a book **after** deploy → assert its chapters are swept and scenes parsed.
7. **Composition badge (P0-3):** publish@A, index draft@B → assert `index_stale` is **false** and the
   conformance manifest is coherent.
8. **`kg_exclude` retraction (P1-7):** index → set `kg_exclude` → assert facts and passages are removed.
9. **Unpublish (P1-9):** index → unpublish → assert the index request **survives**.
10. Re-index an unchanged revision → no LLM spend.

Unit: sweeper predicate (published · draft-indexed · excluded · trashed); empty-prose guard; concurrent
re-index; the six-writer hygiene test.

## 6. The backfill is safe — proof (was asserted in v1, now demonstrated)

The red team checked for a mass re-parse/re-extract storm on first sweep and **found none**:
- The backfill set (`published AND published_revision_id IS NOT NULL`) is **exactly** the old predicate's set.
- The new predicate keeps `lifecycle_state='active'` → trashed chapters get a pointer but stay out of the sweep.
- Chapters with `published_revision_id IS NULL` are excluded by **both**.
- Chapters already stale (e.g. `import.go`'s NULL `last_parsed`) are stale under **both** — they are being
  swept today already.
- `is_bible` chapters (worlds.go:119) are swept today and continue to be.

**Rollback is *survivable*, not *clean*** (v1 overstated it): facts and passages extracted from draft revisions
**remain in Neo4j** and need the §3.8 retraction path to clean up; `scenes`/`last_parsed` may point at draft
revisions, which the old predicate will self-heal back to the published body (emitting one
`scenes_reparsed` per chapter — cheap **once step 0 lands**, expensive before it).

## 7. Open questions

1. **Idle-debounce:** resolved to **OFF** for v2 (was OQ-1). Revisit only after step 0.
2. **`prose_drift`** in composition — also re-key to the KG pointer? (recommend yes)
3. **MCP tool tier** — indexing causes downstream LLM spend. Existing worker-ai `try_spend` guardrail +
   a spend estimate in the tool result, or a propose→confirm gate? (recommend the former)
4. **`scenes` semantics** — after this change `scenes` no longer implies "published". Audit its readers
   (composition conformance, `pass2_orchestrator`, `hierarchy_writer`) and say so in the code comments.
5. **Canon search divergence** — book-service lexical "canon search" (search.go:113) stays published-only, so
   "canon search" and "the KG" now legitimately diverge. Acceptable? (recommend yes; document it)

## 8. Review record (v1 → v2)

Red-team verdict on v1: **"DO NOT BUILD AS WRITTEN."** All findings code-verified.

| # | Finding | Fix |
|---|---|---|
| P0-1 | Spec updated **1 of 6** `published_revision_id` writers; **worker-infra** absent from the blast radius; new imports would be invisible to the sweeper forever | §2.1, §3.2, hygiene test |
| P0-2 | worker-ai rebuild, passage backfill, and cost estimate are **independently** publish-gated → a rebuild silently ignores everything the user indexed | §3.5 (`kg_indexed` filter) |
| P0-3 | composition-service **duplicates the sweeper's WHERE in Python** → permanently-stuck `index_stale`; canon-markers contract can't even express the new predicate | §3.6 |
| P0-4 | Every index click → `scenes_reparsed` → **`delete_by_book`** → wipes the whole book's extraction cache. v1's churn-control claim was self-contradictory | §3.3 (chapter-scoped invalidation; debounce removed) |
| P1-5 | Re-keying only the `WHERE` (not SELECT/JOIN) → dropped rows + infinite re-parse loop | §3.4 (full query) |
| P1-6 | `kg_exclude` unreachable from knowledge-service → unimplementable; write-only setting | §3.7 (producer-side authoritative) |
| P1-7 | `kg_exclude` after indexing didn't retract facts — primitive already exists | §3.8 |
| P1-8 | Draft prose would be ingested as `canon=True` passages | §3.7 (`canon = (rev == published_rev)`) |
| P1-9 | Unpublish silently drops an explicit index request | §3.8 (unpublish no longer retracts) |
| P2 | Backfill safety asserted, not proven; rollback overstated; event plumbing verified clean (no new stream/consumer group needed) | §6 |
