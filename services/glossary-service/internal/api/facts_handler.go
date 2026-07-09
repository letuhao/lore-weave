package api

import (
	"errors"
	"net/http"
	"strconv"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
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
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	asOf, hasAsOf := parseOptionalInt(r.URL.Query().Get("as_of"))
	args := []any{entityID, bookID} // book_id scopes the read (tenancy, LOCKED)
	pred := "valid_to_ordinal IS NULL" // current head
	if hasAsOf {
		args = append(args, asOf)
		pred = "valid_from_ordinal <= $3 AND (valid_to_ordinal IS NULL OR $3 < valid_to_ordinal)"
	}
	rows, err := s.pool.Query(r.Context(), `
		SELECT fact_id, entity_id, fact_kind, attr_or_predicate, value, valid_from_ordinal,
		       valid_to_ordinal, cardinality, source_episode_id
		FROM entity_facts
		WHERE entity_id = $1 AND book_id = $2 AND invalidated_at IS NULL AND `+pred+`
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
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	limit := parseLimit(r.URL.Query().Get("limit"), 50, 200)
	args := []any{entityID, bookID} // book_id scopes the read (tenancy, LOCKED)
	where := "entity_id = $1 AND book_id = $2"
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
	items := scanFacts(rows)
	// next_cursor = the oldest ordinal on this page; the caller pages older via before_order.
	resp := map[string]any{"items": items}
	if len(items) == limit {
		resp["next_cursor"] = strconv.FormatInt(items[len(items)-1].ValidFrom, 10)
	}
	writeJSON(w, http.StatusOK, resp)
}

// internalListAttrValues — GET .../attr-values?attr=&as_of=
// Paginated STRUCTURED multi-valued facts for one attr (aliases/tags/appears_in, §12.5.3).
func (s *Server) internalListAttrValues(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	attr := r.URL.Query().Get("attr")
	if attr == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "attr query param required")
		return
	}
	args := []any{entityID, attr, bookID} // book_id scopes the read (tenancy, LOCKED)
	pred := ""
	if asOf, ok := parseOptionalInt(r.URL.Query().Get("as_of")); ok {
		args = append(args, asOf)
		pred = " AND valid_from_ordinal <= $4 AND (valid_to_ordinal IS NULL OR $4 < valid_to_ordinal)"
	} else {
		pred = " AND valid_to_ordinal IS NULL"
	}
	rows, err := s.pool.Query(r.Context(), `
		SELECT fact_id, entity_id, fact_kind, attr_or_predicate, value, valid_from_ordinal,
		       valid_to_ordinal, cardinality, source_episode_id
		FROM entity_facts
		WHERE entity_id = $1 AND attr_or_predicate = $2 AND book_id = $3 AND invalidated_at IS NULL`+pred+`
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
	// Tenancy (LOCKED): the entity MUST belong to the path book, else a caller for book A
	// could write a fact onto a book-B entity stamped book_id=A (corrupt scope key).
	if !s.entityInBook(w, r, entityID, bookID) {
		return
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
	if err := markFoldDirty(r.Context(), tx, entityID, false); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "mark fold dirty failed")
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
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
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
	if len(body.FactIDs) > 0 && len(ids) == 0 {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "no valid fact_ids")
		return
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
	chains, err := retractFacts(r.Context(), tx, bookID, ids, reason)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "retract failed: "+err.Error())
		return
	}
	// Mark each affected entity's canonical dirty (an invalidation → bumps the re-ground counter).
	seenEnt := map[uuid.UUID]struct{}{}
	for _, c := range chains {
		if _, dup := seenEnt[c.EntityID]; dup {
			continue
		}
		seenEnt[c.EntityID] = struct{}{}
		if err := markFoldDirty(r.Context(), tx, c.EntityID, true); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "mark fold dirty failed")
			return
		}
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"retracted": len(ids), "chains_restitched": len(chains)})
}

