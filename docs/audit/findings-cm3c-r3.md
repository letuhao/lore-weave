# AMAW Adversary findings — CM3c, round 3 (FINAL design round)

**Verdict:** APPROVED_WITH_WARNINGS (0 BLOCK + 3 WARN). Pragmatic stop after round 3 (L calibration). Captured rules: read pre-loaded (none — ContextHub unreachable).

**R2 folds verified sound:** is_last scope-guard precisely excludes the drain path (only chapters/all populate pre_chapters with a tail; cursor-resume strips from front → manual tail stays book tail); positional-arg wiring keeps COUNT/LIST in lockstep via the shared countArgs slice.

## WARN#1 (FOLDED) — published revision-fetch None → silent delete-stale wipes passages (L3↔graph drift)
`passage_ingester.py:214-228`. The conditional fetch (revision_id set → `get_chapter_revision_text`) feeds the existing delete-stale-on-None branch. A published chapter whose revision-text endpoint returns None on a TRANSIENT error → passages wiped while the graph half retains canon = L3/graph drift.
**Resolution:** add `delete_stale_on_missing: bool = True`; the published-revision caller passes `False`. On the published path, None-from-fetch → `logger.warning` ("pinned revision text unavailable — keeping existing passages") + return WITHOUT deleting. (Draft/legacy `get_chapter_text` path keeps delete-stale.) Transient fetch failure must not nuke canon passages.

## WARN#2 (FOLDED) — unpublish passage-delete: incomplete signature + swallowed if graph-retract raises
`handlers.py:348-365`. Design shorthand omitted `session`+`user_id`; placing the passage delete AFTER `remove_evidence_for_source` in the SAME try means a transient graph-retract raise skips the passage delete → published-era passages linger after unpublish (the drift this fold closes).
**Resolution:** full signature `delete_passages_for_source(session, user_id=str(user_id), source_type='chapter', source_id=str(chapter_id))`; run it as an INDEPENDENT best-effort step in the neo4j session (own try OR sequenced first) so a graph-retract failure doesn't suppress it. Symmetric with `handle_chapter_deleted`'s passage cleanup.

## WARN#3 (FOLDED into test plan) — estimate↔enumerate parity untested; book-service Go list endpoint un-DB-tested
Two independent call sites (`extraction.py` estimate passes `editorial_status='published'`; `_enumerate_chapters` passes the same) must stay in sync — nothing asserts parity → a future one-sided edit re-opens R1-BLOCK#1 silently.
**Resolution:** (a) add a regression-lock asserting both the estimate (`count_chapters(editorial_status='published')`) and the all-scope enumeration gate on published; (b) the live-smoke "book with 1 draft + 1 published → extracts ONLY published, from the pinned revision" is the ONLY coverage for the Go list-filter wiring → run it as a REQUIRED VERIFY gate if infra is bootable, else explicit `LIVE-SMOKE deferred to D-CANON-CYCLE0-LIVE-SMOKE` with the Go endpoint string/build-tested.
