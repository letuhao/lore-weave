package api

// state_handler.go — the book-wide as-of read (plan T5, AC1 + AC2).
//
// `facts_handler.go` already serves the as-of predicate for ONE entity. That is not the
// read the drafting agent needs: writing chapter 12 it must know the state of the whole
// cast at chapter 12, and asking per entity means N round trips through the KAL plus a
// list of entities it does not have yet. `composition-service` therefore never asked —
// zero occurrences of `as_of` — and drafted every chapter against the END of the book.
//
//	GET /internal/books/{book_id}/state?as_of=N
//
// Answers "what was true at story position N, for every entity in this book", one value
// per (entity, attribute). Two axes are involved and they are not the same:
//
//   - STORY time — the half-open interval [valid_from_ordinal, valid_to_eff). A character
//     who dies in chapter 40 is alive at 39 and dead at 40. This is what `as_of` selects.
//   - BELIEF time — `invalidated_at`. A chapter revision supersedes a fact; the fact stays
//     in the table (append-only) but is no longer canon at ANY position, so it is excluded
//     regardless of how well its story interval matches.
//
// A third, unrelated axis is AUTHORING lifecycle (`glossary_entities.deleted_at`): an
// entity the author moved to the recycle bin is not part of the book's canon at any
// position, so it is excluded here too — the same guard T1 put on `entityExistsInBook`.
// It is filtered on the ENTITY, never on the fact, precisely so it cannot be mistaken for
// the temporal death above.

import (
	"log/slog"
	"net/http"
	"strconv"
	"time"

	"github.com/google/uuid"
)

// stateFact is one attribute's value at the requested position. `valid_from_ordinal` is
// part of the contract, not decoration: it says WHICH interval answered, which is how a
// caller tells canon established last chapter from canon established in chapter 1.
type stateFact struct {
	Attr             string `json:"attr"`
	Value            string `json:"value"`
	FactKind         string `json:"fact_kind"`
	ValidFromOrdinal int64  `json:"valid_from_ordinal"`
}

type stateEntity struct {
	EntityID string      `json:"entity_id"`
	Facts    []stateFact `json:"facts"`
}

type stateResponse struct {
	BookID      string        `json:"book_id"`
	AsOfOrdinal int64         `json:"as_of_ordinal"`
	Entities    []stateEntity `json:"entities"`
}

// stateSizeWarnFacts — above this many facts in one response the read is worth looking at
// (T8 measures the ceiling; T9 adds the covering index). It WARNs, it does not truncate: a
// silently capped state read is a confidently wrong answer, which is the exact failure
// this endpoint exists to remove.
const stateSizeWarnFacts = 20000

