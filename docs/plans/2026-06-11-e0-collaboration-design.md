# E0 — Collaboration-permissions epic · DESIGN

> **Date:** 2026-06-11. **Phase:** DESIGN (loom, XL, AMAW). **Input:** [`2026-06-11-e0-collaboration-clarify.md`](2026-06-11-e0-collaboration-clarify.md) (locked decisions D-E0-A..E). **Goal:** platform-wide collaborative permissions (owner can grant view/edit/manage on a book; every per-book operation honors the grant), via a **per-request cached grant check** (D-E0-C = B), home = **book-service** (D-E0-A), **big-bang** across 8 services (D-E0-E).

---

## 1. Grant model

**Levels (ordered):** `none(0) < view(1) < edit(2) < manage(3) < owner(4)`.
- **owner** — implicit, derived from `books.owner_user_id` (never a stored grant row). Full control incl. book-level destructive (delete/trash/transfer) + grant management.
- **manage** — content-destructive within the book (delete/merge/reassign/purge entities, etc.) but **NOT** book deletion/transfer and **NOT** grant management (D-E0-D).
- **edit** — create/edit content (entities, attributes, translations, chapters, …).
- **view** — read book-scoped data.

**`need` mapping (the rule every call-site applies):** read → `view`; create/edit → `edit`; content-destructive → `manage`. **Book-level destructive (delete/trash/purge the book, change visibility, transfer ownership) and grant mutation stay `owner`-only** — manage does not reach them.

**Resolution:** `resolveGrant(user, book) = owner if book.owner_user_id == user, else book_collaborators[(book,user)].role or none`. A check passes iff `resolveGrant(user,book) >= need`.

---

## 2. Data model (book-service DB)

```sql
CREATE TABLE book_collaborators (
  book_id     UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  user_id     UUID NOT NULL,                         -- the collaborator
  role        TEXT NOT NULL CHECK (role IN ('view','edit','manage')),
  granted_by  UUID NOT NULL,                          -- the owner who granted (audit)
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (book_id, user_id)                       -- one role per (book,user)
);
CREATE INDEX idx_book_collab_user ON book_collaborators(user_id);  -- "books shared with me"
-- (book_id is the PK prefix → "collaborators of a book" is already indexed)
```
- `owner` is never stored here (implicit via `books.owner_user_id`). The table holds only non-owner grants → AC6 (single-owner no-regress) is free: empty table = today's behavior.
- `ON DELETE CASCADE` on `book_id`: deleting a book cleans up its grants.
- No FK on `user_id` (users live in auth-service; cross-service FK avoided — consistent with the rest of the platform).

---

## 3. book-service — the single authority

### 3a. Internal resolve endpoint (the chokepoint every service calls)
```
GET /internal/books/{id}/access?user_id={uid}     (X-Internal-Token)
→ 200 { "grant_level": "owner"|"manage"|"edit"|"view"|"none" }
→ 404 only if the book itself does not exist (callers collapse none→deny uniformly, INV-8/H13)
```
- Resolves locally (book-service owns both `books` and `book_collaborators`): one SQL `SELECT owner_user_id … ; SELECT role …` (or a single LEFT JOIN). Fail-closed on DB error (502 → callers deny).
- **Does NOT replace `/internal/books/{id}/projection`** (still returns owner_user_id + wiki settings for other uses); `/access` is the new grant-resolution path.

### 3b. Owner-facing grant management (JWT, owner-only — D-E0-D)
```
GET    /v1/books/{id}/collaborators                 → [{user_id, role, granted_by, created_at}]   (owner only)
PUT    /v1/books/{id}/collaborators/{user_id}  {role}  → grant/update (owner only)
DELETE /v1/books/{id}/collaborators/{user_id}          → revoke (owner only)
```
- Owner-only: handler checks `caller == books.owner_user_id`; else 403. Cannot grant to the owner or to self; `role` validated against the enum; target `user_id` SHOULD be a real user — resolve via an auth-service lookup (see §6 invite-by-email) or accept a raw user_id for v1 + validate-exists best-effort.
- On every mutation: write the row, **emit an audit event** to the outbox (`book.collaborator_granted` / `book.collaborator_revoked` with `{book_id, user_id, role, granted_by, ts}`), and **push a Redis invalidate-key** `grant:inval:{user_id}:{book_id}` (TTL ~120s) so per-service caches drop the entry → near-instant revoke/upgrade (otherwise ≤60s via TTL).

---

