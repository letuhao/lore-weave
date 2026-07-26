package api

import (
	"context"
	"net/http"

	"github.com/google/uuid"
)

// fold_handler.go — the canonical FOLD loop (F2-app, spec §12.1). The canonical is a lazy,
// versioned, regenerable CACHE over entity_facts (INV-FACTS): facts are SSOT; the prose
// canonical is derived. This is the glossary side of the loop (the LLM fold runs in the
// translation-service fold worker via provider-registry, mirroring the #26/#7 resummarize):
//
//   - markFoldDirty: a fact change flags the entity for re-fold (debounced — not per-fact-LLM).
//   - GET fold-dirty: the worker fetches dirty, non-quarantined entities + their bounded
//     current facts (the fold input) + a coverage fingerprint.
//   - POST fold-snapshot: the worker writes the folded prose; compare-and-clear (clear dirty
//     only if no fact arrived during the fold, C3) + RETRY_BUDGET backoff/quarantine (B4).
//   - GET canonical: returns the fresh head snapshot, else degrades to canon-content (the
//     entity is still readable — INV-FACTS guarantees it) and marks it dirty.

const foldRetryBudget = 3 // mirror the KG RETRY_BUDGET; after N fails → quarantine (B4)

// markFoldDirty flags an entity's narrative canonical for re-fold. isInvalidation bumps the
// re-ground counter (§12.1 B2 — invalidations are where incremental-refine most likely drops
// a superseded value). Best-effort within the caller's tx.
func markFoldDirty(ctx context.Context, q pgxRWQuerier, entityID uuid.UUID, isInvalidation bool) error {
	inc := 0
	if isInvalidation {
		inc = 1
	}
	_, err := q.Exec(ctx, `
		INSERT INTO canonical_fold_state (entity_id, attr_scope, dirty, invalidations_since_reground)
		VALUES ($1, 'narrative', true, $2)
		ON CONFLICT (entity_id, attr_scope) DO UPDATE
		  SET dirty = true,
		      invalidations_since_reground = canonical_fold_state.invalidations_since_reground + $2`,
		entityID, inc)
	return err
}

