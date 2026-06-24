# E0-4b — campaign-service grant adoption · DESIGN + PLAN

> **Date:** 2026-06-18. **Phase:** PLAN (loom, **L**, no AMAW per PO). Slice of E0 — see
> [`e0-collaboration-plan`](2026-06-11-e0-collaboration-plan.md),
> [`e0-4-…-design`](2026-06-11-e0-4-translation-campaign-composition-design.md) §E0-4b.
> **PO CLARIFY (2026-06-18):** read scoping = **shared per-book view**; full caller-pays
> (locked 2026-06-11). **De-risking finding:** the knowledge-service side is **already
> built** — `internal_dispatch.py` accepts `billing_user_id`/`billing_embedding_model` with
> the full dual-identity caller-pays branch + dimension guard. **This slice is
> campaign-service-only.**

## Current owner-only model (3 gates, all to be replaced/adapted)
1. **Book ownership** — `_owner_verified_chapters` (create + estimate): `get_owner_user_id` → `owner != user_id → 403`.
2. **Campaign-row scoping** — every read/mutate route: `repo.get_campaign(db, id, uid)` (WHERE owner_user_id) → 404. Also `list_campaigns`, `get_report_row`, `update_campaign_fields`, `reset_failed_stages`.
3. **Knowledge-project ownership** — `verify_project_owner(user_id=caller, …)` at create.

## Target model (E0-4a pattern: caller-attributed writes + drop-owner reads + grant chokepoint)
**Dual identity:** `campaigns.owner_user_id = caller` (creator, billed). **book owner** = knowledge-graph partition + project owner. Persist the book owner so the saga can dispatch under it.

### need-mapping (D-E0-4-D)
| Route | need |
|---|---|
| GET `/{id}`, `/{id}/chapters`, `/{id}/activity`, `/{id}/progress`, `/{id}/report`; GET `""` (when `?book_id=`); POST `/estimate` | **view** |
| POST `/{id}/pause` | **edit** |
| POST `""` (create), `/{id}/start`, `/{id}/cancel`, `/{id}/rerun-failed`, PATCH `/{id}` (models + budget) | **manage** |

### Migration (`migrate.py`) — additive, nullable
- `campaigns.book_owner_user_id UUID` — graph/project partition for the saga's knowledge dispatch. Backfill existing rows = `owner_user_id` (pre-E0 campaigns: creator == owner).
- `campaigns.embedding_model_ref UUID` — the **caller's** same-model embedding ref, for `billing_embedding_model` on the collaborator knowledge dispatch (today applied to the project then discarded; now also persisted).

