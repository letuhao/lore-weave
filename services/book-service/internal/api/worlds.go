package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// ── C20 world container (book-service-only) ─────────────────────────────────
// A "world" groups books. Worlds are owner-scoped only (no collaborators — that
// is the per-book grant model, LOCKED-deferred for worlds). Lore (glossary/
// knowledge/composition) stays book_id/chapter_id-keyed and rolls up to a world
// via its books — there is NO world_id on any lore DB. On creation a world
// auto-provisions a hidden "world bible" chapter at sort_order 0 (is_bible) so
// the chapter-keyed lore machinery works prose-less (ARCH-REVIEW LOCK).

const bibleChapterTitle = "World Bible"

// bibleChapterFilename is the synthetic original_filename for the auto-created
// world-bible chapter. Deterministic per book so a re-provision attempt cannot
// fork a second filename (the sort_order-0 unique slot is the real guard).
func bibleChapterFilename(bookID uuid.UUID) string {
	return fmt.Sprintf("world-bible-%s.txt", bookID)
}

// worldNamePayload validates the create/patch body. name is required (trimmed
// non-empty); description is optional. Returns ok=false (caller 400s) on invalid.
type worldNamePayload struct {
	Name        string  `json:"name"`
	Description *string `json:"description"`
}

func decodeWorldPayload(r *http.Request) (worldNamePayload, bool) {
	var in worldNamePayload
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		return worldNamePayload{}, false
	}
	if strings.TrimSpace(in.Name) == "" {
		return worldNamePayload{}, false
	}
	return in, true
}

// createWorld provisions a world + its hidden bible book + a hidden sort_order-0
// bible chapter, all in one transaction (so a partial world without its lore
// anchor can never persist). Owner-scoped: owner_user_id is the JWT subject.
func (s *Server) createWorld(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	in, ok := decodeWorldPayload(r)
	if !ok {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "name is required")
		return
	}
	ctx := r.Context()
	if err := s.ensureQuotaRow(ctx, ownerID); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to initialize quota")
		return
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to create world")
		return
	}
	defer tx.Rollback(ctx)

	// world + hidden bible book + sort_order-0 bible chapter (shared with the
	// world_create MCP tool via createWorldCore, so both paths provision identically).
	worldID, _, _, err := s.createWorldCore(ctx, tx, ownerID, in.Name, in.Description)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to create world")
		return
	}

	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to commit world")
		return
	}
	s.getWorldByID(w, ctx, worldID, ownerID, http.StatusCreated)
}

// provisionBibleChapter inserts the hidden sort_order-0 world-bible chapter into
// bookID if (and only if) one does not already exist — IDEMPOTENT, so a
// re-provision (e.g. a retried create) never produces a second sort_order-0
// chapter. The INSERT ... WHERE NOT EXISTS guard plus the active unique slot
// index (book_id, sort_order, original_language) on sort_order 0 enforce the
// single-bible invariant. Returns the (existing or new) chapter id.
func provisionBibleChapter(ctx context.Context, tx pgx.Tx, bookID, _ uuid.UUID) (uuid.UUID, error) {
	// Fast path: a bible chapter already exists → no-op, return it.
	var existing uuid.UUID
	err := tx.QueryRow(ctx, `
SELECT id FROM chapters
WHERE book_id=$1 AND sort_order=0 AND is_bible=true AND lifecycle_state='active'
LIMIT 1
`, bookID).Scan(&existing)
	if err == nil {
		return existing, nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return uuid.Nil, err
	}

	jsonBody := plainTextToTiptapJSON("")
	var chapterID uuid.UUID
	// INSERT ... SELECT ... WHERE NOT EXISTS so two concurrent provisions cannot
	// both insert; the loser inserts zero rows and we re-select below.
	err = tx.QueryRow(ctx, `
INSERT INTO chapters(book_id,title,original_filename,original_language,content_type,byte_size,sort_order,storage_key,lifecycle_state,is_bible,editorial_status,draft_updated_at,updated_at)
SELECT $1,$2,$3,'und','text/plain',0,0,$4,'active',true,'draft',now(),now()
WHERE NOT EXISTS (
  SELECT 1 FROM chapters
  WHERE book_id=$1 AND sort_order=0 AND lifecycle_state='active'
)
RETURNING id
`, bookID, bibleChapterTitle, bibleChapterFilename(bookID), fmt.Sprintf("chapters/%s/bible", bookID)).Scan(&chapterID)
	if errors.Is(err, pgx.ErrNoRows) {
		// A concurrent insert won the slot; return the existing bible chapter.
		if e := tx.QueryRow(ctx, `
SELECT id FROM chapters
WHERE book_id=$1 AND sort_order=0 AND lifecycle_state='active'
LIMIT 1
`, bookID).Scan(&existing); e != nil {
			return uuid.Nil, e
		}
		return existing, nil
	}
	if err != nil {
		return uuid.Nil, err
	}
	if _, err := tx.Exec(ctx, `INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_updated_at, draft_version) VALUES($1,$2,'json',now(),1)`, chapterID, jsonBody); err != nil {
		return uuid.Nil, err
	}
	return chapterID, nil
}

