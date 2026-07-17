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
// Sealed decisions (docs/specs/2026-07-17-studio-completeness-build/01_DECISIONS.md):
//   - `path` is NOT NULL and import-oriented. A user-created act has no source path,
//     so we SYNTHESIZE one from the title (slugifyPartPath). Keeps the column
//     meaningful + non-null with no migration.
//   - NO OCC on parts — rename is low-contention, updated_at + last-write-wins is fine
//     (chapters keep their own draft OCC; this is the part LAYER only).
//   - Trashing a part UN-HOMES its chapters (part_id = NULL) — they survive in the
//     flat manuscript — it never cascade-deletes them. Restore does NOT re-home.
//
// Tenancy: parts are book_id-scoped; access is grant-gated through authBook (VIEW to
// read, EDIT to write) exactly like chapters. Every query is scoped by book_id. A
// move verifies the target part belongs to the SAME book (a cross-book move is a
// tenancy breach), so a chapter can never be re-homed into another tenant's book.
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

// partView is the JSON shape returned for a part. sort_order drives the manuscript
// act ordering; lifecycle_state is 'active' | 'trashed' (soft-delete, like chapters).
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

// slugifyPartPath turns a user-supplied act title into a stable, filesystem-ish
// path token so the NOT NULL `path` column stays meaningful for a user-created part
// (the import decomposer sets it from the source file; a Studio act has no file).
// Lowercases, keeps [a-z0-9], collapses every other run to a single '-', trims. If
// the title has no ASCII-alphanumerics at all (e.g. a purely CJK title), it yields
// "" and the caller falls back to "part-<sort_order>" — a slug is convenience, not
// identity (the id + (book_id, sort_order) are identity).
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

func scanPart(row pgx.Row) (partView, error) {
	var p partView
	err := row.Scan(&p.PartID, &p.BookID, &p.Title, &p.Path, &p.SortOrder, &p.LifecycleState, &p.CreatedAt, &p.UpdatedAt)
	return p, err
}

const partSelectCols = `id, book_id, title, path, sort_order, lifecycle_state, created_at, updated_at`

// ── GET /v1/books/{book_id}/parts ────────────────────────────────────────────
// Lists a book's parts (acts) in sort order. Active only by default;
// ?include_trashed=true also returns soft-trashed ones (for a restore UI).
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

// ── POST /v1/books/{book_id}/parts ───────────────────────────────────────────
// Creates an act at the end of the book's part sequence. sort_order = MAX+1;
// path is synthesized from the title. A racing create can collide on the
// UNIQUE(book_id, sort_order) slot — retry once (a second racer just takes MAX+2).
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
	title := strings.TrimSpace(in.Title)

	var p partView
	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		row := s.pool.QueryRow(r.Context(), `
INSERT INTO parts(book_id, sort_order, title, path)
VALUES(
  $1,
  (SELECT COALESCE(MAX(sort_order),0)+1 FROM parts WHERE book_id=$1),
  $2,
  $3
)
RETURNING `+partSelectCols,
			bookID, nullIfEmpty(title), partPath(title, 0))
		p, lastErr = scanPart(row)
		if lastErr == nil {
			// Backfill a slug that couldn't know its sort_order at INSERT time (CJK
			// title → empty slug → "part-<n>"). Cheap single-row update, only when needed.
			if p.Path == "" {
				fallback := partPath(title, p.SortOrder)
				if _, err := s.pool.Exec(r.Context(),
					`UPDATE parts SET path=$3 WHERE id=$1 AND book_id=$2`, p.PartID, bookID, fallback); err == nil {
					p.Path = fallback
				}
			}
			writeJSON(w, http.StatusCreated, p)
			return
		}
		// Only a (book_id, sort_order) unique collision is retryable; anything else is fatal.
		if !isUniqueViolation(lastErr) {
			break
		}
	}
	writeError(w, http.StatusConflict, "BOOK_CONFLICT", "failed to create part")
}

// partPath returns slugify(title), or "part-<sort_order>" when the title yields no
// usable slug (empty/CJK). sortOrder=0 signals "unknown yet" → the caller decides.
func partPath(title string, sortOrder int) string {
	if s := slugifyPartPath(title); s != "" {
		return s
	}
	if sortOrder > 0 {
		return "part-" + strconv.Itoa(sortOrder)
	}
	return "" // caller backfills once sort_order is known
}

