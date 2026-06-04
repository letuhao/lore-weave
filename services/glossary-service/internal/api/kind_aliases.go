package api

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// Kind-alias + unknown-bucket review endpoints (kind-resolution epic).
//
// When extract-entities can't resolve an incoming kind_code (neither a kind nor an
// alias), the entity is parked under the 'unknown' system kind and remembers the
// code it arrived as in source_kind_code (see extraction_handler.go). These handlers
// are the author's triage surface:
//   * listUnknownEntities  — GET the review queue for a book.
//   * listKindAliases      — GET the existing alias table (for the GUI).
//   * createKindAlias      — POST an alias (alias_code → kind), optionally reassigning
//                            the unknown entities that arrived as that code ("merge").
//   * reassignEntityKind   — POST move ONE entity to a kind (ad-hoc triage).
// "Create a new kind for it" is the existing POST /v1/glossary/kinds, then merge/reassign.

type unknownEntityOut struct {
	EntityID       string  `json:"entity_id"`
	Name           string  `json:"name"`
	SourceKindCode *string `json:"source_kind_code"`
	Status         string  `json:"status"`
	CreatedAt      string  `json:"created_at"`
}

// listUnknownEntities handles GET /v1/glossary/books/{book_id}/unknown-entities
func (s *Server) listUnknownEntities(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID := chi.URLParam(r, "book_id")

	rows, err := s.pool.Query(r.Context(), `
		SELECT e.entity_id, COALESCE(nv.original_value, ''), e.source_kind_code, e.status, e.created_at
		FROM glossary_entities e
		JOIN entity_kinds k ON k.kind_id = e.kind_id AND k.code = 'unknown'
		LEFT JOIN entity_attribute_values nv
			ON nv.entity_id = e.entity_id
			AND nv.attr_def_id = (
				SELECT attr_def_id FROM attribute_definitions
				WHERE kind_id = e.kind_id AND code = 'name' LIMIT 1
			)
		WHERE e.book_id = $1 AND e.deleted_at IS NULL
		ORDER BY e.created_at DESC
		LIMIT 500`,
		bookID,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to query unknown entities")
		return
	}
	defer rows.Close()
	out := make([]unknownEntityOut, 0)
	for rows.Next() {
		var e unknownEntityOut
		var ts time.Time
		if err := rows.Scan(&e.EntityID, &e.Name, &e.SourceKindCode, &e.Status, &ts); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scan unknown entity")
			return
		}
		e.CreatedAt = ts.Format(time.RFC3339)
		out = append(out, e)
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": out, "total": len(out)})
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
		FROM entity_kind_aliases a JOIN entity_kinds k ON k.kind_id = a.kind_id
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

// createKindAlias handles POST /v1/glossary/kind-aliases
// Body: {alias_code, kind_id, reassign?: bool, book_id?: uuid}
// Creates the alias; if reassign is true, also moves every 'unknown' entity whose
// source_kind_code == alias_code (optionally scoped to book_id) onto that kind.
func (s *Server) createKindAlias(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	var in struct {
		AliasCode string  `json:"alias_code"`
		KindID    string  `json:"kind_id"`
		Reassign  bool    `json:"reassign"`
		BookID    *string `json:"book_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.AliasCode == "" || in.KindID == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "alias_code and kind_id are required")
		return
	}
	// Refuse aliasing a code that is itself a real kind.code (the resolver checks
	// kinds first, so such an alias would be dead — fail loud instead).
	var clash bool
	if err := s.pool.QueryRow(r.Context(),
		`SELECT EXISTS(SELECT 1 FROM entity_kinds WHERE code = $1)`, in.AliasCode,
	).Scan(&clash); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "alias check failed")
		return
	}
	if clash {
		writeError(w, http.StatusConflict, "GLOSS_CONFLICT", "alias_code is already a kind code")
		return
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx begin failed")
		return
	}
	defer tx.Rollback(r.Context())

	var aliasID string
	err = tx.QueryRow(r.Context(), `
		INSERT INTO entity_kind_aliases (alias_code, kind_id, created_by)
		VALUES ($1, $2, $3) RETURNING alias_id`,
		in.AliasCode, in.KindID, uid,
	).Scan(&aliasID)
	if err != nil {
		writeError(w, http.StatusConflict, "GLOSS_CONFLICT", "alias already exists or kind not found")
		return
	}

	reassigned := 0
	if in.Reassign {
		ids, rerr := s.unknownEntityIDsBySourceCode(r.Context(), tx, in.AliasCode, in.BookID)
		if rerr != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "reassign lookup failed: "+rerr.Error())
			return
		}
		for _, eid := range ids {
			if err := s.rekeyEntityToKind(r.Context(), tx, eid, in.KindID); err != nil {
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "reassign failed: "+err.Error())
				return
			}
			reassigned++
		}
	}

	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx commit failed")
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"alias_id": aliasID, "alias_code": in.AliasCode, "kind_id": in.KindID, "reassigned": reassigned,
	})
}

// reassignEntityKind handles POST /v1/glossary/books/{book_id}/entities/{entity_id}/reassign-kind
// Body: {kind_id}. Moves one entity onto the target kind, re-keying its attributes.
func (s *Server) reassignEntityKind(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID := chi.URLParam(r, "book_id")
	entityID := chi.URLParam(r, "entity_id")
	var in struct {
		KindID string `json:"kind_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || in.KindID == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "kind_id is required")
		return
	}
	// Validate the target kind up front so a bogus/non-existent kind_id is a clean
	// 400/404 rather than an FK-violation 500 from the UPDATE (review-impl #1).
	if _, perr := uuid.Parse(in.KindID); perr != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "kind_id must be a UUID")
		return
	}
	var kindExists bool
	if err := s.pool.QueryRow(r.Context(),
		`SELECT EXISTS(SELECT 1 FROM entity_kinds WHERE kind_id=$1)`, in.KindID,
	).Scan(&kindExists); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "kind lookup failed")
		return
	}
	if !kindExists {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "target kind not found")
		return
	}
	// Confirm the entity exists in this book (scopes the action).
	var exists bool
	if err := s.pool.QueryRow(r.Context(),
		`SELECT EXISTS(SELECT 1 FROM glossary_entities WHERE entity_id=$1 AND book_id=$2 AND deleted_at IS NULL)`,
		entityID, bookID,
	).Scan(&exists); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "entity lookup failed")
		return
	}
	if !exists {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found in this book")
		return
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx begin failed")
		return
	}
	defer tx.Rollback(r.Context())
	if err := s.rekeyEntityToKind(r.Context(), tx, entityID, in.KindID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "reassign failed: "+err.Error())
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx commit failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"entity_id": entityID, "kind_id": in.KindID})
}

