package api

import (
	"encoding/json"
	"net/http"

	"github.com/google/uuid"
)

// ── M7 backfill — deterministic per-chapter mention_count recount (no LLM) ───────
//
// The producer (translation-service) holds chapter text + the matcher, so it computes
// the recounted per-(entity,chapter) frequencies and POSTs them here for a targeted,
// idempotent UPDATE. This endpoint does NOT re-run entity resolution or extraction — it
// only writes mention_count onto EXISTING chapter_entity_links rows, so it is cheap and
// safe to re-run. Book-scoped (the UPDATE joins glossary_entities and filters book_id) so
// a stray (entity,chapter) from another tenant's book can't be touched.
//
//	POST /internal/books/{book_id}/recount-mention-counts
//	  body: { "counts": [ { "entity_id": uuid, "chapter_id": uuid, "mention_count": int }, ... ] }
//	  → 200 { "updated": int }

type recountItem struct {
	EntityID     string `json:"entity_id"`
	ChapterID    string `json:"chapter_id"`
	MentionCount int    `json:"mention_count"`
}

type recountRequest struct {
	Counts []recountItem `json:"counts"`
}

// internalRecountMentionCounts applies a batch of per-(entity,chapter) mention_count
// updates for a book. Internal-token gated (registered under the /internal group).
func (s *Server) internalRecountMentionCounts(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	var req recountRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	if len(req.Counts) == 0 {
		writeJSON(w, http.StatusOK, map[string]int{"updated": 0})
		return
	}

	ctx := r.Context()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx begin failed")
		return
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	updated := 0
	for _, it := range req.Counts {
		entID, err1 := uuid.Parse(it.EntityID)
		chID, err2 := uuid.Parse(it.ChapterID)
		if err1 != nil || err2 != nil || it.MentionCount < 0 {
			continue // skip malformed rows rather than poison the batch
		}
		// Book-scoped UPDATE: the link's entity must belong to THIS book. A no-op match
		// (already at this value, or no such link) affects 0 rows — idempotent.
		tag, err := tx.Exec(ctx, `
			UPDATE chapter_entity_links cel
			   SET mention_count = $3
			  FROM glossary_entities e
			 WHERE cel.entity_id = $1
			   AND cel.chapter_id = $2
			   AND e.entity_id = cel.entity_id
			   AND e.book_id = $4`,
			entID, chID, it.MentionCount, bookID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "recount update failed: "+err.Error())
			return
		}
		updated += int(tag.RowsAffected())
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx commit failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]int{"updated": updated})
}
