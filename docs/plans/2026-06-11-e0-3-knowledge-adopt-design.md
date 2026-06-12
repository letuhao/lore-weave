# E0-3 — knowledge-service adopt · DESIGN

> **Date:** 2026-06-11. **Phase:** DESIGN (loom, **XL**, no AMAW). Slice of the E0 epic — see [`-design`](2026-06-11-e0-collaboration-design.md) (R1, knowledge IDOR-heavy) + [`-plan`](2026-06-11-e0-collaboration-plan.md). **Goal:** a collaborator on a book can access that book's knowledge project per their grant, without widening the repo layer (IDOR-safe). **First Python adopter** → also builds the shared Python `grant_client`.

## 1. Findings that shape the design (from the ownership map)
- Authz today = **repo `WHERE user_id=$1`** (project owner) on every method; no book-grant resolution exists.
- `knowledge_projects.book_id` is **nullable** (no FK) — **book-less projects exist** (R1). For a book-bound project, **`project.user_id == book.owner_user_id`** (project creation is book-owner-only — decision Q4), so the project owner *is* the book owner.
- BookClient fetches content only; never sends user_id / checks ownership.

## 2. Access model — resolve-to-owner (PO decision Q1)
**No repo changes.** An access-layer dependency authorizes the caller and hands the repo the **owner's** user_id, so every existing `WHERE user_id=$1` query runs unchanged as the owner — IDOR-safe by construction (the repo never widens; the grant check is the single gate).

