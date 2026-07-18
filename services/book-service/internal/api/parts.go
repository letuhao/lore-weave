package api

// C-merge C4 — after the Parts→Arcs merge, manuscript "parts" live in composition
// (structure_node kind='part'): part CRUD (create/rename/reorder/archive/restore) is served by
// composition (arc.py), read by the Manuscript rail from GET /v1/composition/books/{id}/parts.
//
// book-service keeps ONLY the chapter→part ASSIGNMENT, because a chapter's grouping is a book-service
// chapter column (chapters.structure_node_id — the surviving link after the C4 drop of part_id). The
// part's existence/tenancy is composition's concern; book-service just records which structure node a
// chapter belongs to (or NULL to un-home).
import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	"github.com/google/uuid"
)

// moveChapterToPart sets chapters.structure_node_id — the chapter's manuscript grouping (a composition
// structure_node kind='part' id, or NULL to un-home). Validates the chapter is an ACTIVE chapter of
// bookID (tenancy). No parts-table lookup exists after C4; the FE passes an id from the book's parts
// list (composition), and archiving that part composition-side simply drops the chapter to Unassigned
// via the grouping read filter.
func (s *Server) moveChapterToPart(ctx context.Context, bookID, chapterID uuid.UUID, structureNodeID *uuid.UUID) error {
	ct, err := s.pool.Exec(ctx,
		`UPDATE chapters SET structure_node_id=$3, updated_at=now()
		 WHERE id=$1 AND book_id=$2 AND lifecycle_state='active'`,
		chapterID, bookID, structureNodeID)
	if err != nil {
		return err
	}
	if ct.RowsAffected() == 0 {
		return errChapterNotFound
	}
	return nil
}

// setChapterPart — PATCH /v1/books/{book_id}/chapters/{chapter_id}/part. Assign a chapter to a
// manuscript part (a composition structure_node kind='part' id) or un-home it (part_id: null). The
// body/echo key stays `part_id` for FE compatibility; it now carries a structure_node id.
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
	var structureNodeID *uuid.UUID
	if string(pv) != "null" {
		var id uuid.UUID
		if err := json.Unmarshal(pv, &id); err != nil {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "part_id must be a UUID or null")
			return
		}
		structureNodeID = &id
	}

	if err := s.moveChapterToPart(r.Context(), bookID, chapterID, structureNodeID); err != nil {
		switch {
		case errors.Is(err, errChapterNotFound):
			writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		default:
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to move chapter")
		}
		return
	}
	// Echo the resulting structure_node_id under the `part_id` key so the caller sees the move.
	s.getChapterByID(w, r.Context(), bookID, chapterID, uuid.Nil, http.StatusOK)
}
