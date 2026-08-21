package api

import (
	"encoding/json"
	"net/http"

	"github.com/google/uuid"
)

type epubImportSceneMappingsRequest struct {
	Mappings []struct {
		ChapterID     uuid.UUID `json:"chapter_id"`
		SortOrder     int       `json:"sort_order"`
		OutlineNodeID uuid.UUID `json:"outline_node_id"`
	} `json:"mappings"`
}

// applyEPUBImportSceneMappings is the Book-owned write boundary for the
// Composition scene decompiler. The worker only forwards Composition's
// response; it never writes the Book database directly.
func (s *Server) applyEPUBImportSceneMappings(w http.ResponseWriter, r *http.Request) {
	jobID, ok := parseEPUBImportJobID(w, r)
	if !ok {
		return
	}
	var in epubImportSceneMappingsRequest
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || len(in.Mappings) == 0 {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "scene mappings are required")
		return
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to apply scene mappings")
		return
	}
	defer tx.Rollback(r.Context())
	var bookID uuid.UUID
	if err := tx.QueryRow(r.Context(), `SELECT book_id FROM import_jobs WHERE id=$1 AND pipeline_version=$2 FOR UPDATE`, jobID, epubImportPipelineVersion).Scan(&bookID); err != nil {
		writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "import job not found")
		return
	}
	changed := make(map[uuid.UUID]struct{})
	for _, mapping := range in.Mappings {
		if mapping.ChapterID == uuid.Nil || mapping.OutlineNodeID == uuid.Nil || mapping.SortOrder < 1 {
			writeError(w, http.StatusBadRequest, "INVALID_BODY", "scene mapping is invalid")
			return
		}
		result, err := tx.Exec(r.Context(), `
UPDATE scenes s SET source_scene_id=$4,updated_at=now()
FROM chapter_import_provenance p
WHERE p.import_job_id=$1 AND p.chapter_id=$2 AND s.chapter_id=p.chapter_id
  AND s.sort_order=$3 AND s.source_scene_id IS NULL
`, jobID, mapping.ChapterID, mapping.SortOrder, mapping.OutlineNodeID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to apply scene mapping")
			return
		}
		if result.RowsAffected() > 0 {
			changed[mapping.ChapterID] = struct{}{}
		}
	}
	for chapterID := range changed {
		if err := emitScenesLinked(r.Context(), tx, bookID, chapterID); err != nil {
			writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to publish scene mapping")
			return
		}
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to commit scene mappings")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"mapped_chapters": len(changed)})
}
