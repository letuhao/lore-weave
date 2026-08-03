package api

import (
	"context"
	"encoding/json"

	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/domain"
)

// The DB half of entity-kind resolution (spec docs/specs/2026-08-03-glossary-kg-entity-refactor/2026-08-02-entity-kind-resolution.md). The
// estimator itself is a pure function in internal/domain so it can be tested without a pool;
// this file only loads its inputs and writes its output.

// These take pgxRWQuerier (declared in extraction_handler.go) so the writeback can run them
// inside its per-book transaction and a backfill can run them straight on the pool.
// recordKindVote adds one observation: extraction proposed `kindID` for `entityID`. Called
// even when the store already holds a different kind -- that disagreement IS the signal, and
// throwing it away is precisely what froze 姜子牙 as a species.
func (s *Server) recordKindVote(ctx context.Context, tx pgxRWQuerier, entityID, kindID uuid.UUID) error {
	_, err := tx.Exec(ctx, `
		INSERT INTO entity_kind_votes (entity_id, kind_id, votes)
		VALUES ($1, $2, 1)
		ON CONFLICT (entity_id, kind_id)
		DO UPDATE SET votes = entity_kind_votes.votes + 1, last_seen = now()`,
		entityID, kindID)
	return err
}

// setKindVotes SETS an absolute count rather than incrementing.
//
// A backfill imports a COMPLETE observed history, so re-running it must RESTATE the numbers,
// not add to them. The first version incremented, and four runs of the same script inflated
// 姜子牙's ledger from 84 observations to 321 -- the ratios survived, so the resolution did
// not change, but the counts were fiction and nothing would ever have brought them back down.
//
// A plain SET (not GREATEST) is safe because the source it restates -- translation-service's
// raw-output cache -- holds the latest parse per (chapter, window, batch, profile) key, so it
// already contains whatever a live extraction has voted since. Preserving a higher live count
// would double-count exactly those runs.
func (s *Server) setKindVotes(ctx context.Context, tx pgxRWQuerier, entityID, kindID uuid.UUID, votes int) error {
	_, err := tx.Exec(ctx, `
		INSERT INTO entity_kind_votes (entity_id, kind_id, votes)
		VALUES ($1, $2, $3)
		ON CONFLICT (entity_id, kind_id)
		DO UPDATE SET votes = EXCLUDED.votes, last_seen = now()`,
		entityID, kindID, votes)
	return err
}