// internalCloseFact — POST .../facts/close {fact_id, valid_to_ordinal}
// Explicit valid-time close (§12.3.2 / close_fact): pin the fact's valid_to so its value stops
// holding at the given ordinal even with no successor. Book-scoped; validates the fact is in the
// book + open and valid_to_ordinal > the fact's valid_from_ordinal; a close is a belief change → re-fold.
func (s *Server) internalCloseFact(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	var body struct {
		FactID  string `json:"fact_id"`
		ValidTo *int64 `json:"valid_to_ordinal"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	factID, ferr := uuid.Parse(body.FactID)
	if ferr != nil || body.ValidTo == nil {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "fact_id + valid_to_ordinal required")
		return
	}
	// Look up the fact in THIS book (tenancy) and fetch its chain key + lower bound + kind.
	var entityID uuid.UUID
	var attr, factKind, card string
	var validFrom int64
	err := s.pool.QueryRow(r.Context(), `
		SELECT entity_id, attr_or_predicate, fact_kind, cardinality, valid_from_ordinal
		FROM entity_facts WHERE fact_id = $1 AND book_id = $2 AND invalidated_at IS NULL`,
		factID, bookID).Scan(&entityID, &attr, &factKind, &card, &validFrom)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "fact not found in this book")
		return
	} else if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "fact lookup failed")
		return
	}
	if *body.ValidTo <= validFrom {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID",
			"valid_to_ordinal must be greater than the fact's valid_from_ordinal")
		return
	}
	// Overlap guard (single-valued chains only): a close must not extend PAST a later value's
	// start, or the as-of read would return two values at once. Closing AT or BEFORE the
	// successor's valid_from is fine (it shortens the interval / opens a gap). Multi-valued
	// facts have no chain successor, so they are exempt.
	if card == "single" {
		var nextFrom *int64
		if err := s.pool.QueryRow(r.Context(), `
			SELECT min(valid_from_ordinal) FROM entity_facts
			WHERE entity_id = $1 AND attr_or_predicate = $2 AND fact_kind = $3
			  AND cardinality = 'single' AND invalidated_at IS NULL AND valid_from_ordinal > $4`,
			entityID, attr, factKind, validFrom).Scan(&nextFrom); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "successor lookup failed")
			return
		}
		if nextFrom != nil && *body.ValidTo > *nextFrom {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID",
				"valid_to_ordinal would overlap a later value on this chain")
			return
		}
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx begin failed")
		return
	}
	defer tx.Rollback(r.Context()) //nolint:errcheck
	if err := acquireFactChainLock(r.Context(), tx, entityID, attr); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "chain lock failed")
		return
	}
	if _, err := closeFact(r.Context(), tx, bookID, factID, *body.ValidTo); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "close failed: "+err.Error())
		return
	}
	if err := markFoldDirty(r.Context(), tx, entityID, true); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "mark fold dirty failed")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}
	// Return the updated fact (the contract's Fact schema).
	var f factDTO
	var ep *uuid.UUID
	if err := s.pool.QueryRow(r.Context(), `
		SELECT fact_id, entity_id, fact_kind, attr_or_predicate, value, valid_from_ordinal,
		       valid_to_ordinal, cardinality, source_episode_id
		FROM entity_facts WHERE fact_id = $1`, factID).Scan(
		&f.FactID, &f.EntityID, &f.FactKind, &f.Attr, &f.Value, &f.ValidFrom, &f.ValidTo,
		&f.Cardinality, &ep); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "reload failed")
		return
	}
	if ep != nil {
		s := ep.String()
		f.SourceEpisode = &s
	}
	writeJSON(w, http.StatusOK, f)
}

// internalFactMerge — POST .../facts/merge {winner, loser, cross_kind}
// The fact-chain merge (§12.4.1) via mergeEntitiesCore (which now repoints + reconciles
// entity_facts, F1f). Service-driven (actor = nil).
func (s *Server) internalFactMerge(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	var body struct {
		Winner    string `json:"winner"`
		Loser     string `json:"loser"`
		CrossKind bool   `json:"cross_kind"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	winner, werr := uuid.Parse(body.Winner)
	if werr != nil || body.Loser == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "winner + loser required")
		return
	}
	results, err := s.mergeEntitiesCore(r.Context(), bookID, winner, []string{body.Loser}, uuid.Nil, body.CrossKind)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "merge failed: "+err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"winner": body.Winner, "merged": results})
}

