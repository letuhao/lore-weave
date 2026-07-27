package api

import (
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/google/uuid"
)

type entitiesByIDsRequest struct {
	EntityIDs []string `json:"entity_ids"`
	// Language (S6, optional): when set, each entity's aliases are augmented with its
	// per-language alias SET for that language (source ∪ target, deduped). Omitted →
	// source-language aliases only (back-compat).
	Language string `json:"language"`
	// IncludeAttributes (optional): also return each entity's authored attribute
	// values. Off by default — the semantic selector only needs identity, and this
	// endpoint sits on a hot path. knowledge-service sets it when building the
	// per-entity `:Passage` that lets the composition lore lens retrieve canon.
	IncludeAttributes bool `json:"include_attributes"`
}

type entitiesByIDsResponse struct {
	Items []glossaryEntityForContext `json:"items"`
}

type entityIDRow struct {
	EntityID string `json:"entity_id"`
	KindCode string `json:"kind_code"`
}

type entityIDsResponse struct {
	Items      []entityIDRow `json:"items"`
	NextOffset *int          `json:"next_offset"`
}

// internalEntityIDs enumerates EVERY alive entity of a book — the primitive for
// "index/sync all of it", which no internal route provided.
//
// Why not known-entities: that endpoint is the EXTRACTION ANCHOR list. It filters by
// chapter-mention frequency and resolves the display name from the attribute whose code
// is literally 'name' — so a kind that identifies itself differently (`terminology` uses
// `term`) yields an empty name and falls out. Using it to enumerate silently missed 2 of
// 14 entities on the live Mị Đế book while reporting a complete-looking count, which is
// the exact silent-cap failure an indexing pass must not have.
//
//	GET /internal/books/{book_id}/entity-ids?limit=&offset=
func (s *Server) internalEntityIDs(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	q := r.URL.Query()
	limit := queryInt(q.Get("limit"), 200)
	if limit > 500 {
		limit = 500
	}
	if limit < 1 {
		limit = 1
	}
	offset := queryInt(q.Get("offset"), 0)
	if offset < 0 {
		offset = 0
	}

	// Ordered by entity_id so paging is stable under concurrent writes.
	rows, err := s.pool.Query(r.Context(), `
		SELECT e.entity_id, k.code
		FROM glossary_entities e
		JOIN book_kinds k ON k.book_kind_id = e.kind_id
		WHERE e.book_id = $1 AND e.deleted_at IS NULL AND e.alive
		ORDER BY e.entity_id
		LIMIT $2 OFFSET $3`, bookID, limit+1, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "entity-ids query failed")
		return
	}
	defer rows.Close()

	items := []entityIDRow{}
	for rows.Next() {
		var id, kind string
		if err := rows.Scan(&id, &kind); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "entity-ids scan failed")
			return
		}
		items = append(items, entityIDRow{EntityID: id, KindCode: kind})
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "entity-ids rows error")
		return
	}

	// The +1 row is the lookahead: its presence means another page exists. Reported as
	// an explicit next_offset rather than left for the caller to infer from a full page.
	var next *int
	if len(items) > limit {
		items = items[:limit]
		n := offset + limit
		next = &n
	}
	writeJSON(w, http.StatusOK, entityIDsResponse{Items: items, NextOffset: next})
}

// internalEntitiesByIDs batch-fetches glossary entities by id in the SAME item
// shape as select-for-context (mui #4 — semantic retrieval, architecture B).
// The knowledge-service semantic selector resolves vector hits →
// glossary_entity_ids → this endpoint to enrich them with canon detail
// (cached_name/aliases/short_description/kind_code). Order is NOT significant —
// the caller re-ranks by its vector scores; tier/rank_score are left zero.
// Missing or soft-deleted ids are silently dropped (soft-absent, DI3).
//
//	POST /internal/books/{book_id}/entities/by-ids
//	body: { "entity_ids": ["…", …] }  →  { "items": [glossaryEntityForContext] }
func (s *Server) internalEntitiesByIDs(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}

	var req entitiesByIDsRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON body")
		return
	}

	// Parse + drop malformed ids (soft-absent). Empty → empty result, not error.
	ids := make([]uuid.UUID, 0, len(req.EntityIDs))
	for _, raw := range req.EntityIDs {
		if id, err := uuid.Parse(raw); err == nil {
			ids = append(ids, id)
		}
	}
	if len(ids) == 0 {
		writeJSON(w, http.StatusOK, entitiesByIDsResponse{Items: []glossaryEntityForContext{}})
		return
	}

	query := fmt.Sprintf(`
		SELECT %s
		FROM glossary_entities e
		JOIN book_kinds ek ON ek.book_kind_id = e.kind_id
		WHERE e.book_id = $1
		  AND e.deleted_at IS NULL
		  AND e.entity_id = ANY($2::uuid[])`, selectCols)
	rows, err := s.pool.Query(r.Context(), query, bookID, ids)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "by-ids query failed")
		return
	}
	defer rows.Close()

	items := []glossaryEntityForContext{}
	for rows.Next() {
		row, err := s.scanContextRow(rows, nil)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "by-ids scan failed")
			return
		}
		items = append(items, row)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "by-ids rows error")
		return
	}

	// S6: augment aliases with the requested language's alias set (best-effort).
	s.composePerLanguageAliases(r.Context(), bookID, items, req.Language)

	// Opt-in content fetch (best-effort, same posture).
	if req.IncludeAttributes {
		s.attachEntityAttributes(r.Context(), bookID, items)
	}

	writeJSON(w, http.StatusOK, entitiesByIDsResponse{Items: items})
}
