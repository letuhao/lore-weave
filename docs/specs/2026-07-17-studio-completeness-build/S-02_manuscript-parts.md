# S-02 · Manuscript parts (acts / volumes) — editor CRUD + move-chapter-to-part

> **Tier A — DATA-layer build.** The audit found `parts` is written ONLY by the import decomposer
> (`parse.go:192`); there is no public/MCP create/rename/delete route, and `patchChapter`/`reorderChapters`
> never write `part_id`. A Studio user cannot create/rename/delete an act or re-home a chapter — **the
> hierarchy is frozen at import**. **HTML draft:** ✅ net-new (`screen-manuscript-parts.html`).
> **Service:** book-service (Go).

## 1. Goal / user story

A book has a chapter→scene manuscript, and optionally a `parts` layer (acts / volumes) above chapters. An
imported book gets its parts from the decomposer; a book written IN the Studio has none, and even an imported
one can't be reorganised. **Goal:** let a user create / rename / reorder / delete an act, and move a chapter
into / out of / between acts — all persisted, grant-gated, no id churn.

## 2. Current state (verified against code)

```
parts (migrate.go:273)
  id UUID PK · book_id UUID FK→books ON DELETE CASCADE · sort_order INT · title TEXT · path TEXT NOT NULL
  · parse_version INT DEFAULT 1 · lifecycle_state TEXT DEFAULT 'active' · trashed_at · created_at · updated_at
  UNIQUE (book_id, sort_order)
chapters.part_id UUID  (migrate.go:305, nullable; idx_chapters_part)  ── legacy chapters keep it NULL
```
- **Infra already present:** `lifecycle_state` (soft-delete like chapters), `updated_at`, the
  `UNIQUE(book_id, sort_order)` ordering constraint, and the `chapters.part_id` FK column + index. This is a
  route/repo build over an existing schema — NOT a schema-from-scratch.
- Writers today: `parse.go:192` (parts) + `parse.go:241` (chapters carry `part_id` at import). Nothing else.
- `patchChapter` (`server.go:1903`) + `POST /chapters/reorder` exist but **never touch `part_id`**.

## 3. Tenancy — via the parent book (no new scope decision)

Parts are `book_id`-scoped; book access is already grant-gated through `authBook(…, Grant…)`. Every part
route resolves the book first and enforces the grant (VIEW for reads, EDIT for writes), then scopes every
query by `book_id`. No new scope key, no shared-row risk — a part cannot exist without its book, and the FK
cascade already handles book deletion. **Move-chapter-to-part must verify the target part is in the SAME
book** (a cross-book move is a tenancy breach) — gate on `part.book_id = chapter.book_id`.

## 4. Schema — one nullability fix, otherwise additive

`path TEXT NOT NULL` is import-oriented (the decomposer stores the source file path). A user-created act has
no source path. Two options — **choose (a)**:
- **(a) synthesize a path** from the title at create time (`slugify(title)` with a `part-<sort_order>`
  fallback), keeping `NOT NULL` intact and the column meaningful. Preferred — no migration, no null-handling
  downstream.
- (b) make `path` nullable. Rejected: it weakens a column other code may assume non-null.

