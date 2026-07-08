package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/loreweave/grantclient"
)

// Kind-alias + unknown-bucket review endpoints (kind-resolution epic).
//
// When extract-entities can't resolve an incoming kind_code (neither a kind nor an
// alias), the entity is parked under the 'unknown' system kind and remembers the
// code it arrived as in source_kind_code (see extraction_handler.go). These handlers
// are the author's triage surface:
//   * listUnknownEntities  — GET the review queue for a book.
//   * listKindAliases      — GET the existing alias table (for the GUI).
//   * reassignEntityKind   — POST move ONE entity to a kind (ad-hoc triage; gated on
//                            a book EDIT grant — it moves an entity reference, it does
//                            NOT mutate the shared kind catalogue).
//
// SS-4 Milestone C removed the bulk merge writer (createKindAlias: alias_code → kind
// + reassign) along with the user-facing system-kind write routes — a regular user
// must not author shared system kinds/aliases. The bulk-merge returns in SS-7,
// retargeted at the tiered (user/book) kind model. Per-entity reassignEntityKind
// stays so reviewers can still triage the unknown bucket one entity at a time.

type unknownEntityOut struct {
	EntityID       string  `json:"entity_id"`
	Name           string  `json:"name"`
	SourceKindCode *string `json:"source_kind_code"`
	Status         string  `json:"status"`
	CreatedAt      string  `json:"created_at"`
	// ScopeLabel (D-GLOSSARY-ENTITY-SCOPE) surfaces an existing disambiguator so a
	// triaging agent/human can tell two same-named unknowns apart before deciding
	// whether one is a duplicate of the other or a genuinely distinct entity.
	ScopeLabel string `json:"scope_label,omitempty"`
}

// listUnknownEntities handles GET /v1/glossary/books/{book_id}/unknown-entities
func (s *Server) listUnknownEntities(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookUUID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookUUID, userID, grantclient.GrantView) {
		return
	}
	// REST callers keep the pre-existing status-blind behavior unchanged — the
	// default-to-"draft" narrowing (2026-07-08 MCP feedback) is scoped to the
	// glossary_list_unknown_entities MCP tool, not this REST endpoint.
	out, total, err := s.queryUnknownEntities(r.Context(), bookUUID, "all")
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to query unknown entities")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": out, "total": total})
}

type kindAliasOut struct {
	AliasID   string `json:"alias_id"`
	AliasCode string `json:"alias_code"`
	KindID    string `json:"kind_id"`
	KindCode  string `json:"kind_code"`
	CreatedAt string `json:"created_at"`
}

// listKindAliases handles GET /v1/glossary/kind-aliases
func (s *Server) listKindAliases(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	rows, err := s.pool.Query(r.Context(), `
		SELECT a.alias_id, a.alias_code, a.kind_id, k.code, a.created_at
		FROM entity_kind_aliases a JOIN system_kinds k ON k.kind_id = a.kind_id
		ORDER BY a.alias_code`)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to query aliases")
		return
	}
	defer rows.Close()
	out := make([]kindAliasOut, 0)
	for rows.Next() {
		var a kindAliasOut
		var ts time.Time
		if err := rows.Scan(&a.AliasID, &a.AliasCode, &a.KindID, &a.KindCode, &ts); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scan alias")
			return
		}
		a.CreatedAt = ts.Format(time.RFC3339)
		out = append(out, a)
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": out, "total": len(out)})
}

