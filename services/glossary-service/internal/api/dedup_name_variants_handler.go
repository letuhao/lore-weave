package api

// D-GLOSSARY-ST-DEDUP M3b — internal remediation endpoint that merges existing
// entity name-variant duplicates (CJK simplified/traditional, full-width, case)
// that predate the M2 resolver fold. It groups LIVE entities of a book by
// (kind, textnorm.Normalize(cached_name)) — the SAME fold the resolver now uses —
// and merges every >1 group into a single winner via the journaled mergeEntitiesCore
// (so each merge is reversible and emits the `merged` outbox event that re-syncs the
// knowledge graph). DRY-RUN by default; ?apply=true performs the merges.
//
//	POST /internal/books/{book_id}/dedup-name-variants[?apply=true]
//
// New entities never form these duplicates anymore (the resolver folds at write
// time); this endpoint heals the pre-existing ones. It also re-stamps every live
// entity's app-maintained normalized_name with the new fold (M3a column) so the DB
// dedup-key backstop matches the resolver going forward.

import (
	"net/http"

	"github.com/google/uuid"
	"github.com/loreweave/glossary-service/internal/textnorm"
)

// dedupEnt is one live entity considered for name-variant merging.
type dedupEnt struct {
	id        uuid.UUID
	kind      uuid.UUID
	name      string
	linkCount int
	evidCount int
}

type dedupVariantMember struct {
	EntityID string `json:"entity_id"`
	Name     string `json:"name"`
}

type dedupVariantGroup struct {
	KindID    string               `json:"kind_id"`
	Key       string               `json:"normalized_key"`
	WinnerID  string               `json:"winner_id"`
	Winner    string               `json:"winner_name"`
	Losers    []dedupVariantMember `json:"losers"`
	MergeOK   *bool                `json:"merge_ok,omitempty"`
	MergeNote string               `json:"merge_note,omitempty"`
}

type dedupVariantResponse struct {
	DryRun        bool                `json:"dry_run"`
	TotalEntities int                 `json:"total_entities"`
	GroupCount    int                 `json:"duplicate_group_count"`
	EntitiesToMerge int               `json:"entities_to_merge"`
	NormalizedReStamped int           `json:"normalized_name_restamped"`
	Groups        []dedupVariantGroup `json:"groups"`
}

