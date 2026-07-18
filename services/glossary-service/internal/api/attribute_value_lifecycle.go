package api

// S-06 — glossary attribute-value LIFECYCLE the editor was missing: ADD a value for an
// attr-def that was added to the ontology AFTER the entity existed (until now only the MCP
// `glossary_entity_set_attributes` path could fill it — "an LLM can, you can't"), and DELETE
// a value ROW (not just blank it to empty, which PATCH already does).
//
// Both mirror `patchAttributeValue`'s discipline: grant-gated EDIT, book/entity scoped, and — in
// ONE transaction — the write + a `glossary_entities.updated_at` bump + the `entity_updated`
// outbox event the staleness / glossary_sync→Neo4j / learning consumers need.

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/loreweave/grantclient"
)

// ── POST /v1/glossary/books/{book_id}/entities/{entity_id}/attributes
//
// Add a value row for a post-create attr-def. 201 with the new value; 409 if a value row for
// (entity, attr_def) already exists (PATCH is the edit path); 422 if the attr-def is not
// applicable to this entity (wrong kind / not in the entity's genres / deprecated).
func (s *Server) addAttributeValue(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
		return
	}
	if !s.verifyEntityInBook(w, r.Context(), entityID, bookID) {
		return
	}

	var in struct {
		AttributeDefID string `json:"attribute_def_id"`
		Value          string `json:"value"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	if strings.TrimSpace(in.AttributeDefID) == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "attribute_def_id is required")
		return
	}
	attrDefID, err := uuid.Parse(strings.TrimSpace(in.AttributeDefID))
	if err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "attribute_def_id must be a UUID")
		return
	}

	ctx := r.Context()

	// SD-1 — applicability: the attr-def must belong to THIS entity's KIND and not be deprecated.
	// The FK only checks existence, so without the kind match a client could attach another
	// kind's attr. Genre is a seeding-time refinement of WHICH kind-attrs are pre-created, not an
	// add-time gate: universal-genre attrs (e.g. `name`) apply to an entity that carries no
	// explicit `entity_genres` row, so gating add on genre would wrongly 422 them. Returning the
	// code (not just EXISTS) also drives the description/name post-write hooks.
	var attrCode string
	err = s.pool.QueryRow(ctx, `
		SELECT ba.code
		FROM book_attributes ba
		JOIN glossary_entities e ON e.entity_id = $2
		WHERE ba.attr_id = $1
		  AND ba.kind_id = e.kind_id
		  AND ba.deprecated_at IS NULL`,
		attrDefID, entityID,
	).Scan(&attrCode)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_ATTR_DEF",
			"attribute is not on this entity's kind/genres (or is deprecated)")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "attr-def lookup failed")
		return
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "begin tx failed")
		return
	}
	defer tx.Rollback(ctx)

	beforeName, beforeKind, beforeAliases, beforeShortDesc, beforeOK := loadEntityEventFields(ctx, tx, entityID)

	// INSERT-or-409: an explicit ADD must not silently overwrite an existing value (that is
	// PATCH's job). ON CONFLICT DO NOTHING → no RETURNING row → ErrNoRows → 409. Marked
	// 'verified' (a human-directed write) so INV-8's verified-clobber guard protects it.
	var attrValueID uuid.UUID
	err = tx.QueryRow(ctx, `
		INSERT INTO entity_attribute_values (entity_id, attr_def_id, original_language, original_value, confidence)
		VALUES ($1, $2, 'und', $3, 'verified')
		ON CONFLICT (entity_id, attr_def_id) DO NOTHING
		RETURNING attr_value_id`,
		entityID, attrDefID, in.Value,
	).Scan(&attrValueID)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusConflict, "GLOSS_ATTR_VALUE_EXISTS",
			"a value for this attribute already exists; edit it instead")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "insert failed")
		return
	}

	// Parity with the PATCH/MCP write path: sync per-item child rows for a LIST value
	// (scalar ⇒ no-op), stamped 'verified'.
	if err := syncListItemsByID(ctx, tx, attrValueID, in.Value, "verified", nil); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "item sync failed")
		return
	}
	// A 'description' add refreshes the auto short_description (only if still auto); a
	// 'name'/'term' add moves the dedup key (both mirror patchAttributeValue).
	if attrCode == "description" {
		if err := s.regenerateAutoShortDescription(ctx, tx, entityID); err != nil {
			slog.Warn("add-attr: regen short_description failed (non-fatal)",
				"entity_id", entityID.String(), "error", err.Error())
		}
	}
	if attrCode == "name" || attrCode == "term" {
		if err := refreshEntityDedupKey(ctx, tx, entityID); err != nil {
			if errors.Is(err, errDuplicateName) {
				writeError(w, http.StatusConflict, "GLOSS_DUPLICATE_NAME",
					"an entity with this name already exists in this book")
				return
			}
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "dedup key refresh failed")
			return
		}
	}

	if _, err := tx.Exec(ctx, `UPDATE glossary_entities SET updated_at = now() WHERE entity_id = $1`, entityID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "version bump failed")
		return
	}

	afterName, afterKind, afterAliases, afterShortDesc, _ := loadEntityEventFields(ctx, tx, entityID)
	var before *EntitySnapshot
	if beforeOK {
		before = &EntitySnapshot{Name: beforeName, Kind: beforeKind, Aliases: beforeAliases, ShortDescription: beforeShortDesc}
	}
	payload := buildEntityEventPayload(
		bookID.String(), entityID.String(),
		afterName, afterKind, afterAliases, afterShortDesc, "updated",
		"user", userID.String(), before,
	)
	if err := emitEntityUpdatedTx(ctx, tx, entityID, payload); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "outbox emit failed")
		return
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}

	av, err := s.scanAttrValueBasic(ctx, attrValueID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	writeJSON(w, http.StatusCreated, av)
}

// ── DELETE /v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}
//
// Remove the value ROW entirely — distinct from PATCH-to-empty (which keeps the row blank).
// Children (translations, list items, evidences) go via ON DELETE CASCADE. Mirrors the PATCH
// post-write hooks (short_description regen / dedup-key refresh) so the entity snapshot stays
// consistent, and emits the entity_updated event. 204.
func (s *Server) deleteAttributeValue(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}
	attrValueID, ok := parsePathUUID(w, r, "attr_value_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantEdit) {
		return
	}
	if !s.verifyEntityInBook(w, r.Context(), entityID, bookID) {
		return
	}
	if !s.verifyAttrValueInEntity(w, r.Context(), attrValueID, entityID) {
		return
	}

	ctx := r.Context()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "begin tx failed")
		return
	}
	defer tx.Rollback(ctx)

	// The attr code, read BEFORE the row is gone, drives the same post-write hooks as PATCH.
	var attrCode string
	if err := tx.QueryRow(ctx, `
		SELECT ad.code FROM entity_attribute_values eav
		JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
		WHERE eav.attr_value_id = $1`, attrValueID).Scan(&attrCode); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "attr code lookup failed")
		return
	}

	beforeName, beforeKind, beforeAliases, beforeShortDesc, beforeOK := loadEntityEventFields(ctx, tx, entityID)

	tag, err := tx.Exec(ctx,
		`DELETE FROM entity_attribute_values WHERE attr_value_id = $1 AND entity_id = $2`,
		attrValueID, entityID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	if tag.RowsAffected() == 0 {
		// verifyAttrValueInEntity already confirmed it exists; 0 rows ⇒ a concurrent delete race.
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "attribute value not found")
		return
	}

	// The EAV trigger recomputes cached_name on this delete; keep the app-maintained pieces in
	// step (parity with patchAttributeValue): a name/term removal moves the dedup key, a
	// description removal refreshes the auto short_description.
	if attrCode == "name" || attrCode == "term" {
		if err := refreshEntityDedupKey(ctx, tx, entityID); err != nil {
			if errors.Is(err, errDuplicateName) {
				writeError(w, http.StatusConflict, "GLOSS_DUPLICATE_NAME",
					"another entity would collide on this name; resolve it first")
				return
			}
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "dedup key refresh failed")
			return
		}
	}
	if attrCode == "description" {
		if err := s.regenerateAutoShortDescription(ctx, tx, entityID); err != nil {
			slog.Warn("delete-attr: regen short_description failed (non-fatal)",
				"entity_id", entityID.String(), "error", err.Error())
		}
	}

	if _, err := tx.Exec(ctx, `UPDATE glossary_entities SET updated_at = now() WHERE entity_id = $1`, entityID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "version bump failed")
		return
	}

	afterName, afterKind, afterAliases, afterShortDesc, _ := loadEntityEventFields(ctx, tx, entityID)
	var before *EntitySnapshot
	if beforeOK {
		before = &EntitySnapshot{Name: beforeName, Kind: beforeKind, Aliases: beforeAliases, ShortDescription: beforeShortDesc}
	}
	payload := buildEntityEventPayload(
		bookID.String(), entityID.String(),
		afterName, afterKind, afterAliases, afterShortDesc, "updated",
		"user", userID.String(), before,
	)
	if err := emitEntityUpdatedTx(ctx, tx, entityID, payload); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "outbox emit failed")
		return
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}