// reassignEntityKind handles POST /v1/glossary/books/{book_id}/entities/{entity_id}/reassign-kind
// Body: {kind_id}. Moves one entity onto the target kind, re-keying its attributes.
func (s *Server) reassignEntityKind(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookUUID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	// reassign-kind is the core action of the unknown-kind REVIEW queue (editorial
	// curation), so it's an EDIT op — gating it at manage would lock editors out of
	// the review workflow. Incompatible-code attrs are dropped on rekey, but the
	// prior revision snapshot preserves them (recoverable via restore), making this
	// less destructive than the edit-tier child-deletes. (D-E0-1-NEEDMAP-REVIEW;
	// the lifecycle gate still requires an active book.)
	if !s.requireGrant(w, r.Context(), bookUUID, userID, grantclient.GrantEdit) {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	var in struct {
		KindID string `json:"kind_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.KindID == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "kind_id is required")
		return
	}
	// Validate the target kind up front so a bogus/non-existent kind_id is a clean
	// 400/404 rather than an FK-violation 500 from the UPDATE (review-impl #1).
	newKindID, perr := uuid.Parse(in.KindID)
	if perr != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "kind_id must be a UUID")
		return
	}
	err := s.reassignEntityKindCore(r.Context(), bookUUID, entityID, newKindID)
	switch {
	case errors.Is(err, errReassignKindNotFound):
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "target kind not found")
		return
	case errors.Is(err, errReassignEntityNotFound):
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found in this book")
		return
	case err != nil:
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "reassign failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"entity_id": entityID.String(), "kind_id": newKindID.String()})
}

// reassign sentinels (shared by the HTTP handler + the glossary_propose_reassign_kind
// confirm effect).
var (
	errReassignKindNotFound   = errors.New("target kind not found")         // → 404 / re-proposable
	errReassignEntityNotFound = errors.New("entity not found in this book") // → 404 / re-proposable
)

// reassignEntityKindCore validates the target kind (live, in-book) + the entity (live,
// in-book), then re-keys the entity onto the new kind in a transaction. Grant is the
// CALLER's concern. Single source of truth for the HTTP reassign handler and the
// confirm effect.
func (s *Server) reassignEntityKindCore(ctx context.Context, bookID, entityID, newKindID uuid.UUID) error {
	var kindExists bool
	if err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM book_kinds WHERE book_kind_id=$1 AND book_id=$2 AND deprecated_at IS NULL)`,
		newKindID, bookID,
	).Scan(&kindExists); err != nil {
		return err
	}
	if !kindExists {
		return errReassignKindNotFound
	}
	var exists bool
	if err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM glossary_entities WHERE entity_id=$1 AND book_id=$2 AND deleted_at IS NULL)`,
		entityID, bookID,
	).Scan(&exists); err != nil {
		return err
	}
	if !exists {
		return errReassignEntityNotFound
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	if err := s.rekeyEntityToKind(ctx, tx, entityID.String(), newKindID.String()); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// reassignKindDroppedCodes lists the attribute CODES currently on the entity that have
// NO counterpart in the target kind — i.e. the values reassign will DROP (data loss).
// 'name'/'term' are excluded because rekey maps the display value across them. Used to
// render the reassign confirm preview (§11 #10) from current state.
func (s *Server) reassignKindDroppedCodes(ctx context.Context, entityID, newKindID uuid.UUID) ([]string, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT DISTINCT od.code
		FROM entity_attribute_values eav
		JOIN book_attributes od ON od.attr_id = eav.attr_def_id
		WHERE eav.entity_id = $1
		  AND od.kind_id <> $2
		  AND od.code NOT IN ('name','term')
		  AND NOT EXISTS (
		    SELECT 1 FROM book_attributes nd
		    WHERE nd.kind_id = $2 AND nd.code = od.code
		  )
		ORDER BY od.code`, entityID, newKindID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	dropped := []string{}
	for rows.Next() {
		var code string
		if err := rows.Scan(&code); err != nil {
			return nil, err
		}
		dropped = append(dropped, code)
	}
	return dropped, rows.Err()
}

