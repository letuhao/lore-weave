package api

import (
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/loreweave/grantclient"
)

// D-GLOSSARY-MULTIROW-ATTR-VALUES slice 3 — per-item verify/tombstone.
//
// PATCH /v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}/items/{item_id}
// Body: {"status": "active"|"tombstoned", "confidence": "machine"|"draft"|"verified"} (≥1 field).
//
// Flips a SINGLE list-item's status/confidence — the product win of the per-item model:
// reject one alias/tag while keeping the rest (tombstone), or mark one verified. The cache
// (original_value) is rebuilt from the ACTIVE items, so a tombstone drops the item from every
// reader for free; a verified item is then protected by the row-level verified-clobber guard
// once the whole value is verified (the per-item guard is a later enhancement). Atomic with
// the entity-updated event so glossary-sync→Neo4j and the staleness consumer see the change.

var validItemStatus = map[string]bool{"active": true, "tombstoned": true}
var validItemConfidence = map[string]bool{"machine": true, "draft": true, "verified": true}

func (s *Server) patchAttributeValueItem(w http.ResponseWriter, r *http.Request) {
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
	itemID, ok := parsePathUUID(w, r, "item_id")
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

	var in struct {
		Status     *string `json:"status"`
		Confidence *string `json:"confidence"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	if in.Status == nil && in.Confidence == nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "status and/or confidence required")
		return
	}
	if in.Status != nil && !validItemStatus[*in.Status] {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "status must be active|tombstoned")
		return
	}
	if in.Confidence != nil && !validItemConfidence[*in.Confidence] {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "confidence must be machine|draft|verified")
		return
	}

	ctx := r.Context()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "begin tx failed")
		return
	}
	defer tx.Rollback(ctx)

	// BEFORE snapshot for the user-correction event.
	beforeName, beforeKind, beforeAliases, beforeShortDesc, beforeOK :=
		loadEntityEventFields(ctx, tx, entityID)

	// Update the single item; the (item_id, attr_value_id) pair guards an item that doesn't
	// belong to this attr value → 0 rows → 404 (existence of attr_value already verified).
	setClauses := "updated_at = now()"
	args := []any{itemID, attrValueID}
	argN := 3
	if in.Status != nil {
		setClauses += fmt.Sprintf(", status = $%d", argN)
		args = append(args, *in.Status)
		argN++
	}
	if in.Confidence != nil {
		setClauses += fmt.Sprintf(", confidence = $%d", argN)
		args = append(args, *in.Confidence)
		argN++
	}
	tag, err := tx.Exec(ctx,
		`UPDATE entity_attribute_value_items SET `+setClauses+` WHERE item_id = $1 AND attr_value_id = $2`,
		args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update item failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "item not found for this attribute value")
		return
	}

	// Rebuild the cache from the ACTIVE items (INV-MR1) — a tombstone drops the item from
	// original_value, so every reader excludes it.
	if err := rebuildItemsCache(ctx, tx, attrValueID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "cache rebuild failed")
		return
	}
	// Bump the entity version so the edit is one coherent token + the AFTER snapshot reflects it.
	if _, err := tx.Exec(ctx, `UPDATE glossary_entities SET updated_at = now() WHERE entity_id = $1`, entityID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "entity bump failed")
		return
	}

	afterName, afterKind, afterAliases, afterShortDesc, _ := loadEntityEventFields(ctx, tx, entityID)
	var before *EntitySnapshot
	if beforeOK {
		before = &EntitySnapshot{
			Name:             beforeName,
			Kind:             beforeKind,
			Aliases:          beforeAliases,
			ShortDescription: beforeShortDesc,
		}
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

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"item_id": itemID.String(), "status": in.Status, "confidence": in.Confidence,
	})
}