### grant gate (`app/grant_deps.py` — new, mirrors translation E0-4a)
- `get_grant_client_dep`, `authorize_book(gc, book_id, caller, need) -> caller` (404 none / 403 under-tier), `GrantLevel` re-export.
- `app/grant_client.py` — thin singleton shim → `loreweave_grants` (copy translation's), wired to `book_service_internal_url` + `internal_service_token`. lifespan init/close in `main.py`.
- Per-campaign routes bootstrap book from the row: router-local `_grant_campaign(db, gc, campaign_id, caller, need) -> row` = fetch-by-id (no owner) → 404 → `authorize_book` → return row.

### Router changes (`routers/campaigns.py`)
- `_owner_verified_chapters` → `_grant_verified_chapters(gc, book_id, caller, need)`: `authorize_book` (gate) **+** `get_owner_user_id` (book owner for partition) **+** `list_published_chapters`. Returns `(chapters, book_owner)`.
- **create:** gate `manage`; `verify_project_owner(user_id=book_owner, …)` (project is owner-owned); persist `book_owner_user_id` + `embedding_model_ref`. **`set_campaign_models` only when `caller == book_owner`** (a collaborator must NOT mutate the owner's project embedding — would trigger a destructive graph swap on a same-model ref-string mismatch). Collaborator create with no `embedding_model_ref` → 400 (`CAMPAIGN_NO_BILLING_EMBEDDING`) since the knowledge dispatch will require it.
- **estimate:** gate `view`.
- **reads** (`get`/chapters/activity/progress/report): `_grant_campaign(view)`; repo calls drop the owner predicate.
- **list:** add `book_id: UUID | None` query. `book_id` → `authorize_book(view)` + `list_campaigns(book_id=…)` (shared per-book). Absent → owner-scoped "my campaigns" (unchanged; cross-book dashboard — a full cross-book shared view needs a book-service reverse-grant endpoint → **D-E0-4B-LIST-CROSSBOOK-SHARED** deferred).
- **mutations** (start/cancel/pause/rerun/patch): `_grant_campaign(tier)`; repo mutators drop the owner predicate.

### Repo changes (`repositories.py`) — drop owner predicate (grant gate is the chokepoint; campaign_id PK + book scope keep it IDOR-safe)
- `get_campaign(pool, campaign_id)` — drop `owner_user_id`. Add `book_owner_user_id`, `embedding_model_ref` to `_CAMPAIGN_COLS`.
- `list_campaigns(pool, *, owner_user_id=None, book_id=None)` — book_id branch (WHERE book_id) for shared view; owner branch unchanged.
- `get_report_row(pool, campaign_id)`, `update_campaign_fields(pool, campaign_id, fields)`, `reset_failed_stages(pool, campaign_id, ids)` — drop owner.
- `create_campaign(…, book_owner_user_id, embedding_model_ref)` — persist the two new cols.
- **Consumer correlation `(book_id, owner_user_id, chapter_id)` UNCHANGED** — events carry the caller's `user_id` = `campaigns.owner_user_id`; caller-attributed, still correct.

### Dispatch (`saga/driver.py` + `clients/dispatch_clients.py`) — dual identity
- `KnowledgeDispatchClient.dispatch_extraction` gains `billing_user_id`, `billing_embedding_model` (forwarded to the knowledge endpoint that already accepts them).
- `process_campaign` knowledge dispatch: `user_id = book_owner_user_id` (graph); if `owner_user_id != book_owner_user_id` → `billing_user_id = owner_user_id` (caller) + `billing_embedding_model = embedding_model_ref`. Owner-self → both None (legacy owner-paid). Translation dispatch: `user_id = owner_user_id` (caller) — **unchanged** (already caller-attributed/paid).
- `_propagate_cancel`: knowledge cancel uses `book_owner_user_id`; translation cancel uses `owner_user_id`.
- `reconcile.py`: knowledge status/cancel calls keyed by book owner; translation by caller (audit the file's `user_id` uses).

## Test plan
- **grant_client/grant_deps unit** (mirror translation): none→404, under-tier→403, ≥tier→pass.
- **router deny** (the executable guard owner-run tests miss): view-grantee 403s on create/start/cancel/pause/patch/rerun; non-grantee 404s on every read; edit-grantee sees the owner's campaign (shared view); pause=edit passes for edit-grantee but start=manage 403s.
- **conftest autouse shim**: stub `get_grant_client` → owner-level grant so existing owner-run router tests pass through.
- **dispatch unit**: collaborator campaign (owner≠book_owner) → knowledge dispatch body has `user_id=book_owner`, `billing_user_id=caller`, `billing_embedding_model=ref`; owner-self → both None.
- **real-PG**: create persists book_owner+embedding_ref; drop-owner reads return the row for a grantee.
- **Live-smoke (≥3 svc → `D-E0-4B-LIVE-SMOKE`):** manage-collaborator B creates+starts a campaign on A's book → knowledge job `user_id=A` + `billing_user_id=B`; translation `owner_user_id=B`; usage billed to B; view-grantee C create→403; non-grantee→404. Token: `live smoke: campaign grant-gated dual-identity across book+knowledge+translation`.

## Risks
- **R-IDOR**: drop-owner reads keep campaign_id PK + book-grant gate as the single chokepoint + router deny tests.
- **R-billing-leak**: collaborator's knowledge stage must bill the caller, not the book owner — verified in dispatch unit + live-smoke.
- **R-project-corruption**: a collaborator must NOT run `set_campaign_models` on the owner's project (graph-destructive on same-model ref mismatch) — guarded by `caller == book_owner`.
- **R-consumer-correlation**: caller-attributed events still correlate (owner_user_id = caller); knowledge graph writes under book owner — confirm the `campaign_id` tag is the anchor.