// rekeyEntityToKind moves an entity onto newKindID and RE-KEYS its attribute values
// by code (attr values are keyed by per-kind attr_def_id, so a kind change must remap
// them or the name/attrs would vanish). Values whose code has no counterpart in the
// new kind are dropped. Clears source_kind_code (no longer in the unknown bucket).
func (s *Server) rekeyEntityToKind(ctx context.Context, tx pgx.Tx, entityID, newKindID string) error {
	// 1. Re-point each attr value to the new kind's attr_def of the SAME code (book
	//    tier; attrs live under the universal genre, so resolve nd to that row).
	if _, err := tx.Exec(ctx, `
		UPDATE entity_attribute_values eav
		SET attr_def_id = nd.attr_id
		FROM book_attributes od,
		     LATERAL (
		       SELECT ba.attr_id FROM book_attributes ba
		       JOIN book_genres g ON g.genre_id = ba.genre_id
		       WHERE ba.kind_id = $2 AND ba.code = od.code
		       ORDER BY (g.code = 'universal') DESC, ba.sort_order LIMIT 1
		     ) nd
		WHERE eav.entity_id = $1
		  AND eav.attr_def_id = od.attr_id
		  AND od.kind_id <> $2`,
		entityID, newKindID,
	); err != nil {
		return err
	}
	// 1b. Preserve the DISPLAY value across kinds that use different display codes.
	//     display_name resolves from a 'name' OR 'term' attribute (entity_handler.go),
	//     so an entity whose name lives under 'name' (e.g. the unknown bucket) would
	//     lose it when moved onto a kind that uses 'term' (e.g. terminology). Map the
	//     leftover display value (still on a foreign kind) onto the target's display
	//     attr — preferring 'name' — but only when the exact re-key above didn't already
	//     place one there.
	if _, err := tx.Exec(ctx, `
		UPDATE entity_attribute_values eav
		SET attr_def_id = (
			SELECT ba.attr_id FROM book_attributes ba
			JOIN book_genres g ON g.genre_id = ba.genre_id
			WHERE ba.kind_id = $2 AND ba.code IN ('name','term')
			ORDER BY CASE ba.code WHEN 'name' THEN 0 ELSE 1 END,
			         (g.code = 'universal') DESC, ba.sort_order
			LIMIT 1
		)
		FROM book_attributes od
		WHERE eav.entity_id = $1
		  AND eav.attr_def_id = od.attr_id
		  AND od.kind_id <> $2
		  AND od.code IN ('name','term')
		  AND EXISTS (SELECT 1 FROM book_attributes WHERE kind_id = $2 AND code IN ('name','term'))
		  AND NOT EXISTS (
			SELECT 1 FROM entity_attribute_values x
			JOIN book_attributes xd ON xd.attr_id = x.attr_def_id
			WHERE x.entity_id = $1 AND xd.kind_id = $2 AND xd.code IN ('name','term')
		  )`,
		entityID, newKindID,
	); err != nil {
		return err
	}
	// 2. Drop any values whose code has no counterpart in the new kind (still point
	//    at a foreign kind's attr_def).
	if _, err := tx.Exec(ctx, `
		DELETE FROM entity_attribute_values eav
		USING book_attributes od
		WHERE eav.entity_id = $1 AND eav.attr_def_id = od.attr_id AND od.kind_id <> $2`,
		entityID, newKindID,
	); err != nil {
		return err
	}
	// 3. Move the entity + clear the unknown-bucket marker.
	tag, err := tx.Exec(ctx, `
		UPDATE glossary_entities SET kind_id = $2, source_kind_code = NULL, updated_at = now()
		WHERE entity_id = $1`,
		entityID, newKindID,
	)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return pgx.ErrNoRows
	}
	// D-GLOSSARY-ST-DEDUP M3a: re-keying moved the name/term value onto a different
	// attr_def (the trigger recomputed cached_name); re-stamp the dedup key so it
	// reflects the (possibly newly-resolved) name. Idempotent when unchanged.
	if eid, perr := uuid.Parse(entityID); perr == nil {
		if err := refreshEntityDedupKey(ctx, tx, eid); err != nil {
			return err
		}
	}
	return nil
}
