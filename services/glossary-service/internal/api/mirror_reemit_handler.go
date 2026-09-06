package api

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"

	"github.com/google/uuid"
)

// The REPAIR side of the glossary→KG mirror (D-GLOSSARY-KG-MIRROR-HAS-NO-RECONCILER).
//
//	POST /internal/books/{book_id}/mirror-reemit   {"entity_ids": [...]}
//
// WHY THE REPAIR LIVES HERE AND NOT IN knowledge-service
// -------------------------------------------------------
// knowledge-service detects the divergence — it owns the KG and knows what is absent. The
// obvious fix from there is to MERGE the missing nodes itself. That would be wrong: the
// mirror would then have TWO writers, and the day they disagree the divergence class grows
// instead of shrinking. The projection has exactly one legitimate path — outbox → relay →
// Redis → consumer → `sync_glossary_entity_to_neo4j` — and this endpoint puts the lost
// events back at the START of it.
//
// That path is already proven correct today (the live replay in the deferral: a stored
// payload through the real handler created the node) and already idempotent (the MERGE is
// keyed on `glossary_entity_id`), so re-emitting an event for an entity that is ALREADY
// mirrored is a no-op update rather than a duplicate. Which is why this endpoint does not
// need — and deliberately does not have — its own notion of what is missing: passing an id
// that is fine costs one redundant MERGE, and passing one that is lost repairs it.
//
// WHAT IT REFUSES
// ---------------
// `loadEntityEventFields` is the emit-side read, and it is the SAME read every organic
// emit uses: it returns ok=false for an entity that is soft-deleted or absent. A caller
// asking to re-emit a trashed entity therefore gets it skipped, not resurrected — the KG
// is correct not to hold it, and D-OUTBOX-PAYLOAD-TRASH is the bug where editing a trashed
// entity silently un-deleted it in the consumer's index. Nameless drafts are skipped for
// the same reason the handler skips them: there is nothing to MERGE a node from yet.
//
// It is a repair, so it is deliberately boring: no new payload shape, no new writer, no
// state of its own. Everything it emits is byte-identical to what the organic path emits.
const mirrorReemitMaxIDs = 500

type mirrorReemitRequest struct {
	EntityIDs []string `json:"entity_ids"`
}

type mirrorReemitResponse struct {
	// Events actually written to the outbox. The relay ships them asynchronously, so a
	// caller that re-detects immediately will still see the old divergence — convergence
	// is eventual by construction, and pretending otherwise would be a lie about a
	// projection that has always been eventually consistent.
	Reemitted int `json:"reemitted"`
	// Ids the emit-side read declined: soft-deleted, absent, or belonging to another
	// book. Reported per id rather than counted, because "nothing happened and I will not
	// say which" is how a repair that silently does nothing looks exactly like one that
	// worked.
	SkippedIDs []string `json:"skipped_ids"`
	// Ids whose outbox insert failed. Non-empty means the repair is INCOMPLETE; re-run it.
	FailedIDs []string `json:"failed_ids"`
}

func (s *Server) internalMirrorReemit(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	var req mirrorReemitRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "invalid JSON body")
		return
	}
	if len(req.EntityIDs) == 0 {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST", "entity_ids is required")
		return
	}
	if len(req.EntityIDs) > mirrorReemitMaxIDs {
		writeError(w, http.StatusBadRequest, "GLOSS_BAD_REQUEST",
			"entity_ids exceeds the per-call cap; page the repair")
		return
	}

	resp := mirrorReemitResponse{SkippedIDs: []string{}, FailedIDs: []string{}}
	exec := func(ctx context.Context, sql string, args ...any) error {
		_, e := s.pool.Exec(ctx, sql, args...)
		return e
	}

	for _, raw := range req.EntityIDs {
		entityID, err := uuid.Parse(raw)
		if err != nil {
			resp.SkippedIDs = append(resp.SkippedIDs, raw)
			continue
		}
		name, kind, aliases, shortDesc, live := loadEntityEventFields(r.Context(), s.pool, entityID)
		if !live || name == "" || kind == "" {
			resp.SkippedIDs = append(resp.SkippedIDs, raw)
			continue
		}
		// Tenancy: the id must belong to the book in the path. Without this a caller
		// could name any entity in the database and have this service emit for it —
		// the scope has to come from the row, not from the caller's assertion.
		var owner uuid.UUID
		if err := s.pool.QueryRow(r.Context(),
			`SELECT book_id FROM glossary_entities WHERE entity_id = $1`, entityID,
		).Scan(&owner); err != nil || owner != bookID {
			resp.SkippedIDs = append(resp.SkippedIDs, raw)
			continue
		}

		payload := buildEntityEventPayload(
			bookID.String(), entityID.String(), name, kind, aliases, shortDesc,
			"updated", "pipeline", "", nil,
		)
		if err := insertEntityOutboxEvent(r.Context(), exec, entityID, payload); err != nil {
			slog.Warn("mirror-reemit: outbox insert failed",
				"entity_id", entityID.String(), "err", err)
			resp.FailedIDs = append(resp.FailedIDs, raw)
			continue
		}
		resp.Reemitted++
	}

	slog.Info("mirror-reemit", "book_id", bookID.String(),
		"requested", len(req.EntityIDs), "reemitted", resp.Reemitted,
		"skipped", len(resp.SkippedIDs), "failed", len(resp.FailedIDs))
	writeJSON(w, http.StatusOK, resp)
}
