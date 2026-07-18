// S-02 — manuscript parts (acts / volumes) editor CRUD + move-chapter-to-part.
//
// Why this file exists: `parts` was written ONLY by the import decomposer
// (parse.go:192); there was no public create/rename/reorder/delete route, and
// patchChapter/reorderChapters never touched `chapters.part_id`. So a Studio user
// could not create/rename/delete an act or re-home a chapter — the hierarchy was
// FROZEN at import. This adds the missing verbs over the EXISTING schema (parts +
// chapters.part_id already carry lifecycle_state, updated_at, the
// UNIQUE(book_id, sort_order) ordering constraint, and the FK index).
//
// Structure: the SQL lives in store methods (storeCreatePart, storeReorderParts, …)
// so BOTH surfaces — the REST routes below AND the MCP tools (book_part_*,
// book_chapter_set_part in mcp_tools_parts.go) — share ONE implementation. A REST
// route parses + grant-gates + maps the store error to an HTTP status; an MCP tool
// grant-gates + maps it to the kit sentinel. Neither re-implements the write.
//
// Sealed decisions (docs/specs/2026-07-17-studio-completeness-build/01_DECISIONS.md):
//   - `path` is NOT NULL and import-oriented. A user-created act has no source path,
//     so we SYNTHESIZE one from the title (slugifyPartPath). Keeps the column
//     meaningful + non-null with no migration.
//   - NO OCC on parts — rename is low-contention, updated_at + last-write-wins is fine.
//   - Trashing a part UN-HOMES its chapters (part_id = NULL) — they survive in the
//     flat manuscript — it never cascade-deletes them. Restore does NOT re-home.
//
// Tenancy: parts are book_id-scoped; access is grant-gated (VIEW to read, EDIT to
// write) exactly like chapters. Every query is scoped by book_id. A move verifies
// the target part belongs to the SAME book (a cross-book move is a tenancy breach).
package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// Store-layer sentinels, mapped to HTTP by the REST routes and to kit errors by the
// MCP tools. errChapterNotFound is shared from server.go.
var (
	errPartNotFound  = errors.New("part not found")
	errPartNotInBook = errors.New("target part is not an active part of this book")
	// errReorderMismatch: ordered_ids was not exactly the book's active part set.
	errReorderMismatch = errors.New("ordered_ids must list every active part of this book exactly once")
)

// partView is the JSON shape returned for a part. sort_order drives the act
// ordering; lifecycle_state is 'active' | 'trashed' (soft-delete, like chapters).
type partView struct {
	PartID         uuid.UUID `json:"part_id"`
	BookID         uuid.UUID `json:"book_id"`
	Title          *string   `json:"title"`
	Path           string    `json:"path"`
	SortOrder      int       `json:"sort_order"`
	LifecycleState string    `json:"lifecycle_state"`
	CreatedAt      any       `json:"created_at"`
	UpdatedAt      any       `json:"updated_at"`
}

const partSelectCols = `id, book_id, title, path, sort_order, lifecycle_state, created_at, updated_at`

func scanPart(row pgx.Row) (partView, error) {
	var p partView
	err := row.Scan(&p.PartID, &p.BookID, &p.Title, &p.Path, &p.SortOrder, &p.LifecycleState, &p.CreatedAt, &p.UpdatedAt)
	return p, err
}

// slugifyPartPath turns a user-supplied act title into a stable, filesystem-ish
// path token so the NOT NULL `path` column stays meaningful for a user-created part
// (the import decomposer sets it from the source file; a Studio act has no file).
// Lowercases, keeps [a-z0-9], collapses every other run to a single '-', trims. If
// the title has no ASCII-alphanumerics (e.g. a purely CJK title) it yields "" and
// the caller falls back to "part-<sort_order>" — a slug is convenience, not identity
// (the id + (book_id, sort_order) are identity).
func slugifyPartPath(title string) string {
	var b strings.Builder
	prevHyphen := false
	for _, r := range strings.ToLower(strings.TrimSpace(title)) {
		switch {
		case (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9'):
			b.WriteRune(r)
			prevHyphen = false
		default:
			if !prevHyphen && b.Len() > 0 {
				b.WriteByte('-')
				prevHyphen = true
			}
		}
	}
	return strings.Trim(b.String(), "-")
}

// partPath returns slugify(title), or "part-<sort_order>" when the title yields no
// usable slug. sortOrder=0 signals "unknown yet" → the caller backfills.
func partPath(title string, sortOrder int) string {
	if s := slugifyPartPath(title); s != "" {
		return s
	}
	if sortOrder > 0 {
		return "part-" + strconv.Itoa(sortOrder)
	}
	return ""
}

// ═══════════════════════════════════════════════════════════════════════════
// Store methods — the single implementation shared by REST + MCP.
// They do NOT check grants or book lifecycle (the caller's job); they only own the
// SQL + the store-layer sentinels. Every query is scoped by book_id.
// ═══════════════════════════════════════════════════════════════════════════

// storeCreatePart appends an act at sort_order = MAX+1, path synthesized from the
// title. A racing create can collide on UNIQUE(book_id, sort_order) → retry once
// (the second racer just takes MAX+2).
func (s *Server) storeCreatePart(ctx context.Context, bookID uuid.UUID, title string) (partView, error) {
	title = strings.TrimSpace(title)
	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		// Each attempt is its own txn so the C2 emit stays ATOMIC with the INSERT; a unique-violation
		// racer rolls its txn back and retries (the second racer just takes MAX+2).
		p, err := s.createPartTx(ctx, bookID, title)
		if err == nil {
			return p, nil
		}
		lastErr = err
		if !isUniqueViolation(err) {
			break
		}
	}
	return partView{}, lastErr
}

