# PlanForge auto-bootstrap POC — PLAN (2026-07-06)

Implements the POC scope locked in
[`docs/specs/2026-07-06-planforge-auto-bootstrap.md`](../specs/2026-07-06-planforge-auto-bootstrap.md)
§4 + §4.1: the propose→record→approve→apply gate, end to end, proven via
real chapter-shell creation ([A]). Size: **L** (7 logic units, 2 side
effects — DB migration + cross-service book-service call — single service).

## Files touched (composition-service only — no book-service code changes;
its `createChapter` endpoint already exists and already does what's needed)

1. `app/db/migrate.py` — add `plan_bootstrap_proposal` table to `_SCHEMA_SQL`
   (near the existing `plan_run`/`plan_artifact` block). Columns: `id`,
   `run_id` (FK → plan_run), `book_id`, `owner_user_id`, `status`
   (`pending|approved|rejected|applying|applied|failed`), `diff JSONB`,
   `applied_results JSONB DEFAULT '{}'`, `created_at`, `updated_at`. Index on
   `(book_id, status, created_at DESC)` for the propose-dedup query.
2. `app/db/repositories/plan_bootstrap_proposals.py` (new) — `create`,
   `get`, `list_applied_for_book` (for dedup), `mark_approved`,
   `mark_rejected`, `claim_for_apply` (conditional UPDATE
   `WHERE status='approved'`, returns None if already claimed),
   `mark_item_applied` (append to `applied_results`, one call per
   successfully created chapter — partial-failure visibility），
   `mark_applied`, `mark_failed`.
3. `app/clients/book_client.py` — add `create_chapter(book_id, bearer, *,
   title, original_language) -> dict` (POST JSON body, no `sort_order` —
   §4.1.2 lets book-service auto-append). Bearer-forwarded, same pattern as
   `publish_chapter`/`patch_draft`.
4. `app/services/bootstrap_service.py` (new — kept separate from the
   715-line `plan_forge_service.py`; this is a distinct quarantine-gate
   subsystem per spec §3.1, not a PlanForge pipeline step) —
   `propose(user_id, book_id, run_id, bearer) -> record`: loads the run's
   latest `package` artifact, calls `book_client.list_chapters()` +
   `plan_bootstrap_proposals.list_applied_for_book()`, diffs
   `package.chapters[]` by title against both, persists a `pending` record.
   `approve(user_id, record_id)` / `reject(user_id, record_id)`: status
   transition, 404/409 mapped from ValueError/LookupError.
   `apply(user_id, book_id, record_id, bearer)`: `claim_for_apply` (409 if
   already claimed/applied), then loops `diff.new_chapters`, calls
   `book_client.create_chapter` per entry, `mark_item_applied` per success;
   on exception mid-loop, marks `failed` with per-item status already
   recorded (not a bare rollback) and re-raises for the router to surface.
5. `app/routers/plan_bootstrap.py` (new) —
   `POST /v1/composition/books/{book_id}/plan/runs/{run_id}/bootstrap/propose`
   `POST /v1/composition/books/{book_id}/plan/bootstrap/{record_id}/approve`
   `POST /v1/composition/books/{book_id}/plan/bootstrap/{record_id}/reject`
   `POST /v1/composition/books/{book_id}/plan/bootstrap/{record_id}/apply`
   `GET  /v1/composition/books/{book_id}/plan/bootstrap/{record_id}`
   Same `_gate_book` + `Depends(get_current_user)` pattern as
   `plan_forge.py`; registered in the app's router include list.
6. Tests: `tests/db/test_plan_bootstrap_proposals.py` (repository — claim
   race, status transitions), `tests/services/test_bootstrap_service.py`
   (propose dedup logic with a fake book_client, apply partial-failure,
   apply-twice-is-safe-noop), `tests/routers/test_plan_bootstrap.py`
   (HTTP contract — 404/403/409 mapping).

## Explicitly NOT in this POC (per spec §4's out-of-scope list)

Real glossary POST wiring ([B]), scene/beat drafting context ([C]),
`run_chapter_generate` reachability ([D]), bulk auto-draft, line-by-line
approve/reject, the polished plain-language review UI (a raw JSON response
from `GET .../bootstrap/{record_id}` is acceptable for POC review).

## Verify

Unit suite green (`pytest -n auto --dist loadgroup` per repo convention).
Live smoke: propose → approve → apply against a real dev-stack book with an
existing PlanForge run, confirm the new chapters render in the Studio's
Manuscript Navigator (not just a 200 response) and that calling `apply`
twice on the same record is a safe no-op (second call returns the
already-applied status, doesn't double-create chapters).