// ── PATCH /v1/books/{book_id}/parts/{part_id} ────────────────────────────────
// Renames an act. Last-write-wins (no OCC — sealed). Only `title` is mutable here;
// reorder + lifecycle have their own routes so each write is explicit + auditable.
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
	row := s.pool.QueryRow(r.Context(), `
UPDATE parts SET title=$3, updated_at=now()
WHERE id=$1 AND book_id=$2 AND lifecycle_state='active'
RETURNING `+partSelectCols,
		partID, bookID, nullIfEmpty(strings.TrimSpace(in.Title)))
	p, err := scanPart(row)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "PART_NOT_FOUND", "part not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to rename part")
		return
	}
	writeJSON(w, http.StatusOK, p)
}

// ── POST /v1/books/{book_id}/parts/reorder ───────────────────────────────────
// Rewrites the whole part ordering. Body: {ordered_ids:[uuid,...]} — the exact set
// of the book's ACTIVE parts, in the new order. Two-phase negate/rewrite (same
// trick as reorderChapters) because UNIQUE(book_id, sort_order) is checked per row,
// so an intermediate permutation state would collide. FOR UPDATE serializes racing
// reorders. A subset/superset/foreign id is a 400 (never a partial reorder).
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
	if len(in.OrderedIDs) == 0 {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "ordered_ids is required")
		return
	}
	// Reject a duplicate id up front (a permutation cannot repeat an element).
	seen := make(map[uuid.UUID]bool, len(in.OrderedIDs))
	for _, id := range in.OrderedIDs {
		if seen[id] {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "ordered_ids has a duplicate")
			return
		}
		seen[id] = true
	}

	ctx := r.Context()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to reorder parts")
		return
	}
	defer tx.Rollback(ctx) //nolint:errcheck // no-op after Commit

	// Load the book's active parts FOR UPDATE (serializes concurrent reorders).
	rows, err := tx.Query(ctx,
		`SELECT id FROM parts WHERE book_id=$1 AND lifecycle_state='active' ORDER BY sort_order, id FOR UPDATE`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to reorder parts")
		return
	}
	existing := make(map[uuid.UUID]bool)
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			rows.Close()
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to reorder parts")
			return
		}
		existing[id] = true
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to reorder parts")
		return
	}
	// ordered_ids must be EXACTLY the active set — same size and every id present.
	if len(in.OrderedIDs) != len(existing) {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR",
			"ordered_ids must list every active part of this book exactly once")
		return
	}
	for _, id := range in.OrderedIDs {
		if !existing[id] {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR",
				"ordered_ids contains a part that is not an active part of this book")
			return
		}
	}

	// Phase 1: park every active slot in the negative space (positive → negative;
	// disjoint from the target positives, so the per-row unique check never trips).
	if _, err := tx.Exec(ctx,
		`UPDATE parts SET sort_order = -sort_order - 1 WHERE book_id=$1 AND lifecycle_state='active'`, bookID); err != nil {
		writeError(w, http.StatusConflict, "BOOK_CONFLICT", "failed to reorder parts")
		return
	}
	// Phase 2: write the dense 1..N sequence (negative → positive; disjoint again).
	out := make([]partView, 0, len(in.OrderedIDs))
	for i, id := range in.OrderedIDs {
		row := tx.QueryRow(ctx, `
UPDATE parts SET sort_order=$3, updated_at=now()
WHERE id=$1 AND book_id=$2
RETURNING `+partSelectCols, id, bookID, i+1)
		p, err := scanPart(row)
		if err != nil {
			writeError(w, http.StatusConflict, "BOOK_CONFLICT", "failed to reorder parts")
			return
		}
		out = append(out, p)
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusConflict, "BOOK_CONFLICT", "failed to reorder parts")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": out})
}