func (s *Server) createPartTx(ctx context.Context, bookID uuid.UUID, title string) (partView, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return partView{}, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck // no-op after Commit
	row := tx.QueryRow(ctx, `
INSERT INTO parts(book_id, sort_order, title, path)
VALUES(
  $1,
  (SELECT COALESCE(MAX(sort_order),0)+1 FROM parts WHERE book_id=$1),
  $2,
  $3
)
RETURNING `+partSelectCols,
		bookID, nullIfEmpty(title), partPath(title, 0))
	p, err := scanPart(row)
	if err != nil {
		return partView{}, err
	}
	// Backfill a slug that couldn't know its sort_order at INSERT time (CJK title → empty slug →
	// "part-<n>"). Cheap single-row update, only when needed.
	if p.Path == "" {
		fallback := partPath(title, p.SortOrder)
		if _, err := tx.Exec(ctx,
			`UPDATE parts SET path=$3 WHERE id=$1 AND book_id=$2`, p.PartID, bookID, fallback); err == nil {
			p.Path = fallback
		}
	}
	if err := emitManuscriptPartChanged(ctx, tx, bookID); err != nil {
		return partView{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return partView{}, err
	}
	return p, nil
}

// storeRenamePart renames an active act (LWW — no OCC). errPartNotFound if absent.
func (s *Server) storeRenamePart(ctx context.Context, bookID, partID uuid.UUID, title string) (partView, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return partView{}, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck // no-op after Commit
	row := tx.QueryRow(ctx, `
UPDATE parts SET title=$3, updated_at=now()
WHERE id=$1 AND book_id=$2 AND lifecycle_state='active'
RETURNING `+partSelectCols,
		partID, bookID, nullIfEmpty(strings.TrimSpace(title)))
	p, err := scanPart(row)
	if errors.Is(err, pgx.ErrNoRows) {
		return partView{}, errPartNotFound
	}
	if err != nil {
		return partView{}, err
	}
	if err := emitManuscriptPartChanged(ctx, tx, bookID); err != nil { // C2 dual-write
		return partView{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return partView{}, err
	}
	return p, nil
}

// storeReorderParts rewrites the whole active ordering. orderedIDs must be EXACTLY
// the book's active parts (a subset/superset/foreign id → errReorderMismatch).
// Two-phase negate/rewrite (like reorderChapters) because UNIQUE(book_id, sort_order)
// is checked per row; FOR UPDATE serializes racing reorders. Caller pre-checks
// empty/duplicate ids (pure input validation).
//
// Returns `prior` — the active order BEFORE the rewrite, captured from the same
// FOR UPDATE snapshot — so the MCP undo hint is an ACCURATE reverse op (never a
// best-effort second query that could race or come back empty).
func (s *Server) storeReorderParts(ctx context.Context, bookID uuid.UUID, orderedIDs []uuid.UUID) (prior []uuid.UUID, out []partView, err error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, nil, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck // no-op after Commit

	rows, err := tx.Query(ctx,
		`SELECT id FROM parts WHERE book_id=$1 AND lifecycle_state='active' ORDER BY sort_order, id FOR UPDATE`, bookID)
	if err != nil {
		return nil, nil, err
	}
	existing := make(map[uuid.UUID]bool)
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			rows.Close()
			return nil, nil, err
		}
		existing[id] = true
		prior = append(prior, id) // ORDER BY sort_order ⇒ this IS the pre-reorder order
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return nil, nil, err
	}
	if len(orderedIDs) != len(existing) {
		return nil, nil, errReorderMismatch
	}
	for _, id := range orderedIDs {
		if !existing[id] {
			return nil, nil, errReorderMismatch
		}
	}

	// Phase 1: park every active slot in the negative space (positive → negative;
	// disjoint from the target positives, so the per-row unique check never trips).
	if _, err := tx.Exec(ctx,
		`UPDATE parts SET sort_order = -sort_order - 1 WHERE book_id=$1 AND lifecycle_state='active'`, bookID); err != nil {
		return nil, nil, err
	}
	// Phase 2: write the dense 1..N sequence (negative → positive; disjoint again).
	out = make([]partView, 0, len(orderedIDs))
	for i, id := range orderedIDs {
		row := tx.QueryRow(ctx, `
UPDATE parts SET sort_order=$3, updated_at=now()
WHERE id=$1 AND book_id=$2
RETURNING `+partSelectCols, id, bookID, i+1)
		p, err := scanPart(row)
		if err != nil {
			return nil, nil, err
		}
		out = append(out, p)
	}
	// C2 dual-write: reorder changed every part's rank → the mirror must re-read + reconcile.
	if err := emitManuscriptPartChanged(ctx, tx, bookID); err != nil {
		return nil, nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, nil, err
	}
	return prior, out, nil
}

