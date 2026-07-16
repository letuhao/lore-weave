# 34a · Arc-template BOOK-SHARED tier (D-ARC-TEMPLATE-BOOK-TIER)

> **Status:** S2 detail design, 2026-07-17. Amends [`34`](34_arc_templates_and_deconstruct.md) §OQ-6.
> **Why:** spec 34 OQ-6 DEFERRED a book-shared tier for `arc_template` (gate #2 — schema + tenancy).
> The PO (2026-07-16) pulled it in (`D-S2-NO-DEFER`). This is its detail design.
> **The safe move: MIRROR the PROVEN `motif.book_shared` pattern verbatim — do NOT invent a tenancy
> model.** A rushed, novel tenancy tier is exactly the User-Boundaries LOCKED bug class (a shared row a
> regular user can mutate for everyone). Motif already shipped this (`D-MOTIF-ADOPT-BOOK-COLLAB-TIER`,
> model B); every decision below is "what motif did", verified against `migrate.py`.

---

## 0 · The tenancy model (mirrors motif model B — LOCKED)
An arc template lives in one of FOUR tiers (was three; this adds the shared one):
| tier | `owner_user_id` | `book_id` | `book_shared` | who WRITES | visible to |
|---|---|---|---|---|---|
| System | NULL | NULL | false | admin/seed only | everyone (read-only) |
| Per-user | a user | NULL | false | that user | that user |
| Public | a user | NULL | false, `visibility='public'` | the owner | everyone (read-only, via catalog) |
| **Book-shared (NEW)** | a user (attribution) | a book | **true** | **the book's EDIT-grantees** | **the book's VIEW-grantees** |

**The key rule (User Boundaries):** a book-shared row's access is the **book grant resolved at the
caller**, NOT the owner. `owner_user_id` is *attribution only* — an EDIT-grantee who is not the owner
may still edit it. This is the whole point of a collaboration tier, and it is what motif does.

## 1 · Schema (mirror `motif` lines 721/773/792 — verified)
```sql
-- add the column FIRST (an index referencing it before it exists would fail — motif's own note)
ALTER TABLE arc_template ADD COLUMN IF NOT EXISTS book_id      UUID;
ALTER TABLE arc_template ADD COLUMN IF NOT EXISTS book_shared  BOOLEAN NOT NULL DEFAULT false;
-- both-or-neither shape (identical to motif_book_shared_shape): a shared row MUST carry a book + an
-- owner (attribution) and stay visibility='private' (the shared axis and the public axis are disjoint)
ALTER TABLE arc_template ADD CONSTRAINT arc_template_book_shared_shape
  CHECK (NOT book_shared OR (book_id IS NOT NULL AND owner_user_id IS NOT NULL AND visibility = 'private'));
-- per-BOOK dedup for the shared tier (one code+language per book), + keep the per-user dedup scoped
-- to book_id IS NULL so a user's private lib and a book-shared clone don't collide on the same code.
CREATE UNIQUE INDEX IF NOT EXISTS uq_arc_template_user_nobook
  ON arc_template(owner_user_id, code, language) WHERE owner_user_id IS NOT NULL AND book_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_arc_template_book_shared
  ON arc_template(book_id, code, language) WHERE book_id IS NOT NULL AND book_shared;
CREATE INDEX IF NOT EXISTS idx_arc_template_book ON arc_template(book_id) WHERE book_id IS NOT NULL;
```
⚠ **The existing `uq_arc_template_user ON (owner_user_id, code, language) WHERE owner_user_id IS NOT
NULL` must be REPLACED by the `…_nobook` variant** (add `AND book_id IS NULL`) — else a book-shared
clone of a code the user already owns privately would 23505 against the old index. This is a
partial-unique-index amendment ([[postgres-partial-index-on-conflict-predicate-must-match]]).
Migration order: add columns → create the new `_nobook` index → DROP the old `uq_arc_template_user` →
create the book_shared index. (Drop-after-create so no window has zero uniqueness.)

## 2 · The write paths (mirror motif's `target='book_shared'`)
`ArcTemplateRepo.create` / `.adopt` gain a `target: 'user' | 'book_shared'` + `book_id`:
- `target='user'` (default) — today's behavior (owner-stamped private).
- `target='book_shared'` — set `book_id` + `book_shared=true`, `visibility='private'`; **gate EDIT on
  that book** (server-side, before the repo — the `_gate_book` chokepoint the routes already have).
- The **list** read (`scope='all'`) must additionally surface book-shared rows for the CURRENT book
  the caller has VIEW on (a `book_id = $book AND book_shared` branch). A book-shared row is NOT visible
  to a user with no grant on that book.

## 3 · The doors (both — parity)
- **REST** (`arc.py`): `POST /arc-templates` + `/{id}/adopt` accept `{target, book_id}`; `_gate_book`
  EDIT when `target='book_shared'`. `GET /arc-templates?scope=all&book_id=` adds the shared branch.
- **MCP** (`server.py`): `_ArcTemplateCreateArgs`/`_ArcAdoptArgs` gain `target`/`book_id` (mirror
  `_MotifCreateArgs`). Same gate. 3-schema-source discipline.
- **FE**: the arc-templates panel's tier filter gains **"Book"** (rows where `book_shared && book_id
  === this book`); adopt offers "adopt to this book (shared with collaborators)" (mirrors motif's
  `adoptEstimate({shared:true})`). `arcApi.create/adopt` gain the optional `{target, bookId}`.

## 4 · Tests (the tenancy proof — MANDATORY, this is the critical class)
- **DB/integration:** a book-shared row is (a) editable by an EDIT-grantee who is NOT the owner;
  (b) INVISIBLE to a user with no grant on the book; (c) the shape CHECK rejects `book_shared=true`
  with a NULL book or `visibility='public'`; (d) two books may each hold the same `code` (per-book
  dedup); (e) a user's private lib and a book-shared clone of the same code coexist (the `_nobook`
  amendment). **A non-grantee MUST NOT read or write a book-shared row** — the User-Boundaries LOCKED
  assertion; a green suite without this test is the drift this whole tier risks.
- **Route:** `target='book_shared'` with no EDIT on the book → 403/404 (uniform); the create never runs.

## 5 · Compliance
- **User Boundaries:** access derives from the **book grant on the row's `book_id`**, never the owner
  (a non-owner EDIT-grantee writes; a non-grantee is blocked). No shared `UNIQUE(code)` — the shared
  dedup is `UNIQUE(book_id, code, language)`. Mirrors motif exactly.
- **No rushed novelty:** every schema line + gate mirrors the shipped `motif.book_shared`; the risk of
  a novel tenancy bug is retired by copying the proven one.
- **Migration safety:** additive columns + a drop-after-create index swap; a dry-run row-count of
  existing arc_template rows before the index swap (none are book_shared, so the swap is a no-op on
  data — verify with a scan, [[add-column-if-not-exists-never-revisits-a-bad-default]] does not apply
  since these are NEW columns).