// loadKindVotes reads an entity's ledger.
func (s *Server) loadKindVotes(ctx context.Context, tx pgxRWQuerier, entityID uuid.UUID) ([]domain.KindVote, error) {
	rows, err := tx.Query(ctx,
		`SELECT kind_id, votes FROM entity_kind_votes WHERE entity_id=$1`, entityID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []domain.KindVote
	for rows.Next() {
		var v domain.KindVote
		if err := rows.Scan(&v.KindID, &v.Votes); err != nil {
			return nil, err
		}
		out = append(out, v)
	}
	return out, rows.Err()
}

// loadKindParents reads the book's kind hierarchy as child -> parent. Book-local, so the map is
// small (one row per adopted kind) and is loaded once per writeback request rather than per
// entity.
func (s *Server) loadKindParents(ctx context.Context, tx pgxRWQuerier, bookID uuid.UUID) (map[uuid.UUID]uuid.UUID, error) {
	rows, err := tx.Query(ctx,
		`SELECT book_kind_id, parent_kind_id FROM book_kinds
		 WHERE book_id=$1 AND parent_kind_id IS NOT NULL`, bookID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := map[uuid.UUID]uuid.UUID{}
	for rows.Next() {
		var child, parent uuid.UUID
		if err := rows.Scan(&child, &parent); err != nil {
			return nil, err
		}
		out[child] = parent
	}
	return out, rows.Err()
}

// loadCanonicalKindCodes maps a book's kind ids to their CANONICAL codes.
//
// Not the inverse of `loadKindMap`: that map is alias-folded, so several codes point at one
// kind and inverting it returns whichever alias the map iteration happened to reach. The first
// version did exactly that and reported moves "to generic" -- an alias of `terminology` -- which
// would have gone out on the wire to knowledge-service as the entity's kind.
func (s *Server) loadCanonicalKindCodes(ctx context.Context, tx pgxRWQuerier, bookID uuid.UUID) (map[uuid.UUID]string, error) {
	rows, err := tx.Query(ctx, `SELECT book_kind_id, code FROM book_kinds WHERE book_id=$1`, bookID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := map[uuid.UUID]string{}
	for rows.Next() {
		var id uuid.UUID
		var code string
		if err := rows.Scan(&id, &code); err != nil {
			return nil, err
		}
		out[id] = code
	}
	return out, rows.Err()
}

// applyKindResolution writes a resolution back. Returns true when the PRIMARY kind moved, so
// the caller knows to emit the outbox event that re-syncs the KG -- a kind change that the
// graph never hears about is worse than no change at all.
//
// `kind_labels` and `kind_conflict_id` are refreshed on every call, including when the primary
// did not move: a conflict that has been resolved must CLEAR, or the badge outlives the
// disagreement and becomes noise nobody trusts.
func (s *Server) applyKindResolution(ctx context.Context, tx pgxRWQuerier, entityID uuid.UUID, r domain.Resolution) (bool, error) {
	// As []string, not []uuid.UUID: pgx has a codec for a single uuid but not for a SLICE of
	// google/uuid values, so the array bind failed at runtime with an opaque error while the
	// identical statement worked by hand. Strings encode into uuid[] unambiguously.
	labels := make([]string, 0, len(r.Secondary))
	for _, k := range r.Secondary {
		labels = append(labels, k.String())
	}
	var conflict *string
	if r.Conflict != uuid.Nil {
		c := r.Conflict.String()
		conflict = &c
	}
	if r.Changed {
		// A re-kind is not always a MOVE. The dedup key is
		// (book_id, kind_id, normalized_name, scope_label), so if the target kind already
		// holds an entity with this name, moving there is a unique violation -- and the
		// operation the data actually calls for is a MERGE of two rows, not a relabel of one.
		//
		// Found the hard way: the first backfill aborted its whole transaction on 姜子牙,
		// because a `character` row with that name already existed alongside the `species`
		// one. Blocking here keeps the other 90-odd corrections, and records the intent as a
		// conflict so the pair is visible instead of silently left alone.
		var clash bool
		if err := tx.QueryRow(ctx, `
			SELECT EXISTS(
			  SELECT 1 FROM glossary_entities other
			  JOIN glossary_entities self ON self.entity_id = $1
			  WHERE other.entity_id <> self.entity_id
			    AND other.book_id = self.book_id
			    AND other.kind_id = $2
			    AND other.normalized_name = self.normalized_name
			    AND other.scope_label IS NOT DISTINCT FROM self.scope_label
			    AND other.deleted_at IS NULL
			    AND self.normalized_name <> '')`,
			entityID, r.Primary).Scan(&clash); err != nil {
			return false, err
		}
		if clash {
			target := r.Primary.String()
			_, err := tx.Exec(ctx, `
				UPDATE glossary_entities SET kind_labels=$2, kind_conflict_id=$3
				 WHERE entity_id=$1`, entityID, labels, &target)
			return false, err
		}
		_, err := tx.Exec(ctx, `
			UPDATE glossary_entities
			   SET kind_id=$2, kind_labels=$3, kind_conflict_id=$4, updated_at=now()
			 WHERE entity_id=$1`, entityID, r.Primary, labels, conflict)
		return err == nil, err
	}
	_, err := tx.Exec(ctx, `
		UPDATE glossary_entities SET kind_labels=$2, kind_conflict_id=$3
		 WHERE entity_id=$1`, entityID, labels, conflict)
	return false, err
}

// resolveEntityKind is the whole cycle for one entity: record what extraction just said, read
// the ledger back, resolve, and persist. Returns the resolution so the caller can emit the
// RESOLVED kind rather than the proposed one.
func (s *Server) resolveEntityKind(
	ctx context.Context, tx pgxRWQuerier, entityID, proposedKindID uuid.UUID,
	incumbentKindID uuid.UUID, parents map[uuid.UUID]uuid.UUID,
) (domain.Resolution, error) {
	if err := s.recordKindVote(ctx, tx, entityID, proposedKindID); err != nil {
		return domain.Resolution{Primary: incumbentKindID}, err
	}
	votes, err := s.loadKindVotes(ctx, tx, entityID)
	if err != nil {
		return domain.Resolution{Primary: incumbentKindID}, err
	}
	res := domain.ResolveKind(incumbentKindID, votes, parents)
	if _, err := s.applyKindResolution(ctx, tx, entityID, res); err != nil {
		return res, err
	}
	return res, nil
}

// decodeKindFacets turns the two JSON columns the entity queries select into the response
// shape. Tolerant by design: a decode failure yields no facets rather than failing the read.
// These are an ADVISORY overlay on a kind the row already carries -- an entity list that 500s
// because a badge could not be built would be a strictly worse outcome than a missing badge.
func decodeKindFacets(labelsJSON, conflictJSON []byte) ([]kindSummary, *kindSummary) {
	var labels []kindSummary
	if len(labelsJSON) > 0 {
		if err := json.Unmarshal(labelsJSON, &labels); err != nil {
			labels = nil
		}
	}
	if len(labels) == 0 {
		labels = nil // omitempty: the common case sends no key at all
	}
	var conflict *kindSummary
	if len(conflictJSON) > 0 {
		var c kindSummary
		if err := json.Unmarshal(conflictJSON, &c); err == nil && c.Code != "" {
			conflict = &c
		}
	}
	return labels, conflict
}