// unknownEntityIDsBySourceCode returns the unknown-bucket entity ids that arrived as
// the given source kind code (optionally scoped to a book).
func (s *Server) unknownEntityIDsBySourceCode(ctx context.Context, tx pgx.Tx, code string, bookID *string) ([]string, error) {
	q := `
		SELECT e.entity_id FROM glossary_entities e
		JOIN entity_kinds k ON k.kind_id = e.kind_id AND k.code = 'unknown'
		WHERE e.source_kind_code = $1 AND e.deleted_at IS NULL`
	args := []any{code}
	if bookID != nil {
		q += ` AND e.book_id = $2`
		args = append(args, *bookID)
	}
	rows, err := tx.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var ids []string
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

// rekeyEntityToKind moves an entity onto newKindID and RE-KEYS its attribute values
// by code (attr values are keyed by per-kind attr_def_id, so a kind change must remap
// them or the name/attrs would vanish). Values whose code has no counterpart in the
// new kind are dropped. Clears source_kind_code (no longer in the unknown bucket).
func (s *Server) rekeyEntityToKind(ctx context.Context, tx pgx.Tx, entityID, newKindID string) error {
	// 1. Re-point each attr value to the new kind's attr_def of the SAME code.
	if _, err := tx.Exec(ctx, `
		UPDATE entity_attribute_values eav
		SET attr_def_id = nd.attr_def_id
		FROM attribute_definitions od, attribute_definitions nd
		WHERE eav.entity_id = $1
		  AND eav.attr_def_id = od.attr_def_id
		  AND nd.kind_id = $2 AND nd.code = od.code
		  AND od.kind_id <> $2`,
		entityID, newKindID,
	); err != nil {
		return err
	}
	// 2. Drop any values whose code has no counterpart in the new kind (still point
	//    at a foreign kind's attr_def).
	if _, err := tx.Exec(ctx, `
		DELETE FROM entity_attribute_values eav
		USING attribute_definitions od
		WHERE eav.entity_id = $1 AND eav.attr_def_id = od.attr_def_id AND od.kind_id <> $2`,
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
	return nil
}