No other schema change. (Optionally add `version INT` for OCC as canon/S-01 do — but parts rename is
low-contention and `updated_at` + last-write-wins is acceptable here; **decision: no OCC for parts**,
recorded so it isn't mistaken for an omission. Chapters already have their own OCC on draft.)

## 5. Store methods (book-service, inline pgx per house style)

- `createPart(ctx, bookID, title) -> Part` — `sort_order = COALESCE(MAX(sort_order),0)+1` for the book;
  `path = slugify(title)`; `lifecycle_state='active'`. 409 on the (book_id, sort_order) race → retry once.
- `renamePart(ctx, bookID, partID, title) -> Part` — `UPDATE … SET title, updated_at WHERE id AND book_id`.
- `reorderParts(ctx, bookID, orderedIDs []UUID)` — two-phase `sort_order` rewrite (offset into a temp range
  then back, the same pattern `reorderChapters` uses) to respect `UNIQUE(book_id, sort_order)`.
- `archivePart(ctx, bookID, partID)` — soft `lifecycle_state='trashed'`, `trashed_at=now()`. **Its chapters
  are NOT deleted** — they set `part_id = NULL` (fall back to the flat manuscript). State this in the route.
- `restorePart(ctx, bookID, partID)` — `lifecycle_state='active'`, `trashed_at=NULL`.
- `moveChapterToPart(ctx, bookID, chapterID, partID *UUID)` — `UPDATE chapters SET part_id=$ WHERE id AND
  book_id`; `partID=NULL` un-homes it; verify `partID` (when non-nil) belongs to `bookID` first.

## 6. REST routes (grant-gated via authBook)

```
GET    /v1/books/{bookId}/parts                         (list active; ?include_trashed)
POST   /v1/books/{bookId}/parts                         (create; 201)
PATCH  /v1/books/{bookId}/parts/{partId}                (rename)
POST   /v1/books/{bookId}/parts/reorder                 (body: ordered ids)
DELETE /v1/books/{bookId}/parts/{partId}                (soft trash; its chapters → part_id NULL; 204)
POST   /v1/books/{bookId}/parts/{partId}/restore        (restore)
PATCH  /v1/books/{bookId}/chapters/{chapterId}/part     (body: {part_id: uuid|null}) — move / un-home
```
The last route is deliberately separate from `patchChapter` so the move is an explicit, auditable action
(and so `patchChapter`'s existing OCC contract is untouched).

## 7. MCP tools (MCP-first — agent parity)

`book_part_{create,rename,reorder,archive,restore}` + `book_chapter_set_part` on book-service. The audit
also flagged a **missing MCP chapter-reorder tool** (S-07) — note it here for coherence but ship it in S-07;
this spec adds the part verbs + `set_part`. `part_id` in `book_chapter_set_part` is a nullable UUID arg
(null = un-home).

## 8. Frontend (net-new → HTML draft first)

The manuscript navigator (`StudioSideBar` manuscript view) currently lists chapters flat. Extend it to a
**two-level tree**: parts as collapsible group headers with chapters nested, an "unassigned" group for
`part_id IS NULL`, drag-a-chapter-between-parts (persist via the `…/chapters/{id}/part` route — trusted
pointer-drag, per the `playwright-cdp-mouse-drives-d3-drag` lesson if using a DnD lib), and part
create/rename/reorder/trash affordances. The HTML draft decides the tree layout, the drag target styling,
and the "unassigned" bucket presentation. Reuses the existing manuscript navigator shell — it is an
enhancement of a real surface, but the parts LAYER never had a GUI, hence the draft.

## 9. Tests (evidence gate)

- **tenancy:** a user without an EDIT grant on the book gets 403 on every write; a chapter cannot be moved
  to a part in a DIFFERENT book (400/403); list is book-scoped.
- **archive semantics:** trashing a part sets its chapters' `part_id = NULL` (they survive in the flat
  manuscript), NOT cascade-deletes them; restore does not re-home them (an explicit, non-magical choice).
- **reorder:** respects `UNIQUE(book_id, sort_order)` with no transient collision (two-phase); the flat
  chapter order is unaffected by part order.
- **move:** `part_id` updates in place, no chapter id churn, no re-embed; un-home sets NULL.
- **import unbroken:** the decomposer still writes parts + `part_id` exactly as before.
- **MCP parity:** each tool round-trips; `set_part` accepts null.

## 10. Out of scope / by-design

- No nesting of parts (acts within volumes) — the schema is one level; multi-level is a separate spec.
- No OCC on parts (§4) — deliberate.
- Scene-level authoring stays in composition-service (by design — book-service owns manuscript structure,
  not scene prose).