func nullableDescription(d *string) any {
	if d == nil {
		return nil
	}
	return *d
}

// getWorldByID is a response-builder; callers MUST have established owner scope.
// The query is keyed by (id, owner_user_id) so a non-owner gets pgx.ErrNoRows →
// 404 (no existence oracle).
func (s *Server) getWorldByID(w http.ResponseWriter, ctx context.Context, worldID, ownerID uuid.UUID, status int) {
	var id, owner uuid.UUID
	var name string
	var desc *string
	var createdAt, updatedAt *time.Time
	var bookCount int
	var bibleBookID, bibleChapterID *uuid.UUID
	err := s.pool.QueryRow(ctx, worldSelectSQL+`
WHERE w.id=$1 AND w.owner_user_id=$2
`, worldID, ownerID).Scan(&id, &owner, &name, &desc, &createdAt, &updatedAt, &bookCount, &bibleBookID, &bibleChapterID)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "WORLD_NOT_FOUND", "world not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to get world")
		return
	}
	writeJSON(w, status, worldResponse(id, owner, name, desc, bookCount, bibleBookID, bibleChapterID, createdAt, updatedAt))
}

// worldSelectSQL is the shared projection for get/list. The two correlated
// subqueries resolve the world's hidden bible handle: bibleBook = the world's
// is_bible book; bibleChapter = that book's active sort_order-0 chapter. Both
// are LEFT-correlated (scalar subselect), so a legacy world with no bible book
// yields NULL → null in the FE contract rather than dropping the row. The
// chapter subselect re-derives the book id inline (not via the alias) so the
// projection stays a single self-contained SELECT list.
const worldSelectSQL = `
SELECT w.id, w.owner_user_id, w.name, w.description, w.created_at, w.updated_at,
  COALESCE((SELECT COUNT(*) FROM books b WHERE b.world_id=w.id AND b.is_bible=false AND b.lifecycle_state!='purge_pending'),0) AS book_count,
  (SELECT bb.id FROM books bb WHERE bb.world_id=w.id AND bb.is_bible=true ORDER BY bb.created_at ASC LIMIT 1) AS bible_book_id,
  (SELECT c.id FROM chapters c
     WHERE c.book_id=(SELECT bb.id FROM books bb WHERE bb.world_id=w.id AND bb.is_bible=true ORDER BY bb.created_at ASC LIMIT 1)
       AND c.sort_order=0 AND c.is_bible=true AND c.lifecycle_state='active'
     ORDER BY c.created_at ASC LIMIT 1) AS bible_chapter_id
FROM worlds w`

func worldResponse(id, owner uuid.UUID, name string, desc *string, bookCount int, bibleBookID, bibleChapterID *uuid.UUID, createdAt, updatedAt *time.Time) map[string]any {
	return map[string]any{
		"world_id":         id,
		"owner_user_id":    owner,
		"name":             name,
		"description":      desc,
		"book_count":       bookCount,
		"bible_book_id":    bibleBookID,
		"bible_chapter_id": bibleChapterID,
		"created_at":       createdAt,
		"updated_at":       updatedAt,
	}
}

