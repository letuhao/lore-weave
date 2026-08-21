package api

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"

	"github.com/google/uuid"

	"github.com/loreweave/glossary-service/internal/domain"
)

// POST /internal/books/{book_id}/kind-votes  (internal-token)
//
// Bulk-import observations into the kind ledger and re-resolve. This exists for ONE reason:
// the observation history that would have prevented the 173 frozen kinds lives in
// translation-service's `extraction_raw_outputs`, a different service and a different
// database, while the ledger and the estimator live here.
//
// The alternative was a backfill script that reimplements ResolveKind in Python. That is the
// mirror-the-producer defect this repo has now shipped twice in one day (the replay hash, and
// the strategy hash before it): the copy agrees with the original exactly until one of them
// changes, and nothing goes red when it does. So the script carries no policy at all — it
// posts counts, and the SAME Go function decides.
//
// No grant check: internal-token only, and the caller (a maintenance script run by an
// operator) is outside the user request path — the same posture as internalAdoptBookKinds.

type kindVoteIn struct {
	Name     string `json:"name"`
	KindCode string `json:"kind_code"`
	Votes    int    `json:"votes"`
}

type kindVoteResult struct {
	Name       string `json:"name"`
	From       string `json:"from"`
	To         string `json:"to"`
	Refinement bool   `json:"refinement,omitempty"`
	Conflict   string `json:"conflict,omitempty"`
}

func (s *Server) internalImportKindVotes(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	var in struct {
		Votes []kindVoteIn `json:"votes"`
		// Apply=false is a DRY RUN: vote writes and resolution happen in this transaction
		// to produce an exact preview, then the transaction is rolled back. No ledger,
		// entity, or outbox state may persist without an explicit --apply.
		Apply bool `json:"apply"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	ctx := r.Context()

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx begin failed")
		return
	}
	defer tx.Rollback(ctx)

	kindMap, err := s.loadKindMap(ctx, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "kind map load failed")
		return
	}
	codeByKind, err := s.loadCanonicalKindCodes(ctx, tx, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "kind code map load failed")
		return
	}
	parents, err := s.loadKindParents(ctx, tx, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "kind hierarchy load failed")
		return
	}

	// Record every vote first, so an entity named by several rows resolves ONCE against its
	// complete ledger. Resolving per row would let the last row win — the same arrival-order
	// bug in miniature.
	touched := map[uuid.UUID]bool{}
	unmatched := 0
	for _, v := range in.Votes {
		kindID, kok := kindMap[v.KindCode]
		if !kok || v.Name == "" || v.Votes < 1 {
			unmatched++
			continue
		}
		entID, _, eerr := s.findEntityCrossKind(ctx, tx, bookID, v.Name, "")
		if eerr != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "entity lookup failed")
			return
		}
		if entID == uuid.Nil {
			unmatched++
			continue
		}
		// SET, not increment: this is a complete history being restated, and a second run of
		// the same backfill must be a no-op rather than a doubling. GREATEST also means a
		// live extraction that has already voted past the imported count is never lowered.
		if err := s.setKindVotes(ctx, tx, entID, kindID, v.Votes); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "vote write failed")
			return
		}
		touched[entID] = true
	}

	var changes []kindVoteResult
	var blocked []kindVoteResult
	for entID := range touched {
		var incumbent uuid.UUID
		var name string
		if err := tx.QueryRow(ctx,
			`SELECT kind_id, coalesce(cached_name,'') FROM glossary_entities WHERE entity_id=$1`,
			entID).Scan(&incumbent, &name); err != nil {
			continue
		}
		votes, verr := s.loadKindVotes(ctx, tx, entID)
		if verr != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "vote read failed")
			return
		}
		res := domain.ResolveKind(incumbent, votes, parents)
		if !in.Apply {
			if res.Changed || res.Conflict != uuid.Nil {
				changes = append(changes, kindVoteResult{
					Name: name, From: codeByKind[incumbent], To: codeByKind[res.Primary],
					Refinement: res.Refinement, Conflict: codeByKind[res.Conflict],
				})
			}
			continue
		}
		moved, aerr := s.applyKindResolution(ctx, tx, entID, res)
		if aerr != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "kind apply failed: "+aerr.Error())
			return
		}
		// `res.Changed && !moved` means the move was BLOCKED by an existing entity of the
		// same name under the target kind -- a merge, not a relabel. Reported as blocked
		// rather than as applied, so the run's own output does not overstate what it did.
		if res.Changed && !moved {
			blocked = append(blocked, kindVoteResult{
				Name: name, From: codeByKind[incumbent], To: codeByKind[res.Primary],
				Refinement: res.Refinement,
			})
		} else if res.Changed || res.Conflict != uuid.Nil {
			changes = append(changes, kindVoteResult{
				Name: name, From: codeByKind[incumbent], To: codeByKind[res.Primary],
				Refinement: res.Refinement, Conflict: codeByKind[res.Conflict],
			})
		}
		if moved {
			// Same outbox path the writeback uses, so knowledge-service re-syncs a
			// backfilled re-kind exactly as it would a live one. A silent re-kind would
			// leave the graph projecting the kind we just corrected.
			payload := buildEntityEventPayload(
				bookID.String(), entID.String(), name, codeByKind[res.Primary],
				nil, "", "updated", "pipeline", "", nil,
			)
			if err := insertEntityOutboxEvent(ctx, func(ctx context.Context, sql string, args ...any) error {
				_, e := tx.Exec(ctx, sql, args...)
				return e
			}, entID, payload); err != nil {
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "event emit failed")
				return
			}
		}
	}

	if in.Apply {
		if err := tx.Commit(ctx); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
			return
		}
	} else {
		if err := tx.Rollback(ctx); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "dry-run rollback failed")
			return
		}
		slog.Debug("[FIX] kind-vote dry run rolled back", "book_id", bookID, "entities_touched", len(touched))
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"applied":          in.Apply,
		"votes_in":         len(in.Votes),
		"unmatched":        unmatched,
		"entities_touched": len(touched),
		"changes":          changes,
		// Moves the dedup key refused: the target kind already holds this name, so the
		// correct operation is a merge of two entities rather than a re-kind of one.
		"blocked_by_duplicate": blocked,
	})
}
