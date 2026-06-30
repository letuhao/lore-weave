package api

import (
	"net/http"
	"strconv"

	"github.com/google/uuid"
)

// facts_handler.go — the glossary /internal/facts/* HTTP surface (F4-live). It exposes the
// append-only bi-temporal fact SSOT (entity_facts) so the KAL (knowledge-gateway) can read
// and write it through one typed contract. Internal-token gated (the /internal router).
//
// Reads return bounded results matching contracts/api/knowledge-gateway/kal.v1.yaml. The
// half-open as-of predicate is the §12.3.1 lock: valid_from <= N AND (valid_to IS NULL OR N < valid_to).

type factDTO struct {
	FactID       string  `json:"fact_id"`
	EntityID     string  `json:"entity_id"`
	FactKind     string  `json:"fact_kind"`
	Attr         string  `json:"attr_or_predicate"`
	Value        string  `json:"value"`
	ValidFrom    int64   `json:"valid_from_ordinal"`
	ValidTo      *int64  `json:"valid_to_ordinal"`
	Cardinality  string  `json:"cardinality"`
	SourceEpisode *string `json:"source_episode_id"`
}

// internalGetFacts — GET /internal/books/{book_id}/entities/{entity_id}/facts?as_of=&attrs=
// Latest-valid (or valid-at-N) facts for an entity (current belief, invalidated_at IS NULL).
func (s *Server) internalGetFacts(w http.ResponseWriter, r *http.Request) {
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	asOf, hasAsOf := parseOptionalInt(r.URL.Query().Get("as_of"))
	args := []any{entityID}
	pred := "valid_to_ordinal IS NULL" // current head
	if hasAsOf {
		args = append(args, asOf)
		pred = "valid_from_ordinal <= $2 AND (valid_to_ordinal IS NULL OR $2 < valid_to_ordinal)"
	}
	rows, err := s.pool.Query(r.Context(), `
		SELECT fact_id, entity_id, fact_kind, attr_or_predicate, value, valid_from_ordinal,
		       valid_to_ordinal, cardinality, source_episode_id
		FROM entity_facts
		WHERE entity_id = $1 AND invalidated_at IS NULL AND `+pred+`
		ORDER BY attr_or_predicate, valid_from_ordinal DESC`, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "facts query failed")
		return
	}
	defer rows.Close()
	items := scanFacts(rows)
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

// internalFactTimeline — GET .../timeline?before_order=&after_order=&limit=
// The per-entity change feed (every fact version incl. invalidated), newest-first.
func (s *Server) internalFactTimeline(w http.ResponseWriter, r *http.Request) {
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	limit := parseLimit(r.URL.Query().Get("limit"), 50, 200)
	args := []any{entityID}
	where := "entity_id = $1"
	if before, ok := parseOptionalInt(r.URL.Query().Get("before_order")); ok {
		args = append(args, before)
		where += " AND valid_from_ordinal < $" + strconv.Itoa(len(args))
	}
	if after, ok := parseOptionalInt(r.URL.Query().Get("after_order")); ok {
		args = append(args, after)
		where += " AND valid_from_ordinal >= $" + strconv.Itoa(len(args))
	}
	args = append(args, limit)
	rows, err := s.pool.Query(r.Context(), `
		SELECT fact_id, entity_id, fact_kind, attr_or_predicate, value, valid_from_ordinal,
		       valid_to_ordinal, cardinality, source_episode_id
		FROM entity_facts
		WHERE `+where+`
		ORDER BY valid_from_ordinal DESC, created_at DESC
		LIMIT $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "timeline query failed")
		return
	}
	defer rows.Close()
	writeJSON(w, http.StatusOK, map[string]any{"items": scanFacts(rows)})
}

// internalListAttrValues — GET .../attr-values?attr=&as_of=
// Paginated STRUCTURED multi-valued facts for one attr (aliases/tags/appears_in, §12.5.3).
func (s *Server) internalListAttrValues(w http.ResponseWriter, r *http.Request) {
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	attr := r.URL.Query().Get("attr")
	if attr == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "attr query param required")
		return
	}
	args := []any{entityID, attr}
	pred := ""
	if asOf, ok := parseOptionalInt(r.URL.Query().Get("as_of")); ok {
		args = append(args, asOf)
		pred = " AND valid_from_ordinal <= $3 AND (valid_to_ordinal IS NULL OR $3 < valid_to_ordinal)"
	} else {
		pred = " AND valid_to_ordinal IS NULL"
	}
	rows, err := s.pool.Query(r.Context(), `
		SELECT fact_id, entity_id, fact_kind, attr_or_predicate, value, valid_from_ordinal,
		       valid_to_ordinal, cardinality, source_episode_id
		FROM entity_facts
		WHERE entity_id = $1 AND attr_or_predicate = $2 AND invalidated_at IS NULL`+pred+`
		ORDER BY value`, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "attr-values query failed")
		return
	}
	defer rows.Close()
	writeJSON(w, http.StatusOK, map[string]any{"items": scanFacts(rows)})
}

// ── writes ──────────────────────────────────────────────────────────────────

// internalIngestEpisode — POST .../facts/episode  {chapter_id, chapter_ordinal, content_hash, writeback_key}
func (s *Server) internalIngestEpisode(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	var body struct {
		ChapterID      string `json:"chapter_id"`
		ChapterOrdinal int64  `json:"chapter_ordinal"`
		ContentHash    string `json:"content_hash"`
		WritebackKey   string `json:"writeback_key"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	chapterID, err := uuid.Parse(body.ChapterID)
	if err != nil || body.ContentHash == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "chapter_id + content_hash required")
		return
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx begin failed")
		return
	}
	defer tx.Rollback(r.Context()) //nolint:errcheck
	epID, minted, err := ingestEpisode(r.Context(), tx, bookID, chapterID, body.ChapterOrdinal, body.ContentHash, body.WritebackKey)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "ingest episode failed: "+err.Error())
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"episode_id": epID.String(), "minted": minted})
}

