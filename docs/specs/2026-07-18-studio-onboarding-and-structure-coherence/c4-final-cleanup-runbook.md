# C4 final cleanup — the irreversible retire step (RUNBOOK, deploy-gated)

**Status:** `AUTHORED, NOT EXECUTED.` This is the one-way door. It runs **only after C1–C4b have soaked
in production** (read + write cutover live and observed healthy). Executing it earlier — or in dev —
would break the live system and the shared dev DB the parallel sessions use. C4a (composition write
endpoints) + C4b (FE write-flip) are already built + committed; this is what deletes the old system.

## Preconditions (all must hold before running)
1. C1–C4b deployed to production and soaked (the Manuscript rail reads/writes composition; no parts-table
   traffic in logs for the soak window).
2. `POST /internal/parts-mirror/backfill` has run (every book with parts is mirrored; every
   `chapters.part_id` is copied to `chapters.structure_node_id`). Verify:
   ```sql
   SELECT count(*) FROM chapters WHERE part_id IS NOT NULL AND structure_node_id IS NULL;  -- must be 0
   ```
3. A DB backup/snapshot exists (this drops a table — irreversible without it).

## Step 1 — book-service: remove the parts subsystem (a PR)
Delete (they have no callers after C4b):
- `internal/api/parts.go` (routes + store methods + the C2 emit calls + the /internal parts-mirror +
  backfill handlers).
- The parts routes in `internal/api/server.go` (`/v1/books/{book_id}/parts*`, `/chapters/{id}/part`
  stays — it now writes `structure_node_id`; see Step 3), and the two `/internal` parts-mirror routes.
- `internal/api/mcp_tools_parts.go` + its registrations in `internal/api/mcp_server.go` (the 6
  `book_part_*` / `book_chapter_set_part` tools — `book_chapter_set_part` stays, retargeted to
  `structure_node_id`).
- `emitManuscriptPartChanged` + `ManuscriptPartChangedEvent` in `internal/api/outbox.go`; the emit
  call in `parse.go` (import).
- Tests: `parts_db_test.go`, `mcp_tools_parts_db_test.go`; the parts assertions in `migrate_test.go`
  (`TestSchemaContainsPartsTable`, the part_id/index asserts) — and REMOVE the `parts` DDL +
  `chapters.part_id` + `idx_chapters_part` from `schemaSQL` (leave `chapters.structure_node_id` +
  `idx_chapters_structure_node`).

## Step 2 — composition: remove the C2 mirror bridge (a PR)
Delete (nothing emits to it once book-service stops emitting):
- `app/events/parts_mirror_consumer.py` + its wiring in `app/worker/__main__.py`.
- `app/services/parts_mirror_service.py`.
- `BookClient.list_parts_mirror` in `app/clients/book_client.py`.
- The `test_reconcile_*` / mirror tests in `tests/integration/db/test_parts_mirror.py` (KEEP the
  `create_part`/`reorder_parts`/no-pollution tests — those cover the surviving write/read path).

## Step 3 — book-service: retarget chapter→part assignment
`book_chapter_set_part` / `PATCH /chapters/{id}/part` and `moveChapterToPart` already write BOTH
`part_id` and `structure_node_id` (since C2). After Step 4 drops `part_id`, drop the `part_id` write,
keep only `structure_node_id`. `hierarchy.go`'s `LEFT JOIN parts` (KG grouping) → group by
`chapters.structure_node_id`; its group TITLE was `parts.title` — resolve it from composition
(`GET /v1/composition/books/{id}/parts`) at index time, or emit "Part {n}" from the synthetic fallback
(`hierarchy.go:231` already synthesizes a part for undecomposed chapters).

## Step 4 — the destructive migration (gated, one-time)
Runs with the Step-1 PR (which removes `parts` from `schemaSQL`, so this drop is not re-created on the
next boot). Gate it behind an explicit flag so it never fires in dev/CI:

```go
// book-service Up(), AFTER the main schema — GATED, deploy-time only.
if os.Getenv("C_MERGE_C4_DROP_PARTS") == "1" {
    _ = execGuarded(ctx, pool, "c4-drop-parts", c4DropPartsSQL)
}
```
```sql
-- c4DropPartsSQL — idempotent + self-guarding.
-- 1. belt-and-suspenders: finish the link migration (no-op if backfill already ran).
UPDATE chapters SET structure_node_id = part_id WHERE part_id IS NOT NULL AND structure_node_id IS NULL;
-- 2. drop the redundant link (structure_node_id is now the SSOT) + its index + the FK it carried.
DROP INDEX IF EXISTS idx_chapters_part;
ALTER TABLE chapters DROP COLUMN IF EXISTS part_id;
-- 3. drop the retired table.
DROP TABLE IF EXISTS parts CASCADE;
```

## Rollback
Everything through C4b is reversible (flip the FE/gateway reads+writes back to book-service; the parts
table + dual-write are still intact until this runbook runs). This runbook is the point of no return —
hence the backup precondition and the soak gate.

## Why this is a separate step, not built into the C-merge branch now
Deleting the working parts subsystem + dropping the shared `parts` table before the replacement has
soaked in production is exactly the risk the sealed cutover sequence (C1→C2→backfill→C3→**soak**→C4)
exists to prevent — and it would break the shared dev DB the parallel sessions depend on. The code that
*replaces* parts (C4a write endpoints, C4b FE flip, C3 read surface) is built, tested, and committed;
this runbook is the deliberate final deploy-op that retires the old system once the new one is proven.