func (s *Server) getWorld(w http.ResponseWriter, r *http.Request) {
	worldID, ok := parseUUIDParam(w, r, "world_id")
	if !ok {
		return
	}
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	s.getWorldByID(w, r.Context(), worldID, ownerID, http.StatusOK)
}

// listWorlds — owner-scoped list of the caller's worlds.
func (s *Server) listWorlds(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	limit, offset := parseLimitOffset(r)
	ctx := r.Context()
	rows, err := s.pool.Query(ctx, worldSelectSQL+`
WHERE w.owner_user_id=$1
ORDER BY w.created_at DESC
LIMIT $2 OFFSET $3
`, ownerID, limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to list worlds")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		var id, owner uuid.UUID
		var name string
		var desc *string
		var createdAt, updatedAt *time.Time
		var bookCount int
		var bibleBookID, bibleChapterID *uuid.UUID
		if err := rows.Scan(&id, &owner, &name, &desc, &createdAt, &updatedAt, &bookCount, &bibleBookID, &bibleChapterID); err == nil {
			items = append(items, worldResponse(id, owner, name, desc, bookCount, bibleBookID, bibleChapterID, createdAt, updatedAt))
		}
	}
	var total int
	_ = s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM worlds WHERE owner_user_id=$1`, ownerID).Scan(&total)
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total})
}

// patchWorld — owner-scoped update of name/description. The UPDATE is keyed by
// (id, owner_user_id) so a non-owner's patch affects zero rows → 404.
func (s *Server) patchWorld(w http.ResponseWriter, r *http.Request) {
	worldID, ok := parseUUIDParam(w, r, "world_id")
	if !ok {
		return
	}
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	var in map[string]any
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	setClauses := []string{"updated_at=now()"}
	args := []any{worldID, ownerID}
	paramIdx := 3
	if v, ok := in["name"]; ok {
		name, _ := v.(string)
		if strings.TrimSpace(name) == "" {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "name cannot be empty")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("name=$%d", paramIdx))
		args = append(args, name)
		paramIdx++
	}
	if _, ok := in["description"]; ok {
		setClauses = append(setClauses, fmt.Sprintf("description=$%d", paramIdx))
		args = append(args, stringFromAny(in["description"]))
		paramIdx++
	}
	query := fmt.Sprintf("UPDATE worlds SET %s WHERE id=$1 AND owner_user_id=$2", strings.Join(setClauses, ", "))
	ct, err := s.pool.Exec(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to patch world")
		return
	}
	if ct.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "WORLD_NOT_FOUND", "world not found")
		return
	}
	s.getWorldByID(w, r.Context(), worldID, ownerID, http.StatusOK)
}

// deleteWorld — owner-scoped delete. The FK `books.world_id ON DELETE SET NULL`
// returns member books to standalone (no cascade book delete). Keyed by
// (id, owner_user_id) so a non-owner's delete affects zero rows → 404.
func (s *Server) deleteWorld(w http.ResponseWriter, r *http.Request) {
	worldID, ok := parseUUIDParam(w, r, "world_id")
	if !ok {
		return
	}
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	// S-07 audit — route the world's hidden bible through purge_pending (not orphan it active).
	deleted, err := s.deleteWorldWithBiblePurge(r.Context(), worldID, ownerID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to delete world")
		return
	}
	if !deleted {
		writeError(w, http.StatusNotFound, "WORLD_NOT_FOUND", "world not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// requireWorldOwner resolves (caller owns world) for move-book / list-books.
// Returns ok=false with a written 401/404 on failure (no existence oracle).
func (s *Server) requireWorldOwner(w http.ResponseWriter, r *http.Request, worldID uuid.UUID) (uuid.UUID, bool) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return uuid.Nil, false
	}
	var exists bool
	err := s.pool.QueryRow(r.Context(), `SELECT EXISTS(SELECT 1 FROM worlds WHERE id=$1 AND owner_user_id=$2)`, worldID, ownerID).Scan(&exists)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "RESOLVE_FAILED", "world resolution failed")
		return uuid.Nil, false
	}
	if !exists {
		writeError(w, http.StatusNotFound, "WORLD_NOT_FOUND", "world not found")
		return uuid.Nil, false
	}
	return ownerID, true
}

// bookGrantError maps a resolved per-book grant level against the required tier
// to the uniform HTTP error a move/remove handler must emit, mirroring authBook:
//   - GrantNone           → 404 (missing book OR no grant; no existence oracle)
//   - below `need`        → 403 (caller has access but insufficient)
//   - otherwise           → status 0 (proceed)
//
// Pure (no pool/HTTP) so the route→need contract is unit-testable without a DB —
// the same testability gap grant_mapping_test.go closes for authBook.
func bookGrantError(lvl, need GrantLevel) (status int, code, message string) {
	if lvl == GrantNone {
		return http.StatusNotFound, "BOOK_NOT_FOUND", "book not found"
	}
	if !lvl.AtLeast(need) {
		return http.StatusForbidden, "BOOK_FORBIDDEN", "insufficient access"
	}
	return 0, "", ""
}

// moveBookIntoWorld — POST /v1/worlds/{world_id}/books {book_id}. Sets
// books.world_id. Requires world ownership AND edit grant on the book (so a
// collaborator-editor can group a book they can edit, but a stranger cannot).
func (s *Server) moveBookIntoWorld(w http.ResponseWriter, r *http.Request) {
	worldID, ok := parseUUIDParam(w, r, "world_id")
	if !ok {
		return
	}
	ownerID, ok := s.requireWorldOwner(w, r, worldID)
	if !ok {
		return
	}
	var in struct {
		BookID string `json:"book_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "book_id is required")
		return
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid book_id")
		return
	}
	// Grant gate on the book — reuse the per-book grant chokepoint (edit-tier).
	lvl, _, _, gerr := s.resolve(r.Context(), bookID, ownerID)
	if gerr != nil {
		writeError(w, http.StatusServiceUnavailable, "RESOLVE_FAILED", "grant resolution failed")
		return
	}
	if status, code, msg := bookGrantError(lvl, GrantEdit); status != 0 {
		writeError(w, status, code, msg)
		return
	}
	// is_bible=false guards against re-parenting an auto-created world-bible
	// container book — moving it would orphan its origin world's lore anchor.
	// A bible-book target falls through to the RowsAffected==0 → 404 below.
	// WS-1.2 · EGRESS (review-impl): a diary must never be moved into a world. A world can
	// be shared and its member books surface through world-scoped reads, so absorbing a
	// private diary into one is a share by the back door. `kind<>'diary'` (like is_bible)
	// makes a diary target fall through to the RowsAffected==0 → 404 below.
	ct, err := s.pool.Exec(r.Context(), `UPDATE books SET world_id=$1, updated_at=now() WHERE id=$2 AND is_bible=false AND kind<>'diary'`, worldID, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to move book")
		return
	}
	if ct.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"book_id": bookID, "world_id": worldID})
}