// internalAppendFact — POST .../facts/append  (Path A append; idempotent)
func (s *Server) internalAppendFact(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	var body struct {
		EntityID        string `json:"entity_id"`
		FactKind        string `json:"fact_kind"`
		Attr            string `json:"attr_or_predicate"`
		Value           string `json:"value"`
		ValidFrom       int64  `json:"valid_from_ordinal"`
		Cardinality     string `json:"cardinality"`
		SourceEpisodeID string `json:"source_episode_id"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	entityID, err := uuid.Parse(body.EntityID)
	if err != nil || body.FactKind == "" || body.Attr == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "entity_id + fact_kind + attr_or_predicate required")
		return
	}
	var epPtr *uuid.UUID
	if body.SourceEpisodeID != "" {
		if ep, perr := uuid.Parse(body.SourceEpisodeID); perr == nil {
			epPtr = &ep
		}
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx begin failed")
		return
	}
	defer tx.Rollback(r.Context()) //nolint:errcheck
	if err := acquireFactChainLock(r.Context(), tx, entityID, body.Attr); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "chain lock failed")
		return
	}
	factID, inserted, err := appendFact(r.Context(), tx, appendFactParams{
		BookID: bookID, EntityID: entityID, FactKind: body.FactKind, Attr: body.Attr,
		Value: body.Value, ValidFrom: body.ValidFrom, Card: body.Cardinality, SourceEpisodeID: epPtr,
	})
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "append failed: "+err.Error())
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"fact_id": factID.String(), "inserted": inserted})
}

// internalRetractFacts — POST .../facts/retract  {fact_ids:[], reason}
func (s *Server) internalRetractFacts(w http.ResponseWriter, r *http.Request) {
	if _, ok := parsePathUUID(w, r, "book_id"); !ok {
		return
	}
	var body struct {
		FactIDs []string `json:"fact_ids"`
		Reason  string   `json:"reason"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	ids := make([]uuid.UUID, 0, len(body.FactIDs))
	for _, s := range body.FactIDs {
		if id, err := uuid.Parse(s); err == nil {
			ids = append(ids, id)
		}
	}
	reason := body.Reason
	if reason == "" {
		reason = "retract"
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx begin failed")
		return
	}
	defer tx.Rollback(r.Context()) //nolint:errcheck
	chains, err := retractFacts(r.Context(), tx, ids, reason)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "retract failed: "+err.Error())
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"retracted": len(ids), "chains_restitched": len(chains)})
}

// ── helpers ─────────────────────────────────────────────────────────────────

func scanFacts(rows interface {
	Next() bool
	Scan(...any) error
}) []factDTO {
	items := []factDTO{}
	for rows.Next() {
		var f factDTO
		var ep *uuid.UUID
		if err := rows.Scan(&f.FactID, &f.EntityID, &f.FactKind, &f.Attr, &f.Value,
			&f.ValidFrom, &f.ValidTo, &f.Cardinality, &ep); err != nil {
			continue
		}
		if ep != nil {
			s := ep.String()
			f.SourceEpisode = &s
		}
		items = append(items, f)
	}
	return items
}

func parseOptionalInt(s string) (int64, bool) {
	if s == "" {
		return 0, false
	}
	n, err := strconv.ParseInt(s, 10, 64)
	if err != nil {
		return 0, false
	}
	return n, true
}

func parseLimit(s string, def, max int) int {
	if s == "" {
		return def
	}
	n, err := strconv.Atoi(s)
	if err != nil || n <= 0 {
		return def
	}
	if n > max {
		return max
	}
	return n
}
