# AMAW Adversary findings — CM3c CODE review, round 1

**Verdict:** APPROVED_WITH_WARNINGS (0 BLOCK + 3 WARN). Captured rules: read pre-loaded (none — ContextHub unreachable).

**Verified CORRECT as built:** Go placeholder arithmetic in `getInternalBookChapters` (editorial_status value appended to `countArgs` before its `$N` is emitted from post-append `len`; `limitPos/offsetPos` computed after; COUNT/LIST share `countArgs` → collision-free, R2-BLOCK#2 satisfied). Unpublish dual-retract = two independent `try`/`neo4j_session` blocks → graph-retract failure can't suppress passage delete (R3-WARN#2 satisfied).

## WARN#1 (FOLDED) — published filter omitted `published_revision_id IS NOT NULL`
`server.go` `getInternalBookChapters`. The `editorial_status='published'` filter matched published-but-NULL-pointer chapters (FK ON DELETE SET NULL purge edge), which the worker `_enumerate_chapters` then SKIPS → cost-estimate count > extracted count on that edge.
**Resolution:** when `es == "published"`, also append `AND c.published_revision_id IS NOT NULL` to BOTH `where` and `countWhere` (no placeholder — literal predicate, no arg-shift). Estimate count now == worker enumeration exactly; the worker's null-revision WARN-skip becomes pure defense-in-depth.

## WARN#2 (FOLDED) — swallowed COUNT error → silent `total=0` published-gate blackout
`server.go` `getInternalBookChapters`. `_ = pool.QueryRow(...).Scan(&total)` discarded the error; with CM3c making `total` gate canon, a malformed query would return `total=0` HTTP 200 (silent blackout) instead of 500.
**Resolution:** check the COUNT error → `writeError(500, "BOOK_CONFLICT")` + `OutcomeQueryFailed` metric, mirroring the LIST branch.

## WARN#3 (DEFERRED — tracked) — inline passage embed serializes the consumer under bulk publish
`handlers.py` `handle_chapter_published` → `_ingest_published_passages` awaits a synchronous embed batch inline. CM3c dropped the old C12a save-time skip-gate, so EVERY publish now embeds inline; a composition bulk-publish (all `done` scenes → N sequential `chapter.published`) serializes the knowledge event consumer behind N embed round-trips, back-pressuring chat/glossary events. Graph-queue is written FIRST (canon never lost) → WARN not BLOCK.
**Resolution:** tracked as **D-CM3C-PASSAGE-INLINE-BULK** (LOOM SESSION_HANDOFF Deferred). Cycle-0 single-publish cadence makes inline acceptable; revisit at CM-FE (move passage-ingest behind the `extraction_pending` drain, or fire-and-forget the best-effort passage half). NOT folded now to avoid fire-and-forget task-lifecycle complexity in the consumer.

**Pragmatic stop after code-review round 1 (L calibration: APPROVED_WITH_WARNINGS acceptable).** The two folded fixes are 4 lines of SQL + an error-check with NO new placeholders (R2-BLOCK#2 arithmetic untouched) → self-reviewed delta, `go build`/`vet`/`test -count=1` green; no round-2 agent.
