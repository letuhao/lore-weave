# AMAW Adversary findings — CM3c, round 1

**Verdict:** BLOCK (2 BLOCK + 1 WARN). Captured rules: read pre-loaded (none — ContextHub unreachable). Guardrails relevant: none reachable.

## BLOCK#1 — manual-rebuild cost estimate diverges from the gated enumeration
`knowledge/app/clients/book_client.py:44` (`count_chapters`) + `book-service server.go:1953-1960` (COUNT) + `worker-ai runner.py:1222`.
The CM3c gate filters `_enumerate_chapters` to published chapters, and `items_total` correctly derives from the gated list — but the pre-job cost-estimate (`count_chapters`) counts ALL active chapters with no editorial filter, so the estimate over-counts when drafts exist. (Adversary's "100× reservation envelope" is overstated — cost is per-item `_try_spend`, not a lump pre-reservation — so it's an estimate-preview imprecision, not a budget bypass. Still: "estimator must mirror real payload.")
**Resolution (FOLDED):** add optional `?editorial_status=published` query param to `getInternalBookChapters` filtering BOTH items and COUNT (default unset = all → backward-compat); worker-ai `list_chapters` + knowledge `count_chapters` pass it for the extraction path. Server-side gate unifies estimate + enumeration.

## BLOCK#2 — published-but-NULL-pointer chapter silently debug-skipped (invisible canon loss)
`worker-ai runner.py:_enumerate_chapters` + design §8.11 + §8.9 adversary-R2-NEW-2.
A `(editorial_status='published', published_revision_id=NULL)` chapter (FK `ON DELETE SET NULL` after revision purge) is collapsed into the same skip bucket as a draft, at debug level → a legitimately-published chapter's facts vanish from canon with no operator-visible signal.
**Resolution (FOLDED):** distinguish at the gate — `published AND revision_id is None` → `logger.warning` + run-log entry ("published chapter has no pinned revision — skipping"), not debug. Re-pin is deferred (operator re-publishes); the point is visibility. With server-side draft filtering (BLOCK#1), a null-pointer arrival now unambiguously means "published but unpinnable."

## WARN#3 — inline passage embed/upsert blocks the event consumer on bulk re-publish
`knowledge/app/events/handlers.py:handle_chapter_published` (passage-ingest moved here).
`ingest_chapter_passages` does a synchronous book fetch + embed batch + N Neo4j upserts inside the consumer; a bulk publish loop (CM-FE "publish all" / migration) serializes embed latency before each ack.
**Resolution (ACCEPT-WITH-NOTE):** this is the SAME cost profile as the pre-CM3c `handle_chapter_saved` (already inline) — not a new regression, just moved to the published event. Moving passage-ingest to the worker-ai drainer is a cross-service data-layer relocation (embedding_client + passages repo are knowledge-side) — out of CM3c scope. Documented residual: bulk-publish passage ingest is intentionally serial-in-consumer for Cycle 0 single-publish cadence; revisit at CM-FE if bulk publish lands.
