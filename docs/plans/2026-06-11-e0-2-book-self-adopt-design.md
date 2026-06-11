# E0-2 — book-service self-adopt · DESIGN

> **Date:** 2026-06-11. **Phase:** DESIGN (loom, **L**, no AMAW per PO). **Slice** of the E0 collaboration epic — see [`-design`](2026-06-11-e0-collaboration-design.md) (R2/R3) + [`-plan`](2026-06-11-e0-collaboration-plan.md) (slice E0-2). **Goal:** book-service honors grants on its **own** per-book endpoints — reads/edits grant-gated; "my books" returns owned **+** collaborated; **book-level destructive + collaborator-mgmt stay owner-only**.

## 1. Scope — the owner-gated surface only

E0-2 adopts the **~35 handlers currently filtered by `owner_user_id`** (server.go book/chapter/content/draft/revision handlers + media.go + audio.go + import.go + parse.go + search.go + the deprecated getBookStats). book-service resolves grants **locally** (it owns `books` + `book_collaborators`; no self-RPC — DESIGN §4) reusing the E0-0 `resolveAccess`/`resolveBookAuth`.

**Explicitly OUT of scope (unchanged):**
- **Personal/reader routes** — favorites (add/remove/check/list), reading-progress (upsert/list), reading-history, recordBookView. These key by `user_id` with **no owner filter** (a user may favorite/read a *public* book they don't own); gating them on grants would break public-reader/catalog behavior.
- **getStorageUsage** — the caller's *own* quota aggregate (`owner_user_id = caller`); personal, not book-scoped authz.
- **Owner-only set (stays owner-only via the existing `ensureOwnerBook` / `requireBookOwner`):** book trash/restore/purge (whole-book `transitionBookLifecycle`), `listTrashedBooks`, collaborator mgmt (E0-0), visibility (owned by sharing-service, RPC-fetched — no change). **R-book-destructive guard.**

## 2. need-mapping table (PO-locked, CLARIFY 2026-06-11)

| Route | Handler | need |
|---|---|---|
| GET `/v1/books/` | listBooks | **view** — UNION owned+collaborated (R2) |
| GET `/v1/books/{id}` | getBook → getBookByID | view |
| GET `/v1/books/{id}/search` | searchChapterText | view |
| GET `/v1/books/{id}/cover` | getCover | view |
| GET `/v1/books/{id}/stats` | getBookStats | **view** (PO: gate now — was no-owner-check) |
| GET `/v1/books/{id}/chapters` | listChapters | view |
| GET chapter / content / export / draft | getChapter/…Content/export/getDraft | view |
| GET revisions / revision / compare | listRevisions/getRevision/compareRevisions | view |
| GET media-versions / audio / audio-segment | listMediaVersions/listAudioSegments/getAudioSegment | view |
| GET imports / import | listImportJobs/getImportJob | view |
| PATCH `/v1/books/{id}` | patchBook | edit |
| POST/DELETE cover | uploadCover/deleteCover | edit |
| POST chapters | createChapter | edit |
| PATCH chapter / draft | patchChapter/patchDraft | edit |
| **DELETE chapter (trash)** | trashChapter | **edit** (reversible) |
| POST chapter restore | restoreChapter | **edit** |
| POST publish / unpublish | publishChapter/unpublishChapter | edit |
| POST revision restore | restoreRevision | edit |
| POST media / media-generate / media-versions | uploadChapterMedia/generate/createMediaVersion | edit |
| POST audio generate / block-audio | generateAudio/uploadBlockAudio | edit |
| POST import | startImport | edit |
| **DELETE chapter purge** | purgeChapter | **manage** (irreversible) |
| **DELETE media-version** | deleteMediaVersion | **manage** (asset-del, PO) |
| **DELETE audio** | deleteAudioSegments | **manage** (asset-del, PO) |
| DELETE `/v1/books/{id}` (trash) · restore · purge | transitionBookLifecycle | **owner-only (unchanged)** |
| GET `/v1/books/trash` | listTrashedBooks | **owner-only (unchanged)** |
| collaborators list/put/delete | (E0-0) | **owner-only (unchanged)** |

## 3. Mechanism

### 3a. `resolveBookAuth` (one query → level + owner + lifecycle) — DRY core
Refactor the existing `resolveGrant`/`resolveAccess` to share one resolver that also surfaces the **book owner** (needed for quota attribution, §3c):
```go
func (s *Server) resolveBookAuth(ctx, bookID, userID) (lvl GrantLevel, owner uuid.UUID, lifecycle string, err error)
// missing book → (GrantNone, uuid.Nil, "", nil)   — no oracle (R4)
// owner match  → (GrantOwner, owner, lifecycle, nil)
// collaborator → (roleToLevel(role), owner, lifecycle, nil)
// no grant     → (GrantNone, owner, lifecycle, nil) — owner known but NOT leaked
```
`resolveGrant` → `lvl`; `resolveAccess` → `(lvl, lifecycle)`; both delegate (no behavior change to E0-0/E0-1 callers).

### 3b. `authBook` — the grant chokepoint (grant-only; lifecycle stays in handlers)
```go
func (s *Server) authBook(w, r, bookID, need GrantLevel) (caller, owner uuid.UUID, lifecycle string, ok bool) {
    caller, authed := s.requireUserID(r); if !authed { 401 BOOK_FORBIDDEN; return }
    lvl, owner, lc, err := s.resolveBookAuth(ctx, bookID, caller)
    if err != nil      { 503 RESOLVE_FAILED; return }   // fail-closed
    if lvl == GrantNone { 404 BOOK_NOT_FOUND; return }   // none → 404 (no existence oracle, INV-8/H13)
    if !lvl.AtLeast(need){ 403 BOOK_FORBIDDEN; return }   // has access, lacks tier (caller already knows it exists)
    return caller, owner, lc, true
}
```
**No lifecycle gate inside** — book-service handlers already carry precise per-state checks (patchBook 409 on non-active; transition handlers validate bState/cState per case). `authBook` returns `lifecycle` so a handler can reuse it instead of re-querying. This preserves existing lifecycle behavior exactly (unlike glossary E0-1, which had none of its own).

### 3c. The drop-owner transform (R3)
Each in-scope handler: **add `authBook(need)` pre-check at the top**, then **drop the trailing `AND b.owner_user_id=$N` predicate + its arg** from the data query. Because every query is already scoped by `c.id`/`c.book_id=$2`/`book_id=$1` and `authBook` authorized that `bookID`, dropping the owner predicate is IDOR-safe and **requires no `$N` renumbering** (owner is always the last param). The `JOIN books b` becomes droppable where it served only the owner predicate.

**Critical (was the only authz for some reads):** `getBook`/`getChapter` relied on `getBookByID`/`getChapterByID`'s owner filter as their *sole* authz. Once that filter is dropped, those handlers **must** add an explicit `authBook(view)` pre-check, or they leak any book by id. Router deny-test guards this (§5).

### 3d. owner-vs-caller split (quota vs authorship)
`createChapterRecord` and `processTxtImport` charge **the caller's** quota and set `author_user_id = caller`. With collaborators these diverge:
- **quota** (`ensureQuotaRow`/`recalcQuota`/`user_storage_quota`) → **book owner** (content belongs to the owner's book; an editor must not be billed, and the owner's quota is the real ceiling).
- **author_user_id** (revisions/publish snapshots) → **caller** (the actual author — correct attribution; already the caller).
→ thread both `caller` and `owner` (from `authBook`) into `createChapterRecord(caller, owner, …)` and the parse import path.

### 3e. listBooks UNION (R2) — resolved locally, no N+1
```sql
WHERE b.lifecycle_state=$2
  AND (b.owner_user_id=$1 OR EXISTS (SELECT 1 FROM book_collaborators bc WHERE bc.book_id=b.id AND bc.user_id=$1))
```
…and the COUNT mirrors it. Single query (book-service owns both tables). Each item gains an additive **`access_level`** field (`owner|manage|edit|view`) so the FE (E0-5) can distinguish owned vs shared without a second call. `listTrashedBooks` stays owner-only.

## 4. Anti-oracle / error contract
- non-grantee → **404 BOOK_NOT_FOUND** (uniform with missing book; no existence signal).
- grantee under tier (has view, needs edit) → **403 BOOK_FORBIDDEN** (they already hold view, so no new signal).
- book-service unreachable to itself = N/A (local SQL); a DB error → **503 RESOLVE_FAILED** (fail-closed).
- lifecycle conflicts (409) unchanged — emitted by the handlers as today.

## 5. Test plan
- **Router-level deny test (the executable guard — mirrors glossary `grant_mapping_test.go`):** with a stubbed pool, a **view-grantee** gets **403 on every mutating route** (edit+manage) and **200/handler on reads**; a **non-grantee** gets **404 on reads**; book-destructive (trash/purge book) + collaborators + trash-list **403/404 for a non-owner manage-grantee** (owner-only preserved). This is the only check that catches a need-mapping regression (owner-run DB tests mask it — the E0-1 lesson).
- **Unit:** `resolveBookAuth` (owner/each-role/none/missing); `authBook` status mapping (401/404/403/503); listBooks UNION returns shared-with-me; quota charged to owner not caller.
- **Real-PG / live-smoke:** folded into the epic D-E0 live-smoke (book+glossary already proven E0-1). E0-2 adds: collaborator with `edit` PATCHes a book + creates a chapter through the real chain; `view` collaborator denied on PATCH (403); non-grantee 404 on GET. → token `live smoke: edit-collab patches book+creates chapter; view-collab 403; non-grantee 404` or defer row `D-E0-2-LIVE-SMOKE`.

## 6. Risks
- **R-IDOR-drop-owner** — dropping the owner predicate without a matching pre-check leaks by id. Mitigate: `authBook` at the top of every adopted handler + the router deny-test as the executable guard; the transform keeps `c.book_id=$2` scoping.
- **R-book-destructive** — book trash/purge/transfer must stay owner-only. Mitigate: those handlers untouched (still `ensureOwnerBook`); deny-test asserts a manage-grantee can't trash the book.
- **R-quota-misbill** — an editor's chapter must bill the owner. Mitigate: §3d split + unit test.
- **R-fail-direction** — a missed handler stays owner-only (stricter) = fail-safe.
