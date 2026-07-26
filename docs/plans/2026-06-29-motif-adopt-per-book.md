# WI-5 — Per-book adopt (`D-MOTIF-ADOPT-PER-BOOK`) · 2026-06-29

**Status:** DESIGN → BUILD. Size **M** (schema migration + MCP contract + confirm-path = 2 side-effects → min M; ~7 logic changes).

## Decision (user, 2026-06-29): **Model A — book-scoped filter (per-user)**, NOT a tenancy-tier reversal.

Two readings of "per-book adopt" were on the table:

- **(A) Book-scoped filter (CHOSEN).** `owner_user_id` stays = the adopter; a nullable
  `book_id` is a **label** stamped on the clone so it surfaces under that book's library.
  The **read predicate is UNCHANGED** (`owner_user_id IS NULL OR visibility='public' OR
  owner_user_id=$1`). `book_id` is a *sub-filter within the user's own tier* — it does **not**
  add a visibility tier, needs **no** cross-service grant resolution in the predicate, and does
  **not** reverse the audited R1.1.1 "NO book tier" decision. Collaborators each adopt their own.
- **(B) Book collaboration tier (rejected for now).** A true 3rd tenancy tier visible/writable to
  all the book's E0 grantees. Would reverse R1.1.1, touch every motif query with grant resolution,
  and require a mandatory adversarial tenancy review. Deferred as a future track if real
  multi-collaborator book motif libraries are wanted.

**Why A:** composition is already a per-user-per-book model (every `composition_work` /
`outline_node` / `canon_rule` row filters on `user_id`). A book-scoped label is consistent,
delivers the user value ("adopt this trope for Book X"), and carries a fraction of the risk.

## Tenancy invariants preserved (the kinds-bug guard)
- A book-tier clone is **still owner-stamped** = the adopter → satisfies the `motif_user_owned`
  CHECK, stays private, counts against the adopter's own quota. No shared/global row is mutated.
- The read predicate is untouched, so no foreign row becomes visible. `book_id` only *narrows*
  what the owner sees; it never *widens* visibility.
- A book-tier adopt is **EDIT-gated on the target book** at propose AND re-gated at confirm
  (a grant revoked between propose and confirm stops the clone) — mirrors `motif_mine` scope=book.

## Schema (`app/db/migrate.py`, idempotent)
1. `motif.book_id UUID NULL` — per-book label; NULL = global user/system tier.
2. Uniqueness split so the same source can be adopted globally **and** per-book without a false
   collision (the confirm path uses `clone()`, which raises on collision):
   - `uq_motif_user`  → `(owner_user_id, code, language) WHERE owner_user_id IS NOT NULL AND book_id IS NULL`
   - `uq_motif_user_book` → `(owner_user_id, book_id, code, language) WHERE book_id IS NOT NULL`
   (recreated from the old `uq_motif_user` via a guarded `DROP`/`CREATE` for existing DBs).
3. `idx_motif_book ON motif(book_id) WHERE book_id IS NOT NULL` — the book-library list scan.
4. **No CHECK change** — a book row has owner set, so `motif_user_owned` already holds.

## Code
- **`db/models.py`** — `Motif.book_id: UUID | None = None` (owner's full dump only; the public
  catalog + non-owner projection allow-lists do NOT include it → no book-provenance leak).
- **`db/repositories/motif_repo.py`**
  - `_SELECT_COLS` += `book_id`.
  - `clone(..., book_id: UUID | None = None)` — stamp `book_id` on the INSERT.
  - `adopt(..., book_id=None)` + `_clone_with_code(..., book_id=None)` — thread it; idempotency
    re-read keyed on `book_id IS NOT DISTINCT FROM $book` so re-adopt into the SAME book is
    idempotent, into a DIFFERENT book makes a new clone.
  - `list_for_caller(..., book_id=None)` — when set, `(book_id = $n OR book_id IS NULL)`
    ("motifs available to this book" = its book-scoped clones + the user's globals).
- **`mcp/server.py`** — `_MotifAdoptArgs.target: Literal["user","book"]` + `book_id: str | None`;
  `target="book"` requires `book_id`; `_gate(EDIT)` on the book at propose; `book_id` rides the
  confirm payload. (`book_id` is a legitimate resource arg, like `motif_mine` — not in the S2
  forbidden identity-arg set, so `test_no_motif_tool_leaks_scope_arg` still passes.)
- **`routers/actions.py`** — adopt dispatch re-checks `authorize_book(EDIT)` when the payload
  carries a `book_id`; `_execute_motif_adopt` passes `book_id` to `clone()`.
- **HTTP `routers/motif.py`** — `MotifAdopt` gains an optional `book_id` (parity; the FE bridge
  uses the MCP path, but the HTTP route stays consistent).
- **FE** — the adopt affordance gains a "this book / my library" target when a book context exists.

## Tests
- `test_motif_repo` — clone/adopt stamps `book_id`; same-source global + per-book coexist (no
  collision); idempotent re-adopt into the same book; `list_for_caller(book_id=…)` returns
  book-scoped + globals, excludes another book's rows.
- `test_motif_mcp` — adopt `target="book"` requires `book_id`; EDIT-gated; payload carries it;
  S2 leak test still green. `target` still rejects `system`/`public`.
- FE — adopt-to-book wiring test.

## Out of scope (deferred)
- Model B (book collaboration tier) — `D-MOTIF-ADOPT-BOOK-COLLAB-TIER`, only if multi-collaborator
  shared book motif libraries are needed.