// removeBookFromWorld — DELETE /v1/worlds/{world_id}/books/{book_id}. Clears
// books.world_id (returns the book to standalone) only if it is currently in
// THIS world. Requires world ownership + edit grant on the book.
func (s *Server) removeBookFromWorld(w http.ResponseWriter, r *http.Request) {
	worldID, ok := parseUUIDParam(w, r, "world_id")
	if !ok {
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	ownerID, ok := s.requireWorldOwner(w, r, worldID)
	if !ok {
		return
	}
	lvl, _, _, gerr := s.resolve(r.Context(), bookID, ownerID)
	if gerr != nil {
		writeError(w, http.StatusServiceUnavailable, "RESOLVE_FAILED", "grant resolution failed")
		return
	}
	if status, code, msg := bookGrantError(lvl, GrantEdit); status != 0 {
		writeError(w, status, code, msg)
		return
	}
	// Only clear if the book is actually in this world (keyed by world_id) so a
	// stale/cross-world delete is a no-op rather than detaching from elsewhere.
	_, err := s.pool.Exec(r.Context(), `UPDATE books SET world_id=NULL, updated_at=now() WHERE id=$1 AND world_id=$2`, bookID, worldID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to remove book from world")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// listWorldBooks — GET /v1/worlds/{world_id}/books. Owner-scoped; lists books
// grouped into the world (world_id = the world). Standalone (world_id=NULL)
// books are necessarily excluded by the filter.
func (s *Server) listWorldBooks(w http.ResponseWriter, r *http.Request) {
	worldID, ok := parseUUIDParam(w, r, "world_id")
	if !ok {
		return
	}
	// Ownership is the gate; the list query is keyed by world_id so ownerID is
	// not needed past this point.
	if _, ok := s.requireWorldOwner(w, r, worldID); !ok {
		return
	}
	limit, offset := parseLimitOffset(r)
	ctx := r.Context()
	rows, err := s.pool.Query(ctx, `
SELECT b.id, b.owner_user_id, b.title, b.description, b.lifecycle_state, b.created_at, b.updated_at,
  COALESCE((SELECT COUNT(*) FROM chapters c WHERE c.book_id=b.id AND c.lifecycle_state='active' AND c.is_bible=false),0) AS chapter_count
FROM books b
WHERE b.world_id=$1 AND b.is_bible=false AND b.lifecycle_state!='purge_pending'
ORDER BY b.created_at DESC
LIMIT $2 OFFSET $3
`, worldID, limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to list world books")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		var id, owner uuid.UUID
		var title, state string
		var desc *string
		var createdAt, updatedAt *time.Time
		var chapterCount int
		if err := rows.Scan(&id, &owner, &title, &desc, &state, &createdAt, &updatedAt, &chapterCount); err == nil {
			items = append(items, map[string]any{
				"book_id":         id,
				"owner_user_id":   owner,
				"title":           title,
				"description":     desc,
				"lifecycle_state": state,
				"chapter_count":   chapterCount,
				"world_id":        worldID,
				"created_at":      createdAt,
				"updated_at":      updatedAt,
			})
		}
	}
	var total int
	_ = s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM books WHERE world_id=$1 AND is_bible=false AND lifecycle_state!='purge_pending'`, worldID).Scan(&total)
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total})
}

// internalListWorldBooks — GET /internal/worlds/{world_id}/books?user_id=. The
// service-to-service membership resolver for the knowledge-service world-rollup
// subgraph (W2 / G4). X-Internal-Token authed (the /internal group middleware);
// owner-scoped by the user_id QUERY PARAM (a trusted service call, not a JWT).
//
// The caller-supplied user_id MUST own the world or we 404 uniformly — without
// this parent-scope check the param would be a horizontal-escalation vector
// (read any world's membership). Returns the world's member books (is_bible
// excluded, same population as the public listWorldBooks); the consumer only
// needs the book ids to resolve each book's knowledge project.
func (s *Server) internalListWorldBooks(w http.ResponseWriter, r *http.Request) {
	worldID, ok := parseUUIDParam(w, r, "world_id")
	if !ok {
		return
	}
	userID, err := uuid.Parse(r.URL.Query().Get("user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BAD_USER_ID", "invalid user_id")
		return
	}
	var owned bool
	if err := s.pool.QueryRow(r.Context(),
		`SELECT EXISTS(SELECT 1 FROM worlds WHERE id=$1 AND owner_user_id=$2)`,
		worldID, userID,
	).Scan(&owned); err != nil {
		writeError(w, http.StatusServiceUnavailable, "RESOLVE_FAILED", "world resolution failed")
		return
	}
	if !owned {
		writeError(w, http.StatusNotFound, "WORLD_NOT_FOUND", "world not found")
		return
	}
	rows, err := s.pool.Query(r.Context(), `
SELECT b.id, b.owner_user_id, b.title, b.lifecycle_state
FROM books b
WHERE b.world_id=$1 AND b.is_bible=false AND b.lifecycle_state!='purge_pending'
ORDER BY b.created_at DESC
`, worldID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to list world books")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		var id, owner uuid.UUID
		var title, state string
		if err := rows.Scan(&id, &owner, &title, &state); err == nil {
			items = append(items, map[string]any{
				"book_id":         id,
				"owner_user_id":   owner,
				"title":           title,
				"lifecycle_state": state,
				"world_id":        worldID,
			})
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}
