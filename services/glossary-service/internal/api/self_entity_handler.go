package api

// WS-1.6 (spec 05 §Q5) — POST /internal/books/{book_id}/self-entity?user_id= (internal-token).
//
// Get-or-create the user's OWN identity entity in their diary glossary, marked is_self and
// ACTIVE, so:
//   - capture dedups a candidate that IS the user (their name) onto it instead of minting the
//     user as a colleague ("I told Alice…" must not create "me" as a work contact), and
//   - the co-occurrence / salience detectors can exclude it (the user is the subject of most
//     statements and would otherwise flood every co-occurrence).
//
// Idempotent: exactly one self-entity per book (uq_glossary_entities_one_self_per_book). No
// grant check — the internal caller (the assistant provisioner) already established ownership
// when it created the diary under the user's JWT, exactly like internalAdoptBookKinds.

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// errNoColleagueKindForSelf — the diary has not adopted the work ontology, so there is no
// 'colleague' kind to mint the identity entity as. The provisioner adopts kinds (WS-1.5b)
// BEFORE seeding self, so this is a caller-ordering error, surfaced distinctly (409).
var errNoColleagueKindForSelf = errors.New("diary has no 'colleague' kind — adopt the work ontology first")

// internalEraseBookEntities — D-R27 (human-authorized erasure) — HARD-delete EVERY glossary entity
// of a diary book (the captured people/projects — "Minh", "Acme Corp" — plus the seeded self-entity),
// cascading to their evidence/aliases/revisions via ON DELETE CASCADE. This is a hard row-delete (not
// the `deleted_at` soft-delete), so after erasure the diary's captured entities are ROW-GONE.
// Internal-token; book-scoped — the assistant-erase orchestrator (gateway) resolved the caller's OWN
// diary book_id (same trust model as internalSeedSelfEntity / internalAdoptBookKinds). Idempotent.
func (s *Server) internalEraseBookEntities(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	ct, err := s.pool.Exec(r.Context(), `DELETE FROM glossary_entities WHERE book_id=$1`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_CONFLICT", "failed to erase entities")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"deleted_entities": ct.RowsAffected()})
}

func (s *Server) internalSeedSelfEntity(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	// user_id is required (the entity represents this user's identity) but is validated, not
	// trusted for ownership — that was established upstream. The display name rides the body.
	if strings.TrimSpace(r.URL.Query().Get("user_id")) == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "user_id is required")
		return
	}
	var in struct {
		Name string `json:"name"`
	}
	_ = json.NewDecoder(r.Body).Decode(&in) // body optional
	name := strings.TrimSpace(in.Name)
	if name == "" {
		name = "Me" // a sensible default; the user can rename their own entity
	}

	entityID, created, err := s.seedSelfEntityCore(r.Context(), bookID, name)
	if err != nil {
		if errors.Is(err, errNoColleagueKindForSelf) {
			writeError(w, http.StatusConflict, "GLOSS_NO_KINDS", err.Error())
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to seed self-entity")
		return
	}
	status := http.StatusOK
	if created {
		status = http.StatusCreated
	}
	writeJSON(w, status, map[string]any{"entity_id": entityID, "created": created})
}

// seedSelfEntityCore — the get-or-create for the user's is_self identity entity. Returns
// (entity_id, created). Idempotent + race-safe (proposeNewEntity dedups the name under a
// per-book advisory lock, so concurrent seeds converge on ONE entity and the one-self-per-book
// unique cannot fire). Extracted from the handler so it is directly testable without the
// HTTP/token harness.
func (s *Server) seedSelfEntityCore(ctx context.Context, bookID uuid.UUID, name string) (string, bool, error) {
	// 1. Already seeded? Return it (idempotent — the common case on a re-provision).
	var existing string
	err := s.pool.QueryRow(ctx,
		`SELECT entity_id FROM glossary_entities
		 WHERE book_id=$1 AND is_self AND deleted_at IS NULL LIMIT 1`, bookID).Scan(&existing)
	if err == nil {
		return existing, false, nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return "", false, err
	}

	// 2. Resolve the 'colleague' kind in the diary's adopted ontology (WS-1.5b cloned it in).
	kindMap, err := s.loadKindMap(ctx, bookID)
	if err != nil {
		return "", false, err
	}
	kindID, ok := kindMap["colleague"]
	if !ok {
		return "", false, errNoColleagueKindForSelf
	}

	// 3. Create (or find) the identity entity via the shared machinery, then promote it to
	//    ACTIVE + is_self. We strip the ai-suggested / ai-rejected provenance tags: this is a
	//    system-seeded identity, not a review draft nor a rejection.
	entityID, _, _, err := s.proposeNewEntity(ctx, bookID, kindID, name, nil, "")
	if err != nil {
		return "", false, err
	}
	if _, err := s.pool.Exec(ctx, `
		UPDATE glossary_entities
		   SET status='active', is_self=true,
		       tags = array_remove(array_remove(tags,'ai-suggested'),'ai-rejected'),
		       updated_at=now()
		 WHERE entity_id=$1 AND book_id=$2 AND deleted_at IS NULL`,
		entityID, bookID); err != nil {
		return "", false, err
	}
	return entityID.String(), true, nil
}