// internalFoldDirty — GET /internal/books/{book_id}/fold-dirty?limit=
// Dirty, non-quarantined entities + their bounded current single-valued facts (the fold input)
// + a coverage fingerprint (max coverage_xid) + the head ordinal.
func (s *Server) internalFoldDirty(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	limit := parseLimit(r.URL.Query().Get("limit"), 100, 500)
	rows, err := s.pool.Query(r.Context(), `
		WITH dirty AS (
		  SELECT cfs.entity_id
		  FROM canonical_fold_state cfs
		  JOIN glossary_entities ge ON ge.entity_id = cfs.entity_id
		  WHERE ge.book_id = $1 AND ge.deleted_at IS NULL
		    AND cfs.dirty = true AND cfs.fold_attempts < $3
		  ORDER BY cfs.entity_id
		  LIMIT $2
		)
		SELECT d.entity_id, ge.cached_name, ef.attr_or_predicate, ef.value,
		       max(ef.coverage_xid) OVER (PARTITION BY d.entity_id)::text, ef.valid_from_ordinal
		FROM dirty d
		JOIN glossary_entities ge ON ge.entity_id = d.entity_id
		JOIN entity_facts ef ON ef.entity_id = d.entity_id
		  AND ef.invalidated_at IS NULL AND ef.valid_to_ordinal IS NULL AND ef.cardinality = 'single'
		ORDER BY d.entity_id, ef.attr_or_predicate`, bookID, limit, foldRetryBudget)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "fold-dirty query failed")
		return
	}
	defer rows.Close()

	type foldFact struct {
		Attr  string `json:"attr"`
		Value string `json:"value"`
	}
	type foldItem struct {
		EntityID    string     `json:"entity_id"`
		EntityName  string     `json:"entity_name"`
		Facts       []foldFact `json:"facts"`
		HeadOrdinal int64      `json:"head_ordinal"`
		Fingerprint string     `json:"fold_fingerprint"`
	}
	order := []string{}
	byID := map[string]*foldItem{}
	for rows.Next() {
		var eid, name, attr, value, xid string
		var ord int64
		if err := rows.Scan(&eid, &name, &attr, &value, &xid, &ord); err != nil {
			continue
		}
		it, ok := byID[eid]
		if !ok {
			it = &foldItem{EntityID: eid, EntityName: name}
			byID[eid] = it
			order = append(order, eid)
		}
		it.Facts = append(it.Facts, foldFact{Attr: attr, Value: value})
		if ord > it.HeadOrdinal {
			it.HeadOrdinal = ord
		}
		// xid is the per-entity NUMERIC max(coverage_xid)::text (window agg), identical for
		// every row of the entity — so it round-trips byte-for-byte through the worker into
		// internalWriteFoldSnapshot's compare-and-clear, which recomputes the SAME numeric
		// max(coverage_xid)::text. (A lexical string-max would disagree on differing-length
		// values, e.g. "9" > "10", and wedge the entity in a perpetual re-fold livelock.)
		it.Fingerprint = xid
	}
	items := make([]*foldItem, 0, len(order))
	for _, id := range order {
		items = append(items, byID[id])
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

// internalWriteFoldSnapshot — POST /internal/books/{book_id}/entities/{entity_id}/fold-snapshot
// {content, as_of_ordinal, fold_algo_version, fold_fingerprint, failed}
func (s *Server) internalWriteFoldSnapshot(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	if !s.entityInBook(w, r, entityID, bookID) {
		return
	}
	var body struct {
		Content        string `json:"content"`
		AsOfOrdinal    int64  `json:"as_of_ordinal"`
		FoldAlgo       int    `json:"fold_algo_version"`
		FoldFingerprint string `json:"fold_fingerprint"`
		Failed         bool   `json:"failed"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	if body.FoldAlgo == 0 {
		body.FoldAlgo = 1
	}
	if body.Failed {
		// Backoff/quarantine (B4): bump attempts; after foldRetryBudget the dirty query skips it.
		if _, err := s.pool.Exec(r.Context(), `
			UPDATE canonical_fold_state
			   SET fold_attempts = fold_attempts + 1, fold_failed_at = now()
			 WHERE entity_id = $1 AND attr_scope = 'narrative'`, entityID); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "fold backoff failed")
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"status": "backoff"})
		return
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx begin failed")
		return
	}
	defer tx.Rollback(r.Context()) //nolint:errcheck
	if _, err := tx.Exec(r.Context(), `
		INSERT INTO canonical_snapshot
		  (entity_id, attr_scope, as_of_ordinal, content, fold_algo_version, fact_coverage_xid, canonical_status)
		VALUES ($1, 'narrative', $2, $3, $4, nullif($5,'')::xid8, 'current')
		ON CONFLICT (entity_id, attr_scope, as_of_ordinal, fold_algo_version)
		DO UPDATE SET content = EXCLUDED.content, fact_coverage_xid = EXCLUDED.fact_coverage_xid,
		              canonical_status = 'current', built_at = now()`,
		entityID, body.AsOfOrdinal, body.Content, body.FoldAlgo, body.FoldFingerprint); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "snapshot write failed: "+err.Error())
		return
	}
	// Compare-and-clear (C3): clear dirty ONLY if no fact arrived since the fold input was read
	// (current max coverage_xid == the folded fingerprint). Reset backoff; bump fold counter.
	if _, err := tx.Exec(r.Context(), `
		UPDATE canonical_fold_state cfs
		   SET dirty = COALESCE((
		         SELECT max(ef.coverage_xid)::text FROM entity_facts ef
		         WHERE ef.entity_id = cfs.entity_id AND ef.invalidated_at IS NULL
		       ), '') <> $2,
		       fold_attempts = 0, fold_failed_at = NULL, last_folded_at = now(),
		       folds_since_reground = cfs.folds_since_reground + 1
		 WHERE cfs.entity_id = $1 AND cfs.attr_scope = 'narrative'`,
		entityID, body.FoldFingerprint); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "compare-and-clear failed")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "folded"})
}

// internalGetCanonical — GET /internal/books/{book_id}/entities/{entity_id}/canonical?as_of=
// The KAL get_canonical target. Returns the fresh head snapshot; else degrades to the entity's
// canon-content (short_description) and marks it dirty for the next fold (degrade-safe, B4).
func (s *Server) internalGetCanonical(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	if !s.entityInBook(w, r, entityID, bookID) {
		return
	}
	// The newest head snapshot at the current fold algo, IF no fact with a newer coverage_xid
	// landed since it was built (else it's stale → rebuild-on-read = degrade now, re-fold later).
	var content string
	var asOf int64
	var status string
	err := s.pool.QueryRow(r.Context(), `
		SELECT cs.content, cs.as_of_ordinal, cs.canonical_status
		FROM canonical_snapshot cs
		WHERE cs.entity_id = $1 AND cs.attr_scope = 'narrative'
		  -- A snapshot with UNKNOWN coverage (NULL fingerprint) is STALE, not eternally fresh:
		  -- without this guard, ef.coverage_xid > NULL is always NULL → NOT EXISTS always true →
		  -- the snapshot would be served as current forever and never re-fold.
		  AND cs.fact_coverage_xid IS NOT NULL
		  AND NOT EXISTS (
		    SELECT 1 FROM entity_facts ef
		    WHERE ef.entity_id = cs.entity_id AND ef.invalidated_at IS NULL
		      AND ef.coverage_xid > cs.fact_coverage_xid
		  )
		ORDER BY cs.as_of_ordinal DESC, cs.built_at DESC
		LIMIT 1`, entityID).Scan(&content, &asOf, &status)
	if err == nil {
		writeJSON(w, http.StatusOK, map[string]any{
			"entity_id": entityID.String(), "content": content,
			"as_of_ordinal": asOf, "canonical_status": status, "source": "snapshot",
		})
		return
	}
	// Degrade: the existing canon-content (short_description) is a real, bounded canonical.
	var degraded *string
	_ = s.pool.QueryRow(r.Context(),
		`SELECT short_description FROM glossary_entities WHERE entity_id = $1 AND book_id = $2`,
		entityID, bookID).Scan(&degraded)
	_ = markFoldDirty(r.Context(), s.pool, entityID, false) // schedule a real fold
	body := ""
	if degraded != nil {
		body = *degraded
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"entity_id": entityID.String(), "content": body,
		"canonical_status": "stale", "source": "canon-content",
	})
}

// internalTriggerFold — POST /internal/books/{book_id}/entities/{entity_id}/fold
// The KAL fold_canonical target. Flags the entity's narrative canonical dirty so the next fold
// pass (the translation-service fold worker, LLM via provider-registry) regenerates it, and
// returns the entity's current snapshot status. The fold itself is async + decoupled (there is
// no LLM in glossary) — this is a "queue a re-fold" trigger, not a synchronous build.
func (s *Server) internalTriggerFold(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	if !s.entityInBook(w, r, entityID, bookID) {
		return
	}
	if err := markFoldDirty(r.Context(), s.pool, entityID, false); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "mark fold dirty failed")
		return
	}
	var status string
	_ = s.pool.QueryRow(r.Context(), `
		SELECT canonical_status FROM canonical_snapshot
		WHERE entity_id = $1 AND attr_scope = 'narrative'
		ORDER BY built_at DESC LIMIT 1`, entityID).Scan(&status)
	if status == "" {
		status = "pending" // no snapshot yet — the first fold will build it
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"entity_id": entityID.String(), "status": "queued", "canonical_status": status,
	})
}

// foldDirtyCount is a small probe used by tests.
func (s *Server) foldDirtyCount(ctx context.Context, bookID uuid.UUID) int {
	var n int
	_ = s.pool.QueryRow(ctx, `
		SELECT count(*) FROM canonical_fold_state cfs
		JOIN glossary_entities ge ON ge.entity_id = cfs.entity_id
		WHERE ge.book_id = $1 AND cfs.dirty = true`, bookID).Scan(&n)
	return n
}