// internalResolveEntity — POST .../facts/resolve-entity {name, kind} → resolve-or-create.
// The cross-kind resolver (#43) + cold-start bootstrap (§12.7.4): no match → create a
// minimal entity carrying the name (its name fact is emitted on the next chapter write).
func (s *Server) internalResolveEntity(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	var body struct {
		Name string `json:"name"`
		Kind string `json:"kind"`
	}
	if !decodeJSON(w, r, &body) || body.Name == "" || body.Kind == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "name + kind required")
		return
	}
	kindMap, err := s.loadKindMap(r.Context(), bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "kind map failed")
		return
	}
	kindID, ok := kindMap[body.Kind]
	if !ok {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_UNKNOWN_KIND", "unknown kind: "+body.Kind)
		return
	}
	// One tx under the per-book advisory lock so resolve+create can't race a concurrent
	// resolve-create of the same name (§12.7.8 — the lock is the primary guard, the
	// uq_entity_dedup index the backstop). Mirrors the extraction writeback.
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx begin failed")
		return
	}
	defer tx.Rollback(r.Context()) //nolint:errcheck
	if _, err := tx.Exec(r.Context(), `SELECT pg_advisory_xact_lock($1, hashtext($2))`,
		extractionWritebackLockNS, bookID.String()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "book lock failed")
		return
	}
	existing, err := s.findEntityByNameOrAlias(r.Context(), tx, bookID, kindID, body.Name, "")
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "resolve failed")
		return
	}
	if existing == uuid.Nil {
		if cross, _, cerr := s.findEntityCrossKind(r.Context(), tx, bookID, body.Name, ""); cerr == nil {
			existing = cross
		}
	}
	created := false
	if existing == uuid.Nil {
		// tx, not s.pool: a second pool connection here while tx (holding the book
		// lock above) is still open is the exact deadlock D-GLOSSARY-PROPOSE-LOCK
		// hit under connection pressure — this call was latent-affected too.
		attrDefMap, aerr := s.loadAttrDefMap(r.Context(), tx, bookID)
		if aerr != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "attr def map failed")
			return
		}
		newID, _, _, cerr := s.createExtractedEntity(r.Context(), tx, bookID, kindID, extractedEntity{Name: body.Name}, map[string]string{}, attrDefMap, "zh", nil)
		if cerr != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "create failed: "+cerr.Error())
			return
		}
		existing = newID
		created = true
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"entity_id": existing.String(), "created": created})
}

// internalSplitEntity — POST .../facts/split {source, new_name, new_kind, source_episode_ids}
// Creates the split-off entity and re-attributes facts cited to those episodes (§12.4.2).
func (s *Server) internalSplitEntity(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	var body struct {
		Source           string   `json:"source"`
		NewName          string   `json:"new_name"`
		NewKind          string   `json:"new_kind"`
		SourceEpisodeIDs []string `json:"source_episode_ids"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	source, serr := uuid.Parse(body.Source)
	if serr != nil || body.NewName == "" || body.NewKind == "" || len(body.SourceEpisodeIDs) == 0 {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "source + new_name + new_kind + source_episode_ids required")
		return
	}
	// Tenancy (LOCKED): the `source` entity comes from the request body — it MUST belong to
	// THIS book before we re-attribute (invalidate + copy) any of its facts. Without this a
	// caller holding book A's token could pass a book-B source and split its facts onto a
	// fresh book-A entity (cross-book corruption). splitFactsByEpisode is additionally
	// book-scoped below as defense-in-depth.
	if !s.entityInBook(w, r, source, bookID) {
		return
	}
	episodeIDs := make([]uuid.UUID, 0, len(body.SourceEpisodeIDs))
	for _, s := range body.SourceEpisodeIDs {
		if id, e := uuid.Parse(s); e == nil {
			episodeIDs = append(episodeIDs, id)
		}
	}
	kindMap, err := s.loadKindMap(r.Context(), bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "kind map failed")
		return
	}
	kindID, ok := kindMap[body.NewKind]
	if !ok {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_UNKNOWN_KIND", "unknown kind: "+body.NewKind)
		return
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx begin failed")
		return
	}
	defer tx.Rollback(r.Context()) //nolint:errcheck
	// Per-book lock serializes the new-entity create (resolver-create race, §12.7.8).
	if _, err := tx.Exec(r.Context(), `SELECT pg_advisory_xact_lock($1, hashtext($2))`,
		extractionWritebackLockNS, bookID.String()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "book lock failed")
		return
	}
	attrDefMap, err := s.loadAttrDefMap(r.Context(), tx, bookID) // tx already open+locked above
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "attr def map failed")
		return
	}
	newID, _, _, err := s.createExtractedEntity(r.Context(), tx, bookID, kindID, extractedEntity{Name: body.NewName}, map[string]string{}, attrDefMap, "zh", nil)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "create new entity failed: "+err.Error())
		return
	}
	moved, err := splitFactsByEpisode(r.Context(), tx, bookID, source, newID, episodeIDs)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "split failed: "+err.Error())
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"new_entity_id": newID.String(), "moved_facts": moved})
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