```python
# deps.py — factory; `need` per route
def require_project_grant(need: GrantLevel):
    async def dep(project_id: UUID, caller=Depends(get_current_user),
                  meta=Depends(get_projects_repo), gc=Depends(get_grant_client)) -> UUID:
        owner, book_id = await meta.project_meta(project_id)   # NOT user-scoped; bootstrap only
        if owner is None:                 raise _not_found()   # missing project → 404 (no oracle)
        if caller == owner:               return owner         # owner does everything
        if book_id is None:               raise _not_found()   # book-less → owner-only fallback (R1)
        lvl = await gc.resolve_grant(book_id, caller)          # cached, fail-closed
        if lvl == GrantNone:              raise _not_found()   # non-grantee → 404 (uniform)
        if lvl < need:                    raise _forbidden()   # has access, under tier → 403
        return owner                                            # authorized; repo runs as owner
    return dep
```
- `project_meta(project_id) -> (owner_user_id|None, book_id|None)` — the **only** new repo method; returns just owner+book for the gate, never content (no oracle).
- **Book-scoped** routes (raw-search) use `require_book_grant(need)` reading `book_id` from the path (no project bootstrap).
- **Job-scoped** routes (`/extraction/jobs/{job_id}`, logs) resolve `job_meta(job_id) -> project_id` then reuse the project gate (a collaborator who has grant on the project's book can watch its jobs).
- **owner-only** ops use `require_project_grant(GrantOwner)`: only `caller==owner` yields `GrantOwner` (a non-owner collaborator caps at `manage`), so it's exactly owner-only — and book-less projects are owner-only at every tier via the fallback.

## 3. need-mapping (PO-locked CLARIFY 2026-06-11)

**Own-scoped (unchanged — personal "my stuff", collaboration does NOT extend):** `GET /projects` (list), `GET /extraction/jobs` (list), `GET /me/entities` (+archive), `PATCH /summaries/global`, `GET /costs`, `GET /timeline`, `GET|DELETE /me/data`. Keep `get_current_user`.

**Project-scoped (`/projects/{project_id}/…`) — gate via `require_project_grant`:**
| Route | need |
|---|---|
| GET project · GET drawers · GET events · GET relations(by project) · estimate · graph/stats · benchmark/status | **view** |
| PATCH project · PUT extraction-config · POST extraction/start · POST benchmark/run · PATCH project-summary · summary rollback/regenerate(project scope) | **edit** |
| extraction pause / resume / cancel · disable · entity merge(project) | **manage** |
| **archive · DELETE project · delete-graph · rebuild · change-embedding-model** | **owner-only** |

**Book-scoped:** `GET /books/{book_id}/search` (raw-search) → **view** via `require_book_grant`.

**Create (`POST /projects`)** — decision Q4: if body `book_id` set → caller must be the **book owner** (`require_book_grant(GrantOwner)` on the body value, in-handler since book_id isn't a path param); if `book_id` null → personal project (any caller, owns it).

**Entity/summary duality:** entities/summaries carry a global(user) scope and a project scope. **Global/user-scoped** ops stay own (`/me/entities`, global summary). **Project-scoped** entity/summary ops gate via the project (`entity_meta(entity_id) -> project_id|None`; global entity → own-only). `GET /entities` browse: the project filter (if any) gates via the project; global browse stays own.

## 4. Python `grant_client` (shared SDK — `app/clients/grant_client.py`)
Mirrors the Go `grantclient`: calls book-service `GET /internal/books/{id}/access?user_id=` with `X-Internal-Token`.
- `GrantLevel` IntEnum: `NONE=0 VIEW=1 EDIT=2 MANAGE=3 OWNER=4`; `parse_grant_level(s)` default-deny.
- `resolve_access(book_id, user_id) -> (GrantLevel, lifecycle)`; `resolve_grant(...) -> GrantLevel`; `require_grant(...)` raises.
- **45s positive-only cache** (mirror Go `DefaultCacheTTL`; none/errors never cached); **fail-closed** — any non-200/transport error → `GrantNone` (deny). httpx.AsyncClient + `X-Trace-Id`, graceful like BookClient. Singleton via `get_grant_client()` in `deps.py`/lifespan.

## 5. Anti-oracle / errors
- missing project / non-grantee / book-less-non-owner → **404** (uniform with today's cross-user 404, KSA §6.4 — no existence oracle).
- grantee under tier → **403**.
- book-service unreachable → grant `none` → 404 (fail-closed deny).

## 6. Test plan
- **grant_client unit:** level parse/default-deny; cache positive-hit / none-never-cached / 45s expiry / fail-closed; `require_grant` tiers.
- **Dependency unit:** `require_project_grant` — owner→pass; collaborator≥need→pass(returns owner); none→404; under→403; book-less+non-owner→404; missing project→404. Stub `project_meta` + grant_client (no DB).
- **Router smoke:** a representative project route per tier returns the right code for owner / edit-grantee / view-grantee / non-grantee (FastAPI TestClient + stubbed deps).
- **Live-smoke (≥2 services):** owner grants B `edit` on a book that has a knowledge project → B reads the project + starts extraction through the real chain; B denied on delete-graph (owner-only); non-grantee 404. Token: `live smoke: knowledge project grant-gated across book+knowledge`. → `D-E0-3-LIVE-SMOKE`.

## 6b. BUILD notes / decisions (2026-06-11)
- **Billing consequence of resolve-to-owner:** because everything runs as the owner's user_id (the only consistent model for the user-scoped graph), a **collaborator's extraction bills the owner** — a deliberate divergence from glossary's caller-pays-wiki, justified because extraction writes bulk into a *shared single-user* graph. The owner controls exposure via the grant tier (start=edit) + their budget cap.
- **Scope (shipped in E0-3):** gated the **core collaborative surface** — projects, extraction (all), raw-search, drawers. **Deferred (`D-E0-3-ENTITIES-SUMMARIES`):** entities, summaries, events, relations stay **own-only** (unchanged). This is **fail-safe** — un-gated routes keep the repo's `WHERE user_id` (stricter, no IDOR); a collaborator simply can't reach those secondary surfaces yet. Extend in a follow-up (needs `entity_meta`/`event_meta` bootstraps + global-vs-project scope handling).
- **Test seam:** the gate resolves `(owner, book_id)` via the overridable named deps `project_meta_dep`/`job_meta_dep`; a conftest autouse shim makes them pass-through (`owner=caller`) for existing router tests (the fake repo's own `user_id` filtering still does cross-user denial) and stubs `get_grant_client`. New deny tests (`test_grant_deps.py`) exercise the REAL gate.
- **Pre-existing bug fixed incidentally:** the FD-22 extraction wake was broken since `514f8bb5` (S4a) — `_start_extraction_job_core` referenced `extraction_wake` but neither caller passed it (NameError, swallowed → wake never fired for the public route OR campaign dispatch). Threaded `extraction_wake` through (guarded `if … is not None`). Surfaced because the grant gate let the start tests reach the wake code.

## 7. Risks
- **R-IDOR** (primary): mitigated by resolve-to-owner (repo untouched) + the dependency is the single gate + deny tests.
- **R-book-less**: book-less projects must never resolve a grant → owner-only fallback, tested.
- **R-owner≠projectowner drift**: holds only while create is book-owner-only (Q4). If that ever loosens, `GrantOwner`-means-owner-only breaks — documented invariant.
- **R-bootstrap-oracle**: `project_meta`/`job_meta`/`entity_meta` return only ids for the gate, never content; non-grantee gets uniform 404.
