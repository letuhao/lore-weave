# Plan — Wiki data-loss bug fixes (glossary-service)

- **Date:** 2026-06-08 · **Branch:** `wiki/llm-building` (first commits, before wiki-LLM feature)
- **Size:** L · **Workflow:** /loom 12-phase · **Scope:** single service (glossary-service, Go)
- **Spec ref:** `docs/specs/2026-06-08-wiki-llm-building.md` §5.5 · merge-spec `docs/specs/2026-06-07-entity-resolution-merge.md` AC4

## Goal
Fix 2 pre-existing data-loss bugs before wiki bodies become valuable products:
- **Bug 1** — merge silently abandons loser's `wiki_article` when both sides have one (violates merge AC4).
- **Bug 2** — kind-delete `ON DELETE CASCADE` silently destroys articles+revisions+suggestions.

## Files touched (~6 src + tests)
1. `internal/migrate/migrate.go` — schema: `superseded_by_entity_id` col + index; FK swap CASCADE→RESTRICT (DO-block + inline `wikiSQL`); `merge_journal.superseded_wiki_article_id`.
2. `internal/api/merge_handler.go` — `mergeOne` repoint-else-archive + journal; `revertMergeCore` un-archive.
3. `internal/api/wiki_handler.go` — `getWikiArticle`/`loadWikiArticleDetail` redirect on superseded.
4. `internal/api/kinds_crud.go` — `deleteKind` explicit article delete + count in 200 response.
5. `internal/api/outbox.go` — `wiki.deleted` event emit helper.
6. `internal/api/*_test.go` — DB-integration tests (merge, un-merge, kind-delete).

## Ordered steps (TDD)
1. **Migration** — add column + index; FK robust swap (DO-block drops any FK on `wiki_articles.entity_id`, ADD `... ON DELETE RESTRICT`; idempotent on re-run); update inline `wikiSQL` CASCADE→RESTRICT for fresh DBs; add `merge_journal.superseded_wiki_article_id`.
2. **Failing tests first** (TDD red):
   - `merge` both-have-article → loser article gets `superseded_by_entity_id=winner`, NOT orphaned; winner article untouched.
   - `getWikiArticle` on a superseded article → resolves to winner's article (AC1.2).
   - `revertMerge` → `superseded_by_entity_id` cleared, loser live again (AC1.3 round-trip).
   - `merge` only-loser-has-article → still repoints to winner (AC1.4 unchanged).
   - `deleteKind` with soft-deleted entity that has an article → article explicitly deleted, count surfaced, `wiki.deleted` emitted, NO silent cascade; FK RESTRICT verified.
3. **Bug 1 mergeOne** — try repoint (existing `NOT EXISTS`); if 0 rows, archive `UPDATE … SET superseded_by_entity_id=winner WHERE entity_id=loser AND superseded_by_entity_id IS NULL RETURNING article_id`; journal both `repointed_wiki_article_id` + `superseded_wiki_article_id`.
4. **Bug 1 revertMergeCore** — if `superseded_wiki_article_id` present → `SET superseded_by_entity_id=NULL`. Keep existing repoint-back.
5. **Bug 1 redirect** — superseded article fetch returns winner's article (200 + `redirected_from`).
6. **Bug 2 kinds_crud** — before purge: gather + `DELETE wiki_articles WHERE entity_id IN (soft-deleted of kind)` (revisions/suggestions cascade off article_id — intended), emit `wiki.deleted`/article, return `200 {deleted_wiki_articles:N}` (was 204).
7. **Bug 2 event** — `outbox.go` `wiki.deleted` (payload `{book_id,article_id,entity_id,reason}`); also emit in `deleteWikiArticle`.
8. **Green** — `go test ./...` in glossary-service.

## Confirm-at-BUILD
- Exact `wiki_articles_entity_id_fkey` name (use DO-block to be name-agnostic).
- `outbox.go` `insertEntityOutboxEvent` shape to mirror for `wiki.deleted` (aggregate_type, payload struct).
- `deleteKind` response 204→200 — verify FE tolerates (QC).
- `merge_journal` INSERT/SELECT column lists in merge_handler.go (add the new column to both).

## VERIFY (evidence gate)
Single service (glossary-service only; `wiki.deleted` emitted, no consumer this task) → **no cross-service live-smoke needed**. Evidence = `go test` output for glossary-service api + migrate packages, green, with the new DB-integration tests named.

## Risks
- `merge_handler.go` is hardened (journal/TOCTOU/chain-guard) — additive changes only; keep the tx + journal symmetry.
- FK swap on existing prod data: if a current row would violate RESTRICT it won't (RESTRICT only blocks future deletes). Migration is safe.
- Response shape change on deleteKind — minor; QC checks FE.
