package api

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strings"

	"github.com/google/uuid"
)

// Entity-lifecycle COMMANDS on the internal surface — the KAL's write half (plan T29).
//
// WHY THESE EXIST
// ---------------
// T27 and T28 made the five entity transitions safe: each writes and emits in one
// transaction, through exactly one `*Core`, with a gate that fails the build if a new writer
// forgets the event. But every one of those cores was reachable only from the REST route a
// human's browser calls and the MCP tool an agent calls. A SERVICE that needed to retire or
// restore an entity had no sanctioned way to ask — and INV-KAL forbids reaching around the
// KAL into `/internal/*` from anywhere else, so "no route" meant "no path at all".
//
// These are that path. They are deliberately THIN: parse, resolve the actor, call the core.
// Every rule that matters — book scoping, the no-op/found distinction, the emission — already
// lives in the core, and a handler that re-implemented any of it would be a second place for
// the two to drift, which is the failure T28 is named after.
//
// THE ACTOR IS A HEADER, NOT AN ASSUMPTION
// ----------------------------------------
// `X-User-Id` is forwarded by the KAL when a caller identity exists, and absent when the
// command is a pipeline's own. Absent ⇒ `uuid.Nil` ⇒ `actorFor` records `pipeline` with an
// EMPTY actor id. That distinction is the whole reason T27 made the actor a parameter instead
// of reading it from ctx: an audit trail that records a pipeline sweep as a user's deletion is
// worse than one that says nothing.
//
// AUTHORITY
// ---------
// These sit under the `/internal` router, which is already internal-token gated, and they take
// the book id from the path. There is no grant check here BY DESIGN and it is the same trust
// model every sibling `/internal` route uses: the caller is a trusted service that established
// ownership upstream under the user's JWT. Adding a half-grant-check here would suggest a
// guarantee this surface does not make.

// entityCommandResult is the shape all five commands answer with. `found=false` is a 404, not
// an error: deleting an already-deleted entity changed nothing, and the caller needs to be
// able to tell "I did it" from "there was nothing to do" — a distinction a bare 204 destroys.
type entityCommandResult struct {
	EntityID string `json:"entity_id"`
	Op       string `json:"op"`
	Applied  bool   `json:"applied"`
}

// internalActor reads the forwarded caller identity. A malformed value is treated as ABSENT
// rather than rejected: the command's authority comes from the internal token, not from this
// header, so a garbled id must degrade to `pipeline` rather than fail a legitimate write.
// It is logged, because a caller that thinks it is forwarding an identity and is not should be
// discoverable without reading its source.
func internalActor(r *http.Request) uuid.UUID {
	raw := strings.TrimSpace(r.Header.Get("X-User-Id"))
	if raw == "" {
		return uuid.Nil
	}
	id, err := uuid.Parse(raw)
	if err != nil {
		slog.Warn("internal entity command: unparseable X-User-Id — recording as pipeline",
			"value", raw)
		return uuid.Nil
	}
	return id
}

// runEntityLifecycleCommand is the shared body of delete/restore/purge. The three differ only
// in which core they call and what they call themselves, so they share everything else —
// including the found/404 mapping, which is the part most likely to drift if copied.
func (s *Server) runEntityLifecycleCommand(
	w http.ResponseWriter, r *http.Request, op string,
	core func(ctx context.Context, bookID, entityID, actorID uuid.UUID) (bool, error),
) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	found, err := core(r.Context(), bookID, entityID, internalActor(r))
	if err != nil {
		slog.Error("internal entity command failed", "op", op,
			"book_id", bookID.String(), "entity_id", entityID.String(), "error", err)
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", op+" failed")
		return
	}
	if !found {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND",
			"no entity in this book was in a state to "+op)
		return
	}
	writeJSON(w, http.StatusOK, entityCommandResult{
		EntityID: entityID.String(), Op: op, Applied: true,
	})
}

func (s *Server) internalEntityDelete(w http.ResponseWriter, r *http.Request) {
	s.runEntityLifecycleCommand(w, r, "delete", s.softDeleteEntityCore)
}

func (s *Server) internalEntityRestore(w http.ResponseWriter, r *http.Request) {
	s.runEntityLifecycleCommand(w, r, "restore", s.restoreEntityCore)
}

func (s *Server) internalEntityPurge(w http.ResponseWriter, r *http.Request) {
	s.runEntityLifecycleCommand(w, r, "purge", s.purgeEntityCore)
}

// internalEntityStatus — the batch curation command (T28). Batch rather than per-entity
// because the core is batch: it locks the matched rows, and the count it returns and the
// events it emits come from that ONE locked list. Exposing it per-entity would either loop
// (losing that guarantee) or lie about it.
func (s *Server) internalEntityStatus(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	var in struct {
		Status    string   `json:"status"`
		EntityIDs []string `json:"entity_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	if !validEntityStatus(in.Status) {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_STATUS",
			"status must be active, inactive, draft, or rejected")
		return
	}
	// Same 1000 ceiling the REST route enforces. A batch limit that differs per entry point is
	// a limit the caller cannot reason about.
	if len(in.EntityIDs) == 0 || len(in.EntityIDs) > 1000 {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY",
			"entity_ids must hold between 1 and 1000 ids")
		return
	}
	ids := parseEntityIDs(in.EntityIDs)
	if len(ids) == 0 {
		writeJSON(w, http.StatusOK, map[string]any{"updated": 0, "status": in.Status})
		return
	}
	updated, err := s.bulkSetEntityStatusCore(r.Context(), bookID, in.Status, ids, internalActor(r))
	if err != nil {
		slog.Error("internal entity status command failed",
			"book_id", bookID.String(), "error", err)
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "status change failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"updated": updated, "status": in.Status})
}

// internalEntityReassignKind — the other curation command (T28). Takes `kind_id`, matching the
// REST route: resolving a kind CODE would need the book's ontology, and two entry points
// resolving it separately is how they come to disagree about what a code means.
func (s *Server) internalEntityReassignKind(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	var in struct {
		KindID string `json:"kind_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "kind_id is required")
		return
	}
	kindID, perr := uuid.Parse(strings.TrimSpace(in.KindID))
	if perr != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "kind_id must be a UUID")
		return
	}
	err := s.reassignEntityKindCore(r.Context(), bookID, entityID, kindID, internalActor(r))
	switch {
	case errors.Is(err, errReassignKindNotFound):
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "target kind not found")
	case errors.Is(err, errReassignEntityNotFound):
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found in this book")
	case err != nil:
		slog.Error("internal reassign-kind command failed",
			"book_id", bookID.String(), "entity_id", entityID.String(), "error", err)
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "reassign failed")
	default:
		writeJSON(w, http.StatusOK, entityCommandResult{
			EntityID: entityID.String(), Op: "reassign_kind", Applied: true,
		})
	}
}