// storeArchivePart soft-trashes an act and UN-HOMES its chapters (part_id = NULL —
// they survive in the flat manuscript), in ONE transaction. errPartNotFound if the
// active part is absent.
func (s *Server) storeArchivePart(ctx context.Context, bookID, partID uuid.UUID) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	var trashedID uuid.UUID
	err = tx.QueryRow(ctx, `
UPDATE parts SET lifecycle_state='trashed', trashed_at=now(), updated_at=now()
WHERE id=$1 AND book_id=$2 AND lifecycle_state='active'
RETURNING id`, partID, bookID).Scan(&trashedID)
	if errors.Is(err, pgx.ErrNoRows) {
		return errPartNotFound
	}
	if err != nil {
		return err
	}
	// Un-home this part's chapters — scoped by book_id AND part_id so it can never
	// touch another book's rows.
	if _, err := tx.Exec(ctx,
		`UPDATE chapters SET part_id=NULL, structure_node_id=NULL, updated_at=now() WHERE book_id=$1 AND part_id=$2`, bookID, partID); err != nil {
		return err
	}
	// C2 dual-write: the part is trashed + its chapters un-homed → the consumer archives the mirror
	// structure_node and clears its chapter membership.
	if err := emitManuscriptPartChanged(ctx, tx, bookID); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// storeRestorePart reactivates a soft-trashed act. Its chapters are NOT re-homed
// (restore is a non-magical inverse of trash — sealed). errPartNotFound if absent.
func (s *Server) storeRestorePart(ctx context.Context, bookID, partID uuid.UUID) (partView, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return partView{}, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck // no-op after Commit
	row := tx.QueryRow(ctx, `
UPDATE parts SET lifecycle_state='active', trashed_at=NULL, updated_at=now()
WHERE id=$1 AND book_id=$2 AND lifecycle_state='trashed'
RETURNING `+partSelectCols, partID, bookID)
	p, err := scanPart(row)
	if errors.Is(err, pgx.ErrNoRows) {
		return partView{}, errPartNotFound
	}
	if err != nil {
		return partView{}, err
	}
	// C2 dual-write: a restored part re-appears → the consumer re-creates/un-archives its mirror.
	// (Chapters are NOT re-homed — restore is a non-magical inverse — so structure_node_id stays as is.)
	if err := emitManuscriptPartChanged(ctx, tx, bookID); err != nil {
		return partView{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return partView{}, err
	}
	return p, nil
}

// moveChapterToPart sets chapters.part_id, verifying (a) the chapter is an active
// chapter of bookID, and (b) when partID != nil, the part is an ACTIVE part of the
// SAME book (tenancy: no cross-book move). errChapterNotFound / errPartNotInBook.
//
// Done in ONE transaction with FOR UPDATE on the target part: without it, a
// concurrent archivePart could trash the part BETWEEN the check and the write,
// leaving a chapter homed in a trashed act (TOCTOU). The lock serializes the two —
// if archive wins, the `lifecycle_state='active'` filter finds no row → errPartNotInBook.
func (s *Server) moveChapterToPart(ctx context.Context, bookID, chapterID uuid.UUID, partID *uuid.UUID) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx) //nolint:errcheck // no-op after Commit

	var exists bool
	if err := tx.QueryRow(ctx,
		`SELECT true FROM chapters WHERE id=$1 AND book_id=$2 AND lifecycle_state='active' FOR UPDATE`,
		chapterID, bookID).Scan(&exists); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return errChapterNotFound
		}
		return err
	}
	if partID != nil {
		var ok bool
		if err := tx.QueryRow(ctx,
			`SELECT true FROM parts WHERE id=$1 AND book_id=$2 AND lifecycle_state='active' FOR UPDATE`,
			*partID, bookID).Scan(&ok); err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				return errPartNotInBook
			}
			return err
		}
	}
	// C2 dual-write: structure_node_id mirrors part_id (structure_node.id == part.id), stamped in the
	// SAME txn — nothing reads it until C3, and it becomes the SSOT at C4 (part_id → structure_node_id
	// is then a pure rename). A nil partID (un-home) nulls both.
	if _, err := tx.Exec(ctx,
		`UPDATE chapters SET part_id=$3, structure_node_id=$3, updated_at=now() WHERE id=$1 AND book_id=$2`,
		chapterID, bookID, partID); err != nil {
		return err
	}
	if err := emitManuscriptPartChanged(ctx, tx, bookID); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// ═══════════════════════════════════════════════════════════════════════════