// ── DELETE /v1/books/{book_id}/parts/{part_id} ───────────────────────────────
// Soft-trashes an act. Its chapters are NOT deleted — they are UN-HOMED
// (part_id = NULL) so they fall back to the flat manuscript. One transaction so a
// part is never trashed while its chapters still point at it.
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
	ctx := r.Context()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to trash part")
		return
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	var trashedID uuid.UUID
	err = tx.QueryRow(ctx, `
UPDATE parts SET lifecycle_state='trashed', trashed_at=now(), updated_at=now()
WHERE id=$1 AND book_id=$2 AND lifecycle_state='active'
RETURNING id`, partID, bookID).Scan(&trashedID)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "PART_NOT_FOUND", "part not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to trash part")
		return
	}
	// Un-home this part's chapters (they survive in the flat manuscript). Scoped by
	// book_id AND part_id so it can never touch another book's rows.
	if _, err := tx.Exec(ctx,
		`UPDATE chapters SET part_id=NULL, updated_at=now() WHERE book_id=$1 AND part_id=$2`, bookID, partID); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to un-home chapters")
		return
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to trash part")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// ── POST /v1/books/{book_id}/parts/{part_id}/restore ─────────────────────────
// Restores a soft-trashed act. Its chapters are NOT re-homed — restore is a
// non-magical inverse of trash (an explicit choice, sealed): the user re-homes
// chapters deliberately via the move route.
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
	row := s.pool.QueryRow(r.Context(), `
UPDATE parts SET lifecycle_state='active', trashed_at=NULL, updated_at=now()
WHERE id=$1 AND book_id=$2 AND lifecycle_state='trashed'
RETURNING `+partSelectCols, partID, bookID)
	p, err := scanPart(row)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "PART_NOT_FOUND", "trashed part not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to restore part")
		return
	}
	writeJSON(w, http.StatusOK, p)
}

// ── PATCH /v1/books/{book_id}/chapters/{chapter_id}/part ──────────────────────
// Moves a chapter into / out of / between acts. Body: {part_id: uuid|null}.
// null un-homes it (flat manuscript). Deliberately SEPARATE from patchChapter so
// the move is explicit/auditable and patchChapter's OCC contract is untouched.
// A non-null target part must belong to the SAME book (cross-book move = tenancy
// breach) AND be active. No id churn, no re-embed — only chapters.part_id changes.
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
	// Distinguish "field absent" from "explicit null": both are valid (null = un-home),
	// but an absent field is a malformed request. Use a pointer-to-pointer sentinel.
	var in struct {
		PartID *uuid.UUID `json:"part_id"`
	}
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
	if string(pv) != "null" {
		var id uuid.UUID
		if err := json.Unmarshal(pv, &id); err != nil {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "part_id must be a UUID or null")
			return
		}
		in.PartID = &id
	}

	if err := s.moveChapterToPart(r.Context(), bookID, chapterID, in.PartID); err != nil {
		switch {
		case errors.Is(err, errChapterNotFound):
			writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		case errors.Is(err, errPartNotInBook):
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR",
				"target part is not an active part of this book")
		default:
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to move chapter")
		}
		return
	}
	// Echo the resulting part_id so the caller sees the move without a re-read.
	s.getChapterByID(w, r.Context(), bookID, chapterID, uuid.Nil, http.StatusOK,
		map[string]any{"part_id": in.PartID})
}

// errChapterNotFound is declared in server.go (shared chapter sentinel). This file
// adds only the part-move-specific one.
var errPartNotInBook = errors.New("target part is not an active part of this book")

// moveChapterToPart sets chapters.part_id, verifying (a) the chapter is an active
// chapter of bookID, and (b) when partID != nil, the part is an ACTIVE part of the
// SAME book. Shared by the REST route and the MCP tool (book_chapter_set_part).
func (s *Server) moveChapterToPart(ctx context.Context, bookID, chapterID uuid.UUID, partID *uuid.UUID) error {
	// Guard the chapter exists in this book (active). A missing chapter must 404,
	// not silently no-op.
	var exists bool
	if err := s.pool.QueryRow(ctx,
		`SELECT true FROM chapters WHERE id=$1 AND book_id=$2 AND lifecycle_state='active'`,
		chapterID, bookID).Scan(&exists); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return errChapterNotFound
		}
		return err
	}
	// A non-null target must be an active part of THIS book (tenancy: no cross-book move).
	if partID != nil {
		var ok bool
		if err := s.pool.QueryRow(ctx,
			`SELECT true FROM parts WHERE id=$1 AND book_id=$2 AND lifecycle_state='active'`,
			*partID, bookID).Scan(&ok); err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				return errPartNotInBook
			}
			return err
		}
	}
	_, err := s.pool.Exec(ctx,
		`UPDATE chapters SET part_id=$3, updated_at=now() WHERE id=$1 AND book_id=$2`,
		chapterID, bookID, partID)
	return err
}
