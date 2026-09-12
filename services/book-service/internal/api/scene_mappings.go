package api

import (
	"encoding/json"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

// T7 — the book-scoped sibling of applyEPUBImportSceneMappings.
//
// `scenes.source_scene_id` is the SOLE trigger for the whole written_* chain: it is what makes
// composition emit `chapter.scenes_linked`, which is what reconciles `outline_node.written_*`,
// which is what the Plan Hub's "written" badge reads. Composition's scene decompiler has always
// COMPUTED the back-link mappings — `scene_decompile.py` even documents the write-back as
// idempotent-on-retry ("a retry after a failed write-back returns the SAME mappings") and names
// the owner ("the index owner writes scenes.source_scene_id") — but only the EPUB import path
// ever consumed them. The Plan Hub's "Extract the plan" CTA returned them to a browser that threw
// them away, so a human-authored book could never light up that chain at all.
//
// Why a new endpoint rather than reusing the EPUB one: that route is keyed by an import job and
// joins `chapter_import_provenance` to scope its writes. A Hub extraction has no import job. The
// scoping here is the book itself, which is why the path carries {book_id}.
//
// Why book-service owns this write at all (and composition does not reach across): `scenes` is
// book-service's table. Same reason the EPUB path routes through here rather than letting the
// worker write directly — its own comment: "The worker only forwards Composition's response; it
// never writes the Book database directly."
type sceneMappingsRequest struct {
	// OwnerUserID is the user the caller asserts this write is for. The internal token
	// authenticates the CALLER (composition-service), it does not authorize the ACTION —
	// composition grant-checks EDIT before calling, and re-asserting the owner here keeps that
	// decision auditable at the write boundary.
	OwnerUserID uuid.UUID `json:"owner_user_id"`
	Mappings    []struct {
		ChapterID     uuid.UUID `json:"chapter_id"`
		SortOrder     int       `json:"sort_order"`
		OutlineNodeID uuid.UUID `json:"outline_node_id"`
	} `json:"mappings"`
}

type sceneMappingsResponse struct {
	Linked  int `json:"linked"`
	Skipped int `json:"skipped"`
}

func (s *Server) applyBookSceneMappings(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_BOOK_ID", "book_id must be a UUID")
		return
	}
	var in sceneMappingsRequest
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || len(in.Mappings) == 0 {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "scene mappings are required")
		return
	}
	if in.OwnerUserID == uuid.Nil {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "owner_user_id is required")
		return
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "SCENE_MAPPING_ERROR", "failed to apply scene mappings")
		return
	}
	defer tx.Rollback(r.Context())

	// Fail closed if the asserted owner does not actually own the book. Composition has already
	// grant-checked, so a mismatch here means the two services disagree about who this is —
	// which is exactly when a silent write would be worst.
	var ownerID uuid.UUID
	if err := tx.QueryRow(r.Context(), `SELECT owner_user_id FROM books WHERE id=$1 FOR UPDATE`, bookID).Scan(&ownerID); err != nil {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if ownerID != in.OwnerUserID {
		writeError(w, http.StatusForbidden, "BOOK_NOT_OWNED", "this book belongs to a different owner")
		return
	}

	linked := 0
	changed := make(map[uuid.UUID]struct{})
	for _, mapping := range in.Mappings {
		if mapping.ChapterID == uuid.Nil || mapping.OutlineNodeID == uuid.Nil || mapping.SortOrder < 1 {
			writeError(w, http.StatusBadRequest, "INVALID_BODY", "scene mapping is invalid")
			return
		}
		// `source_scene_id IS NULL` makes this idempotent AND non-destructive: a re-run relinks
		// nothing, and an author's existing link is never overwritten by a later extraction.
		// The chapter is constrained to THIS book so a caller cannot reach another book's scenes.
		result, err := tx.Exec(r.Context(), `
UPDATE scenes s SET source_scene_id=$3,updated_at=now()
FROM chapters c
WHERE c.id = s.chapter_id AND c.book_id = $1
  AND s.chapter_id = $2 AND s.sort_order = $4 AND s.source_scene_id IS NULL
`, bookID, mapping.ChapterID, mapping.OutlineNodeID, mapping.SortOrder)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "SCENE_MAPPING_ERROR", "failed to apply scene mapping")
			return
		}
		if result.RowsAffected() > 0 {
			linked += int(result.RowsAffected())
			changed[mapping.ChapterID] = struct{}{}
		}
	}

	// The event is the whole point: without it the columns change and nothing downstream notices.
	// Emitted per touched chapter, inside the same transaction as the writes.
	for chapterID := range changed {
		if err := emitScenesLinked(r.Context(), tx, bookID, chapterID); err != nil {
			writeError(w, http.StatusInternalServerError, "SCENE_MAPPING_ERROR", "failed to publish scene mapping")
			return
		}
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "SCENE_MAPPING_ERROR", "failed to commit scene mappings")
		return
	}

	writeJSON(w, http.StatusOK, sceneMappingsResponse{
		Linked:  linked,
		Skipped: len(in.Mappings) - linked,
	})
}