// REST routes — grant-gated (authBook), thin over the store methods.
// ═══════════════════════════════════════════════════════════════════════════

// GET /v1/books/{book_id}/parts — list active parts (?include_trashed=true adds trashed).
func (s *Server) listParts(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantView); !ok {
		return
	}
	where := `book_id=$1 AND lifecycle_state='active'`
	if r.URL.Query().Get("include_trashed") == "true" {
		where = `book_id=$1 AND lifecycle_state IN ('active','trashed')`
	}
	rows, err := s.pool.Query(r.Context(),
		`SELECT `+partSelectCols+` FROM parts WHERE `+where+` ORDER BY sort_order, id`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to list parts")
		return
	}
	defer rows.Close()
	items := make([]partView, 0)
	for rows.Next() {
		p, err := scanPart(rows)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to list parts")
			return
		}
		items = append(items, p)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to list parts")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

// POST /v1/books/{book_id}/parts — create an act (201).
func (s *Server) createPart(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	_, _, lifecycle, ok := s.authBook(w, r, bookID, GrantEdit)
	if !ok {
		return
	}
	if lifecycle != "active" {
		writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "parent book is not active")
		return
	}
	var in struct {
		Title string `json:"title"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	p, err := s.storeCreatePart(r.Context(), bookID, in.Title)
	if err != nil {
		writeError(w, http.StatusConflict, "BOOK_CONFLICT", "failed to create part")
		return
	}
	writeJSON(w, http.StatusCreated, p)
}

// PATCH /v1/books/{book_id}/parts/{part_id} — rename.
func (s *Server) renamePart(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	partID, ok := parseUUIDParam(w, r, "part_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantEdit); !ok {
		return
	}
	var in struct {
		Title string `json:"title"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	p, err := s.storeRenamePart(r.Context(), bookID, partID, in.Title)
	if errors.Is(err, errPartNotFound) {
		writeError(w, http.StatusNotFound, "PART_NOT_FOUND", "part not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to rename part")
		return
	}
	writeJSON(w, http.StatusOK, p)
}

