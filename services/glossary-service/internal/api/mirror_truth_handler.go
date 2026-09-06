package api

import (
	"net/http"
)

// The truth side of the glossary→KG mirror reconciliation
// (D-GLOSSARY-KG-MIRROR-HAS-NO-RECONCILER).
//
// The glossary is the SSOT and the KG is its projection, delivered at-least-once through
// the outbox with NO reconciliation: an event lost while a handler was broken is lost
// permanently, because nothing compares the two stores. Live-measured on the acceptance
// book: 26 of 43 entities present in the KG, 17 absent, and no check anywhere reports it.
//
// This endpoint is the enumeration a detector anti-joins against. It deliberately does NOT
// decide what "should be mirrored" — that predicate belongs to the CONSUMER (knowledge-
// service skips an event whose name or kind is empty), so this reports `has_name` and lets
// the consumer apply its own rule. What it does own is the question only this service can
// answer: which rows does the emit path consider to exist at all.
//
//	GET /internal/books/{book_id}/mirror-truth-ids?limit=&offset=
//
// Paging mirrors `entity-ids`: ordered by entity_id (stable under concurrent writes),
// peek-ahead +1 row, and an explicit `next_offset` rather than a full page the caller has
// to infer from — a silent cap here would under-report the divergence, which is the one
// failure mode a detector must not have.
type mirrorTruthRow struct {
	EntityID string `json:"entity_id"`
	KindCode string `json:"kind_code"`
	// HasName is the emit payload's `name` being non-empty — reported rather than
	// filtered on. A freshly-created draft emits before its name attribute is filled,
	// and knowledge-service's handler skips that event BY DESIGN until a populated one
	// arrives. A detector that could not tell "absent because lost" from "absent
	// because not yet nameable" would alarm forever on rows that are correct.
	HasName bool `json:"has_name"`
}

type mirrorTruthResponse struct {
	Items      []mirrorTruthRow `json:"items"`
	NextOffset *int             `json:"next_offset"`
}

// mirrorTruthIDsSQL is built from mirrorTruthPredicate (outbox.go) — the SAME fragment the
// emit-side read uses. See the comment on that constant for why a narrower proxy is a bug.
const mirrorTruthIDsSQL = `
		SELECT e.entity_id, k.code, (COALESCE(e.cached_name, '') <> '') AS has_name
		FROM glossary_entities e
		JOIN book_kinds k ON k.book_kind_id = e.kind_id
		WHERE e.book_id = $1 AND ` + mirrorTruthPredicate + `
		ORDER BY e.entity_id
		LIMIT $2 OFFSET $3`

func (s *Server) internalMirrorTruthIDs(w http.ResponseWriter, r *http.Request) {
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

	rows, err := s.pool.Query(r.Context(), mirrorTruthIDsSQL, bookID, limit+1, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL",
			"mirror-truth-ids query failed")
		return
	}
	defer rows.Close()

	items := []mirrorTruthRow{}
	for rows.Next() {
		var row mirrorTruthRow
		if err := rows.Scan(&row.EntityID, &row.KindCode, &row.HasName); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL",
				"mirror-truth-ids scan failed")
			return
		}
		items = append(items, row)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL",
			"mirror-truth-ids rows error")
		return
	}

	var next *int
	if len(items) > limit {
		items = items[:limit]
		n := offset + limit
		next = &n
	}
	writeJSON(w, http.StatusOK, mirrorTruthResponse{Items: items, NextOffset: next})
}