## 4. Shared per-service grant-check helper (the mechanical core of the big-bang)

One helper per language; identical semantics. Wraps the book-service `/access` call + a **(user,book)→level cache** (60s positive TTL, fail-closed — mirrors glossary's existing `ownerCache` at `glossary-service/internal/api/ownership.go`), + optional Redis-invalidate subscription.

**Go** (`book-service`, `glossary-service`, `sharing-service`, `catalog-service`) — package `grantclient`:
```go
type Level int // None=0 View=1 Edit=2 Manage=3 Owner=4
func (c *Client) Resolve(ctx, bookID, userID uuid.UUID) (Level, error)   // cached; fail-closed
func (c *Client) Require(ctx, w, bookID, userID uuid.UUID, need Level) bool // writes 403/404/503, returns ok
```
**Python** (`knowledge`, `translation`, `campaign`, `composition`) — `grant_client.py`:
```python
async def resolve_grant(book_id, user_id) -> Level   # cached; fail-closed
async def require_grant(book_id, user_id, need) -> None  # raises 403/404/503
```
- **book-service itself does NOT self-RPC** — its helper resolves against its own tables directly (SQL).
- Uniform error (INV-8/H13): `none`/not-found both surface as the same "not accessible" to prevent enumeration. `503` only on book-service unavailable (fail-closed).

---

## 5. Big-bang adoption — per service

| Service | Today | Change | `need` mapping notes | Risk |
|---|---|---|---|---|
| **glossary** | `verifyBookOwner` / `checkBookOwnership` (57 sites) | Re-implement both over `grantclient`; signatures unchanged so the 57 call-sites barely move. `ownerCache`→grant cache. MCP tools (X-User-Id) resolve the same way. | reads→view; create/edit/apply-edit/translations→edit; delete/merge/reassign/recycle-purge/schema-confirm-destructive→manage | **Highest volume.** Mis-mapping a destructive op to `edit` is the main hazard → AMAW + a per-site mapping table reviewed. |
| **book-service** | ~35 SQL `WHERE owner_user_id=$1` | Reads (GET book/list): widen to owner OR collaborator (grant≥view). PATCH content→edit. **Book delete/trash/purge/transfer + visibility stay owner-only.** | careful: "list my books" must include shared-with-me (query `books WHERE owner=$1 UNION book_collaborators`) | book-level destructive must NOT open to manage. |
| **knowledge** | repo-layer `WHERE user_id=$1` (project owner) | Project→`book_id`→grant. Access layer above the repo resolves grant on the project's book; repo widens from single user_id to "accessible". | project read/extract→view/edit per op | **Trickiest** — repo assumes 1 user_id; IDOR risk if widened sloppily. AMAW focus. |
| **translation** | `_verify_book_owner` | → `require_grant(book_id, user, need)` | job create/dispatch→edit; read→view | low |
| **campaign** | `_owner_verified_chapters` (+ knowledge project owner) | grant on book (≥edit to run a campaign) + grant on the knowledge project | running a campaign mutates → edit | medium (two-resource check) |
| **composition** | `owns_book` (book-service public 404 probe) | → `resolve_grant ≥ edit` (or view for read prose) | prose write→edit | low |
| **sharing** | owner-only visibility writes | **No change** — visibility (make public/unlisted) stays **owner-only** (publishing decision). | — | none |
| **catalog** | read-only public aggregate | **No change** — public catalog is grant-independent. | — | none |
| **api-gateway-bff** | transparent proxy | **No change** — forwards JWT/X-User-Id as today. | — | none |

**Rollout order (single epic, deploy order matters):** book-service (table + `/access` + grant endpoints) **first**; then the 6 consuming services adopt the helper; FE collaborators panel last. Each consumer fail-closes if book-service `/access` is unreachable.

---

## 6. Owner UI (AC5) — collaborators panel (sub-slice E0-FE)
- A "Share / Collaborators" panel on the book surface: list collaborators + role; add by **email** → resolve to `user_id`; change role; remove.
- **Invite-by-email** needs an auth-service lookup: `GET /internal/users/by-email?email=` → `{user_id}` (auth-service has user records + `user_follows`, so user lookup exists or is a thin add). If we defer email-invite, v1 can accept a raw `user_id` (less friendly). **Decision for PLAN:** ship email-invite (needs the auth lookup endpoint) vs raw-user_id-v1.

---

## 7. Audit & security (AC-SEC)
- Grant/revoke → audit event in the outbox; `granted_by` stored on the row.
- Only the owner mutates grants (book-service enforces). Forging a grant requires DB write or `JWT_SECRET` compromise (= full compromise).
- Fail-closed everywhere; positive-only cache so a book-service outage never grants stale access; revoke ≤60s (or instant via Redis invalidate-key).
- Uniform not-accessible error preserved (no enumeration oracle).

---

## 8. Migration & compatibility
- One additive migration (the table) in book-service. **No backfill** — owner stays implicit via `owner_user_id`; `book_collaborators` empty = exactly today's behavior (AC6).
- Backward-compatible during rollout: until a consumer adopts the helper, it still does owner-only checks (stricter, never wrong — just no collaboration yet). Big-bang = all adopt in one epic, but partial-deploy is safe (degrades to owner-only).

---

## 9. Verify / test plan
- **Unit (each service):** grant resolution (owner implicit, each role, none); cache hit/miss + 60s expiry + fail-closed; the `need`-mapping per call-site (esp. glossary's destructive→manage table); uniform-error preserved.
- **Real-PG (book-service):** grant store + `/access` resolution + grant/revoke endpoints (owner-only 403s; cannot grant self/owner; cascade on book delete) + audit event emitted.
- **Live-smoke (≥2 services — REQUIRED, the cross-service contract mocks hide):** owner grants user-B `edit` on a book → B edits a glossary entity through the real chain (deny before grant, allow after) → owner revokes → B denied within 60s (or instantly via invalidate-key). Token: `live smoke: grant→edit-allowed→revoke→denied across book+glossary`.
- **IDOR probes:** non-grantee denied on every service; knowledge cross-project access blocked.

---

## 10. AMAW / REVIEW focus areas (for the upcoming adversary review)
1. **`need`-mapping correctness** — every destructive op maps to `manage` (a single op mis-mapped to `edit` lets an editor delete). The glossary 57-site table is the prime target.
2. **knowledge repo-layer widening** — IDOR if "accessible projects" is computed loosely; verify per-project book-grant resolution.
3. **book-level destructive stays owner-only** — delete/trash/transfer/visibility must NOT open to `manage`.
4. **fail-closed + positive-only cache** — outage never grants; revoke latency bounded.
5. **uniform error (INV-8/H13)** — no existence enumeration via grant checks.
6. **grant mutation auth** — only owner; cannot self-escalate; audit complete.

---

## REVIEW (design) — Lead self-review findings (2026-06-11, default v2.2, no AMAW per PO)
Spec-compliance: D-E0-A..E + AC1–AC6 + AC-SEC all represented. 5 refinements folded in:
- **R1 — knowledge project↔book mapping (must-verify).** Grant resolution for knowledge assumes every `knowledge_projects` row has a `book_id`. **PLAN/BUILD must verify this invariant**; if a project can exist without a book, knowledge falls back to **project-owner-only** for those (no collaboration on book-less projects). Trickiest service — IDOR risk if widened loosely.
- **R2 — book-service list endpoints = UNION.** "List my books" must return owned **+** collaborated (`books WHERE owner=$1 UNION SELECT … FROM book_collaborators WHERE user_id=$1`), with pagination over the union. book-service resolves **locally** (owns both tables) → **no N+1** /access calls.
- **R3 — split the ~35 book-service sites.** Single-book handlers (GET/PATCH/DELETE `/{id}`) → **pre-check grant** then query by id. List handlers → **union query** (R2). Not one mechanism for all 35.
- **R4 — /access returns `none`, never 404 (hardening).** Even at the internal authority, distinguishing "book missing" (404) from "exists, no grant" (none) is a faint existence oracle. **`/access` always returns 200 `{grant_level}` with `none` for missing/forbidden alike** — zero existence signal; callers still collapse to a uniform external deny (INV-8/H13).
- **R5 — downgrade latency.** A role downgrade (manage→edit) leaves the higher level cached for ≤60s (same window as revoke). Acceptable per AC4; the Redis invalidate-key closes it instantly when enabled. Documented.

All 5 are folded into the sections above (data model / endpoints / adoption table / test plan). No HIGH design defects; proceed to PLAN.

## Open items for PLAN
- Email-invite (auth `/internal/users/by-email`) vs raw-user_id v1 (§6).
- Redis invalidate-key now, or rely on 60s TTL for v1 (instant-revoke is a nice-to-have; 60s meets AC4).
- Deploy/rollout sequencing of the 8 services in one release.