// POST /v1/books/{book_id}/parts/reorder — body {ordered_ids:[uuid,...]}.
func (s *Server) reorderParts(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantEdit); !ok {
		return
	}
	var in struct {
		OrderedIDs []uuid.UUID `json:"ordered_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	if msg := validateOrderedIDs(in.OrderedIDs); msg != "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", msg)
		return
	}
	_, out, err := s.storeReorderParts(r.Context(), bookID, in.OrderedIDs)
	if errors.Is(err, errReorderMismatch) {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", errReorderMismatch.Error())
		return
	}
	if err != nil {
		writeError(w, http.StatusConflict, "BOOK_CONFLICT", "failed to reorder parts")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": out})
}

// validateOrderedIDs is the pure input check shared by REST + MCP: non-empty and no
// duplicate id (a permutation cannot repeat an element). "" = valid.
func validateOrderedIDs(ids []uuid.UUID) string {
	if len(ids) == 0 {
		return "ordered_ids is required"
	}
	seen := make(map[uuid.UUID]bool, len(ids))
	for _, id := range ids {
		if seen[id] {
			return "ordered_ids has a duplicate"
		}
		seen[id] = true
	}
	return ""
}

// DELETE /v1/books/{book_id}/parts/{part_id} — soft-trash (chapters → part_id NULL); 204.
func (s *Server) archivePart(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	partID, ok := parseUUIDParam(w, r, "part_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantEdit); !ok {
		return
	}
	err := s.storeArchivePart(r.Context(), bookID, partID)
	if errors.Is(err, errPartNotFound) {
		writeError(w, http.StatusNotFound, "PART_NOT_FOUND", "part not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to trash part")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// POST /v1/books/{book_id}/parts/{part_id}/restore — restore a trashed act.
func (s *Server) restorePart(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	partID, ok := parseUUIDParam(w, r, "part_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantEdit); !ok {
		return
	}
	p, err := s.storeRestorePart(r.Context(), bookID, partID)
	if errors.Is(err, errPartNotFound) {
		writeError(w, http.StatusNotFound, "PART_NOT_FOUND", "trashed part not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to restore part")
		return
	}
	writeJSON(w, http.StatusOK, p)
}

// PATCH /v1/books/{book_id}/chapters/{chapter_id}/part — move a chapter into/out of/
// between acts. Body {part_id: uuid|null}. Separate from patchChapter so the move is
// explicit/auditable and patchChapter's OCC contract is untouched.
func (s *Server) setChapterPart(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chapterID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantEdit); !ok {
		return
	}
	// Distinguish "field absent" (400) from "explicit null" (valid — un-home).
	raw := map[string]json.RawMessage{}
	if err := json.NewDecoder(r.Body).Decode(&raw); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	pv, present := raw["part_id"]
	if !present {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "part_id is required (use null to un-home)")
		return
	}
	var partID *uuid.UUID
	if string(pv) != "null" {
		var id uuid.UUID
		if err := json.Unmarshal(pv, &id); err != nil {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "part_id must be a UUID or null")
			return
		}
		partID = &id
	}

	if err := s.moveChapterToPart(r.Context(), bookID, chapterID, partID); err != nil {
		switch {
		case errors.Is(err, errChapterNotFound):
			writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		case errors.Is(err, errPartNotInBook):
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", errPartNotInBook.Error())
		default:
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to move chapter")
		}
		return
	}
	// Echo the resulting part_id so the caller sees the move without a re-read.
	s.getChapterByID(w, r.Context(), bookID, chapterID, uuid.Nil, http.StatusOK,
		map[string]any{"part_id": partID})
}

// getInternalPartsMirror — C-merge C2 dual-write. Returns a book's ACTIVE parts for composition's
// structure_node mirror consumer. Under /internal (X-Internal-Token); NO grant check — a trusted
// service call reconciling the mirror, not a user read. {parts:[{id,title,sort_order}]}. Removed at C4.
func (s *Server) getInternalPartsMirror(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	rows, err := s.pool.Query(r.Context(),
		`SELECT id, COALESCE(title,''), sort_order FROM parts
		 WHERE book_id=$1 AND lifecycle_state='active' ORDER BY sort_order, id`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to list parts mirror")
		return
	}
	defer rows.Close()
	type mirrorPart struct {
		ID        uuid.UUID `json:"id"`
		Title     string    `json:"title"`
		SortOrder int       `json:"sort_order"`
	}
	out := []mirrorPart{}
	for rows.Next() {
		var p mirrorPart
		if err := rows.Scan(&p.ID, &p.Title, &p.SortOrder); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to scan parts mirror")
			return
		}
		out = append(out, p)
	}
	writeJSON(w, http.StatusOK, map[string]any{"parts": out})
}

// postInternalPartsMirrorBackfill — C-merge C2. Emits one manuscript_part.changed per book that has
// ANY part, so composition backfills its structure_node mirror for parts created before C2. Idempotent
// (the consumer reconciles; re-running just re-reconciles). Invoked once at the C2 deploy and available
// as a manual drift re-sync. Under /internal (X-Internal-Token). Removed at C4.
func (s *Server) postInternalPartsMirrorBackfill(w http.ResponseWriter, r *http.Request) {
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "backfill begin failed")
		return
	}
	defer tx.Rollback(r.Context()) //nolint:errcheck
	// One book-level event per distinct book that owns a part (any lifecycle — a book with only
	// trashed parts still needs its mirror reconciled to archived).
	tag, err := tx.Exec(r.Context(), `
		INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
		SELECT 'book', book_id, $1, jsonb_build_object('book_id', book_id)
		FROM (SELECT DISTINCT book_id FROM parts) b`, ManuscriptPartChangedEvent)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "backfill emit failed")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "backfill commit failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"emitted": tag.RowsAffected()})
}
