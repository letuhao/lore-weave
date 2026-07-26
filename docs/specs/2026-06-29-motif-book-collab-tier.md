# Spec — Motif book-collaboration tier (model B) + HTTP adopt-to-book · 2026-06-29

**Branch:** `feat/narrative-pattern-library` · **Owner:** main session · **Size:** XL (tenancy-critical → `/review-impl` mandatory).

Two deferred future-feature rows, specced together because they share the `book_id`
adopt surface:

| ID | Gate | Scope |
|---|---|---|
| `D-MOTIF-HTTP-ADOPT-BOOK` | #5 (minor) | Expose the already-built `book_id` on the **HTTP** `POST /motifs/{id}/adopt` route (parity with the MCP path), **with the same EDIT gate**. |
| `D-MOTIF-ADOPT-BOOK-COLLAB-TIER` | #2 (large/structural) | A **third tenancy tier**: a *shared* book motif library, visible to the book's VIEW-grantees and writable by its EDIT-grantees. This is **model B** — it *adds* a tier (it does NOT reverse the per-user model A, which ships as `book_id` private label). |

---

## 0. Context — what already exists (do NOT rebuild; [[verify-built-before-building]])

- **Model A (`D-MOTIF-ADOPT-PER-BOOK`, shipped):** `motif.book_id` is a **private per-user
  label**. The clone is still owner-stamped = the adopter; `book_id` only *narrows* what that
  owner sees, never widens visibility. The read predicate is **unchanged**. Two collaborators
  each adopt their own copy.
- **`MotifRepo.clone/adopt/_clone_with_code/list_for_caller`** already thread `book_id`.
- **MCP `composition_motif_adopt`** already has `target: Literal["user","book"]` + `book_id`,
  EDIT-gated at propose (`_gate`) and re-gated at confirm (`authorize_book`).