// internalDedupNameVariants groups + merges name-variant duplicates for a book.
func (s *Server) internalDedupNameVariants(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	apply := r.URL.Query().Get("apply") == "true"
	ctx := r.Context()

	// On apply, take the per-book advisory lock (the SAME key the extraction
	// writeback uses, INV-C1) so this multi-tx remediation can't interleave with a
	// concurrent extraction's create/merge on the book. Try-lock: if extraction
	// holds it, tell the caller to retry when quiet rather than block. Held on a
	// dedicated connection for the whole remediation; dry-run is read-only → no lock.
	if apply {
		lockConn, err := s.pool.Acquire(ctx)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "acquire lock conn")
			return
		}
		defer lockConn.Release()
		var locked bool
		if err := lockConn.QueryRow(ctx, `SELECT pg_try_advisory_lock($1, hashtext($2))`,
			extractionWritebackLockNS, bookID.String()).Scan(&locked); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "take book lock")
			return
		}
		if !locked {
			writeError(w, http.StatusConflict, "GLOSS_BOOK_BUSY",
				"the book is busy (extraction in progress) — retry when quiet")
			return
		}
		defer lockConn.Exec(ctx, `SELECT pg_advisory_unlock($1, hashtext($2))`, //nolint:errcheck
			extractionWritebackLockNS, bookID.String())
	}

	// Load all live, named entities for the book with their richness counters.
	rows, err := s.pool.Query(ctx, `
		SELECT entity_id, kind_id, COALESCE(cached_name, ''),
		       cached_chapter_link_count, cached_evidence_count
		FROM glossary_entities
		WHERE book_id = $1 AND deleted_at IS NULL AND COALESCE(cached_name, '') <> ''`,
		bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load entities")
		return
	}
	type groupKey struct {
		kind uuid.UUID
		norm string
	}
	groups := map[groupKey][]dedupEnt{}
	total := 0
	for rows.Next() {
		var e dedupEnt
		if err := rows.Scan(&e.id, &e.kind, &e.name, &e.linkCount, &e.evidCount); err != nil {
			rows.Close()
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan entity")
			return
		}
		total++
		k := groupKey{e.kind, textnorm.Normalize(e.name)}
		groups[k] = append(groups[k], e)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "iterate entities")
		return
	}

	resp := dedupVariantResponse{DryRun: !apply, TotalEntities: total}

	// Merge duplicate groups FIRST. Each merge soft-deletes the loser, removing it
	// from the partial uq_entity_dedup index — which is what makes the subsequent
	// re-stamp (both members → the same folded key) collision-free. Re-stamping
	// before merging would violate the unique index on the second live member.
	for k, members := range groups {
		if len(members) < 2 {
			continue
		}
		// Winner = richest: most chapter links + evidence, then most-…, tie-break by
		// the smallest entity_id for determinism (so a re-run picks the same winner).
		winner := members[0]
		for _, e := range members[1:] {
			if betterWinner(e, winner) {
				winner = e
			}
		}
		g := dedupVariantGroup{KindID: k.kind.String(), Key: k.norm, WinnerID: winner.id.String(), Winner: winner.name}
		loserIDs := make([]string, 0, len(members)-1)
		for _, e := range members {
			if e.id == winner.id {
				continue
			}
			g.Losers = append(g.Losers, dedupVariantMember{EntityID: e.id.String(), Name: e.name})
			loserIDs = append(loserIDs, e.id.String())
		}
		resp.GroupCount++
		resp.EntitiesToMerge += len(loserIDs)

		if apply {
			results, merr := s.mergeEntitiesCore(ctx, bookID, winner.id, loserIDs, uuid.Nil)
			ok := merr == nil
			g.MergeOK = &ok
			if merr != nil {
				g.MergeNote = merr.Error()
			} else {
				// summarize per-loser outcomes (merged vs skipped/failed)
				for _, res := range results {
					if res.Status != "merged" {
						g.MergeNote += res.LoserID + ":" + res.Status + "(" + res.Reason + ") "
					}
				}
			}
		}
		resp.Groups = append(resp.Groups, g)
	}

	// Re-stamp normalized_name to the new fold for every entity (the M3a
	// app-maintained backstop column). Runs AFTER the merges, so a resolved group
	// has just one live member → no collision. A stray unique-violation means a
	// group did NOT fully merge (a merge skip/failure left ≥2 live members sharing
	// the key); skip that row (its old key is harmless — the resolver is the primary
	// dedup) so one bad group can't 500 the whole remediation. Idempotent re-run
	// heals it once the duplication is resolved.
	if apply {
		for k := range groups {
			for _, e := range groups[k] {
				tag, err := s.pool.Exec(ctx,
					`UPDATE glossary_entities SET normalized_name = $1
					 WHERE entity_id = $2 AND normalized_name IS DISTINCT FROM $1`,
					k.norm, e.id)
				if err != nil {
					if isUniqueViolation(err) {
						continue
					}
					writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "restamp normalized_name")
					return
				}
				if tag.RowsAffected() > 0 {
					resp.NormalizedReStamped++
				}
			}
		}
	}

	writeJSON(w, http.StatusOK, resp)
}

// betterWinner reports whether candidate c should beat the current winner w:
// more chapter links wins; tie → more evidence; tie → smaller entity_id (stable).
func betterWinner(c, w dedupEnt) bool {
	if c.linkCount != w.linkCount {
		return c.linkCount > w.linkCount
	}
	if c.evidCount != w.evidCount {
		return c.evidCount > w.evidCount
	}
	return c.id.String() < w.id.String()
}