// internalStateAsOf — GET /internal/books/{book_id}/state?as_of=N
func (s *Server) internalStateAsOf(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}

	// `as_of` is REQUIRED. Defaulting it to the head would answer "what is true now"
	// while wearing the shape of "what was true then", and the caller has no way to
	// notice — that is the defect this whole refactor exists to remove, so it is not
	// reintroduced as a convenience. Each rejection WARNs with the reason: a caller
	// reaching this read without a story position is a bug in the CALLER, and the WARN
	// is how it becomes visible instead of silently receiving end-of-book canon.
	raw := r.URL.Query().Get("as_of")
	if raw == "" {
		slog.Warn("state@as_of: request carries no story position — refused",
			"book_id", bookID.String(), "reason", "missing")
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST",
			"as_of query param required (story ordinal); there is no safe default")
		return
	}
	asOf, err := strconv.ParseInt(raw, 10, 64)
	if err != nil {
		slog.Warn("state@as_of: request carries no story position — refused",
			"book_id", bookID.String(), "reason", "not-an-integer", "as_of_raw", raw)
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "as_of must be an integer story ordinal")
		return
	}
	if asOf < 0 {
		slog.Warn("state@as_of: request carries no story position — refused",
			"book_id", bookID.String(), "reason", "negative", "as_of", asOf)
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "as_of must not be negative")
		return
	}

	started := time.Now()

	// The §12.3.1 half-open predicate, index-served by idx_entity_facts_asof:
	//   valid_from_ordinal <= N < valid_to_eff
	// `valid_to_eff` is the generated coalesce(valid_to_ordinal, maxint) column, so an
	// open interval needs no OR branch and the comparison stays sargable.
	//
	// DISTINCT ON collapses each (entity, attribute) to ONE row — the latest interval
	// that covers N. Without it a caller receives every historical value whose interval
	// happens to match and picks whichever the serializer emitted last; `single`
	// cardinality means overlapping intervals should not exist, and ordering by
	// valid_from DESC means a substrate bug degrades to "freshest wins" rather than
	// "random wins".
	//
	// count(*) OVER () is evaluated BEFORE DISTINCT ON in Postgres, so it carries the
	// pre-dedup row count for the log line without a second query.
	rows, err := s.pool.Query(r.Context(), `
		SELECT DISTINCT ON (f.entity_id, f.attr_or_predicate)
		       f.entity_id, f.attr_or_predicate, f.value, f.fact_kind, f.valid_from_ordinal,
		       count(*) OVER () AS pre_distinct_rows
		FROM entity_facts f
		JOIN glossary_entities e
		  ON e.entity_id = f.entity_id AND e.book_id = f.book_id
		WHERE f.book_id = $1
		  AND f.cardinality = 'single'
		  AND f.invalidated_at IS NULL
		  AND f.valid_from_ordinal <= $2
		  AND $2 < f.valid_to_eff
		  AND e.deleted_at IS NULL
		  AND e.permanently_deleted_at IS NULL
		ORDER BY f.entity_id, f.attr_or_predicate, f.valid_from_ordinal DESC`,
		bookID, asOf)
	if err != nil {
		slog.Error("state@as_of query failed", "book_id", bookID.String(), "as_of", asOf, "err", err)
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "state read failed")
		return
	}
	defer rows.Close()

	// Grouped in one pass. The query orders by entity_id, so a row whose entity differs
	// from the previous one starts a new group — no map, and the output order is stable.
	entities := []stateEntity{}
	var preDistinct int64
	var factCount int
	for rows.Next() {
		var entityID uuid.UUID
		var f stateFact
		if err := rows.Scan(&entityID, &f.Attr, &f.Value, &f.FactKind, &f.ValidFromOrdinal, &preDistinct); err != nil {
			slog.Error("state@as_of scan failed", "book_id", bookID.String(), "as_of", asOf, "err", err)
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "state read failed")
			return
		}
		id := entityID.String()
		if n := len(entities); n > 0 && entities[n-1].EntityID == id {
			entities[n-1].Facts = append(entities[n-1].Facts, f)
		} else {
			entities = append(entities, stateEntity{EntityID: id, Facts: []stateFact{f}})
		}
		factCount++
	}
	if err := rows.Err(); err != nil {
		slog.Error("state@as_of row iteration failed", "book_id", bookID.String(), "as_of", asOf, "err", err)
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "state read failed")
		return
	}

	elapsed := time.Since(started)
	slog.Debug("state@as_of",
		"book_id", bookID.String(),
		"as_of", asOf,
		"rows_pre_distinct", preDistinct,
		"rows_post_distinct", factCount,
		"entities", len(entities),
		"elapsed_ms", elapsed.Milliseconds())
	if factCount > stateSizeWarnFacts {
		slog.Warn("state@as_of returned a very large state — nothing was truncated, but this is the T8 ceiling becoming visible",
			"book_id", bookID.String(), "as_of", asOf, "facts", factCount, "entities", len(entities),
			"elapsed_ms", elapsed.Milliseconds())
	}

	writeJSON(w, http.StatusOK, stateResponse{
		BookID:      bookID.String(),
		AsOfOrdinal: asOf,
		Entities:    entities,
	})
}