- **HTTP `POST /motifs/{id}/adopt`** does **NOT** expose `book_id` (this spec's slice 0).
- Tenancy backstop: `motif_user_owned CHECK (owner_user_id IS NOT NULL OR visibility <> 'private')`;
  read predicate `_VISIBLE_PREDICATE = (owner_user_id IS NULL OR visibility='public' OR owner_user_id=$1)`.
- Book grant chokepoints: MCP `_gate(tc, book_id, GrantLevel.X)`; HTTP `authorize_book(grant, book_id, caller, need)`
  (`none`→404 no-oracle, under-tier→403). **Context-scoped, per-book** — there is no
  "list all my granted books" capability, and this spec does NOT add one.

---

## 1. The tenancy model (the kinds-bug guard — read first)

Model B introduces a **System → Per-user → Per-book(shared)** resolution. The per-book shared
tier is the third tier from CLAUDE.md's table (owner = a `book_id`, writers = owner + grantees).

**A book-shared motif row:**
- `book_id` SET = the book it belongs to.
- `book_shared = true` (the new marker; default `false`).
- `owner_user_id` SET = the **creator** (kept for lineage/quota/attribution + to satisfy the
  `motif_user_owned` CHECK). Ownership here is *attribution*, **not** an access gate — access is
  the **book grant**, resolved at the caller layer.
- `visibility = 'private'` ALWAYS (a shared row is **never** in the public catalog — the
  `visibility='public'` axis and the `book_shared` axis are orthogonal; a CHECK enforces this so a
  shared row can't leak into global discovery).

**How the three decisions land:**

1. **Read = context-scoped (per-book gate).** A book-shared row is visible **only** when the
   caller is operating *inside a specific book they hold ≥VIEW on*. The grant is resolved **once,
   at the caller (router/tool)**, by the existing `_gate`/`authorize_book` on that one book; the
   repo then trusts the gated `book_id` and matches `book_shared AND book_id = $X`. The base
   `_VISIBLE_PREDICATE` is **untouched** — so `get_visible(id)` (used by adopt-source reads, link
   anchors, etc. with no book context) still returns a foreign shared row as **None** (fail-closed,
   no oracle). Shared rows surface ONLY through the book-context list/get methods below.

   *Consequence (deliberate):* there is **no** global "show me every shared motif across my books"
   list. That would need cross-service book enumeration and a wider predicate — explicitly out of
   scope (the rejected "global resolution" option).

2. **Write = any EDIT-grantee (edit AND archive).** Patch/archive of a shared row are gated by
   `authorize_book(..., EDIT)` on the row's book at the caller, then the repo matches
   `id=$id AND book_shared AND book_id=$X` (NO `owner_user_id` filter — any grantee may edit or
   archive). Optimistic-lock `version` still blocks a blind clobber between two collaborators.

3. **Create surface = adopt + create + mine.** All three gain a way to target the shared tier,
   each **EDIT-gated** on the book before the write.

---

## 2. Schema (`app/db/migrate.py`, idempotent — guarded `ALTER`/`DROP`/`CREATE`)

```sql
-- the shared-tier marker (default false = model-A private label / global / system, all unchanged)
ALTER TABLE motif ADD COLUMN IF NOT EXISTS book_shared BOOLEAN NOT NULL DEFAULT false;

-- a shared row MUST carry a book + a creator (owner), and is NEVER publicly published
-- (the two visibility axes stay orthogonal — a shared row can't leak into the public catalog).
ALTER TABLE motif ADD CONSTRAINT motif_book_shared_shape
  CHECK (NOT book_shared OR (book_id IS NOT NULL AND owner_user_id IS NOT NULL AND visibility = 'private'));

-- dedup: the SHARED tier is per-BOOK (one code+language per book across ALL collaborators)
CREATE UNIQUE INDEX IF NOT EXISTS uq_motif_book_shared
  ON motif(book_id, code, language) WHERE book_shared;

-- model-A private book label keeps per-(owner,book) dedup, now scoped to NOT shared
-- (guarded DROP+CREATE so an existing DB re-narrows the old partial)
DROP INDEX IF EXISTS uq_motif_user_book;
CREATE UNIQUE INDEX IF NOT EXISTS uq_motif_user_book
  ON motif(owner_user_id, book_id, code, language) WHERE book_id IS NOT NULL AND NOT book_shared;

-- the shared-library list scan within a book
CREATE INDEX IF NOT EXISTS idx_motif_book_shared ON motif(book_id) WHERE book_shared;
```

`uq_motif_user` (global, `book_id IS NULL`) and `uq_motif_system` are unchanged.

---

## 3. Repo (`db/repositories/motif_repo.py`)

`_SELECT_COLS += book_shared`. `db/models.py` `Motif.book_shared: bool = False` (owner full dump
only; the catalog `_CATALOG_COLS` allow-list does NOT include it → no shared-provenance leak on
the public path).

**New / changed methods (all keep existing signatures additive):**

- `clone(..., book_id=None, book_shared=False)` — stamp both on the INSERT. The shared INSERT sets
  `visibility='private'` (already the clone default).
- `adopt(..., book_id=None, book_shared=False)` →
  - When `book_shared`: advisory lock keyed on the **book** (`motif-adopt-book:{book_id}`) not the
    user (serialize concurrent grantees adopting the same source into the same book); idempotency
    re-read keyed on `book_shared AND book_id=$book AND source_ref=$lineage` (**no owner filter** —
    one shared clone of a source per book, regardless of which grantee adopts first); suffix-retry
    catches `uq_motif_book_shared`.
  - Else: the model-A path, unchanged.
- `_clone_with_code(..., book_id=None, book_shared=False)` — thread both; the collision retry already
  catches `uq_motif_user` / `uq_motif_user_book`; add `uq_motif_book_shared`.
- `create(..., book_id=None, book_shared=False)` — stamp both; a shared create still server-stamps
  `owner_user_id = creator` (no owner arg). Collision → `UniqueViolationError` (router/tool → 409).
- **`list_in_book(caller, book_id, ...)`** — the book-context list: returns the caller's own rows
  (globals + this book's private labels) **PLUS** the book's shared tier:
  `(owner_user_id IS NULL OR owner_user_id=$caller OR (book_shared AND book_id=$X))`
  `AND (book_id IS NULL OR book_id=$X)`. Caller must have VIEW-gated `$X` first.
- **`get_in_book(caller, motif_id, book_id)`** — single read of a row that is either the caller's own
  or the book's shared tier: `WHERE id=$id AND (owner_user_id=$caller OR (book_shared AND book_id=$X))`.
  Caller VIEW-gated `$X`. Returns None → H13.
- **`patch_shared(caller, motif_id, book_id, args, expected_version)`** and
  **`archive_shared(caller, motif_id, book_id)`** — the EDIT-grantee write path: WHERE clause keys on
  `book_shared AND book_id=$X` instead of `owner_user_id=$caller`. Reuse the existing patch jsonb/
  version machinery (refactor `patch` to take an internal `_scope_where` so the owner path and the
  shared path share the body; the public `patch` signature is unchanged).

`get_visible` / `list_for_caller` (non-book) / `get_by_codes` / `list_public` are **UNCHANGED** — a
foreign shared row stays invisible to them (fail-closed).

---

## 4. Surfaces

### 4.1 MCP (`mcp/server.py`)
- `_MotifAdoptArgs.target: Literal["user","book","book_shared"]`. `book`=model-A label;
  `book_shared`=the shared tier. Both require `book_id` + `_gate(EDIT)`; the confirm payload carries
  `book_shared: bool`.
- `_MotifCreateArgs` gains `target: Literal["user","book_shared"]` + `book_id`. `book_shared` →
  `_gate(tc, book_id, EDIT)` then `repo.create(..., book_id, book_shared=True)`. **Create stays
  Tier-A auto-write** but the EDIT gate makes the cross-tenant write safe.
- `composition_motif_mine`: a mined job may target the shared tier — `_MotifMineArgs.promote_target:
  Literal["user","book_shared"] = "user"` (only valid with `scope="book"`; the worker stamps
  `book_shared` + `book_id` on each `create`). EDIT is already gated for `scope="book"` mine.
- **Book-context reads/writes:** add `composition_motif_book_list(book_id)` (VIEW-gated → `list_in_book`),
  and make `composition_motif_patch`/`composition_motif_archive` accept an optional `book_id` →
  when set, EDIT-gate the book and use `patch_shared`/`archive_shared`. (Owner path unchanged when
  `book_id` omitted.)

### 4.2 Confirm dispatch (`routers/actions.py`)
- `_execute_motif_adopt`: read `book_shared` from payload; when true, re-`authorize_book(EDIT)` (the
  dispatch already re-gates any payload `book_id`) and pass `book_shared=True` to `clone()`.
- `_execute_motif_mine`: thread `promote_target` into the worker spec.

### 4.3 HTTP (`routers/motif.py`) — **slice 0 lives here too**
- `MotifAdopt` gains `target: Literal["user","book","book_shared"] = "user"` + `book_id: UUID|None`.
  `book`/`book_shared` require `book_id`; the route resolves a `GrantClient` dep and
  `_gate_book(grant, book_id, EDIT)` **before** the clone (this is the security core of
  `D-MOTIF-HTTP-ADOPT-BOOK` — the HTTP route must NOT be a softer path than MCP). Passes
  `book_id` + `book_shared` to `repo.adopt`.
- `GET /motifs/book/{book_id}` → VIEW-gate → `list_in_book` (the shared-library list for non-MCP
  clients). Optional; ship if cheap.

### 4.4 Mine worker (`engine/motif_mine.py`)
- `run_mine_motifs` reads `promote_target`/`book_shared` from the spec; `_persist` passes
  `book_id` + `book_shared=True` to `motif_repo.create`. The per-book shared dedup means a re-mine
  collides on `uq_motif_book_shared` → the existing no-silent-drop `code_collision` path handles it.

---

## 5. motif_link in the shared tier (scoped OUT, noted)

The `motif_link_guard` same-tier check is `from_owner IS DISTINCT FROM to_owner`. Two shared motifs
created by **different** grantees have different `owner_user_id` → a link between them is **rejected**
(fail-closed, safe). A single user linking two shared rows they both created works. Full
cross-grantee shared-graph editing needs the guard to compare `book_id` for shared rows — **deferred**
as `D-MOTIF-LINK-SHARED-TIER` (gate #2). Not in this slice.

---

## 6. FE
- The adopt affordance gains a **third** target when a book context exists: *My library* /
  *This book (private)* / *This book (shared with collaborators)*.
- A **Shared** filter/section in the book's motif library view (`list_in_book` via the MCP
  `composition_motif_book_list` bridge or the HTTP `GET /motifs/book/{id}`), badged so a user can
  tell a shared row from their own.

---

## 7. Tests
- **Repo (`test_motif_repo`):** shared clone/adopt stamps `book_shared`+`book_id`; per-book dedup
  (two grantees adopting the same source into the same book → ONE shared row, second is idempotent);
  a shared row coexists with a model-A private label + a global of the same code (no false collision);
  `list_in_book` returns own-globals + own-labels + others' shared, EXCLUDES another book's shared and
  a foreign user's globals; `get_in_book` returns a shared row for a (gated) book, None otherwise;
  `patch_shared`/`archive_shared` succeed for the WHERE-matched book, no-op (None) for a wrong book;
  `get_visible` STILL returns None for a foreign shared row (the fail-closed invariant).
- **MCP (`test_motif_mcp`):** adopt `target="book_shared"` requires `book_id` + EDIT-gates; payload
  carries `book_shared`; create `target="book_shared"` EDIT-gates; the S2 scope-arg leak test stays
  green (`book_id`/`target` are legitimate resource args, like `motif_mine`).
- **Schema (`test_motif_migrate`):** the new column/CHECK/indexes exist + are idempotent on re-run;
  the shape CHECK rejects `book_shared` with NULL book / NULL owner / non-private visibility.
- **Router (`test_motif_router`):** HTTP adopt `target="book_shared"`/`"book"` EDIT-gates (403 under
  tier, 404 no grant) and threads `book_id`; the default `target="user"` path is unchanged.
- **FE:** adopt-to-shared wiring; the Shared library section renders + badges.

## 8. VERIFY
- Backend unit suite green; provider-gate clean.
- **Live smoke (cross-service — composition + book-service grant):** real `loreweave_composition`:
  migration idempotent; a grantee adopts a source into a book's shared tier; a *second* grantee sees
  it via `list_in_book` and edits it (EDIT path); a NON-grantee gets H13 on `get_in_book`/list;
  `get_visible` returns None for the foreign shared row; 0 leaked rows on the global/catalog paths.
- **`/review-impl` (mandatory, tenancy boundary):** adversarial pass on the read/write predicates
  and the grant gates — specifically that no path lets a non-grantee see or write a shared row, and
  that a shared row never reaches the public catalog or a non-book global list.

## 9. Out of scope / deferred
- `D-MOTIF-LINK-SHARED-TIER` (§5) — cross-grantee shared-graph link editing.
- Global "all my shared motifs across books" list (would need cross-service book enumeration).
- Publish/unlist of a shared row (a shared row is private by CHECK; publishing is a separate flip
  from the owner's own copy).
