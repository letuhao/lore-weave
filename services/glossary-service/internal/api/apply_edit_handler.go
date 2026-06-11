package api

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strings"
	"unicode/utf8"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/loreweave/grantclient"
)

// EDIT-ATOMIC — POST /v1/glossary/books/{book_id}/entities/{entity_id}/apply-edit
//
// The assistant's diff card proposes several field changes at once + the
// base_version it read; this applies them ALL in ONE transaction with ONE
// optimistic-concurrency check (H5). A multi-field edit is therefore atomic — no
// partial write on failure, and no false 412 that sequential single-field PATCHes
// (against one base_version) would produce. The P3 single-field /v1 PATCH
// endpoints (patchEntity / patchAttributeValue + If-Match) are untouched; the
// manual UI keeps using them.

type applyEditAttr struct {
	AttrValueID   string `json:"attr_value_id"`
	OriginalValue string `json:"original_value"`
}

func (s *Server) applyEntityEdit(w http.ResponseWriter, r *http.Request) {
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

	// Decode raw so `short_description` presence (incl. explicit null = clear) is
	// distinguishable from absence (leave untouched) — same convention as patchEntity.
	var raw map[string]json.RawMessage
	if err := json.NewDecoder(r.Body).Decode(&raw); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}

	base := ""
	if rb, ok := raw["base_version"]; ok {
		_ = json.Unmarshal(rb, &base)
	}
	base = strings.TrimSpace(base)
	if base == "" {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "base_version is required")
		return
	}

	var attrs []applyEditAttr
	if ra, ok := raw["attributes"]; ok {
		if err := json.Unmarshal(ra, &attrs); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid attributes")
			return
		}
	}

	// short_description: nullable; explicit null OR trimmed-empty clears it.
	var shortDescPtr *string
	hasShortDesc := false
	if rs, ok := raw["short_description"]; ok {
		hasShortDesc = true
		if string(rs) != "null" {
			var sd string
			if err := json.Unmarshal(rs, &sd); err != nil {
				writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "short_description must be string or null")
				return
			}
			sd = strings.TrimSpace(sd)
			if utf8.RuneCountInString(sd) > 500 {
				writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_SHORT_DESCRIPTION",
					"short_description must be at most 500 characters")
				return
			}
			if sd != "" {
				shortDescPtr = &sd
			}
		}
	}

	if !hasShortDesc && len(attrs) == 0 {
		writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "no changes to apply")
		return
	}

	// Parse + validate attr ids up front.
	attrIDs := make([]uuid.UUID, 0, len(attrs))
	for _, a := range attrs {
		id, err := uuid.Parse(a.AttrValueID)
		if err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_VALIDATION", "attr_value_id must be a UUID")
			return
		}
		attrIDs = append(attrIDs, id)
	}

	ctx := r.Context()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "begin tx failed")
		return
	}
	defer tx.Rollback(ctx)

	// ── H5 version gate: lock the row + compare in one shot. ──
	var versionMatch bool
	err = tx.QueryRow(ctx, `
		SELECT (updated_at = $3::timestamptz)
		FROM glossary_entities
		WHERE entity_id = $1 AND book_id = $2
		FOR UPDATE`,
		entityID, bookID, base,
	).Scan(&versionMatch)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "version check failed")
		return
	}
	if !versionMatch {
		writeError(w, http.StatusPreconditionFailed, "GLOSS_VERSION_CONFLICT",
			"entity changed since it was read; re-open and try again")
		return
	}

	// Capture BEFORE (pre-edit) snapshot in-tx for the event.
	beforeName, beforeKind, beforeAliases, beforeShortDesc, beforeOK := loadEntityEventFields(ctx, tx, entityID)
	var before *EntitySnapshot
	if beforeOK {
		before = &EntitySnapshot{Name: beforeName, Kind: beforeKind, Aliases: beforeAliases, ShortDescription: beforeShortDesc}
	}

	// short_description (entity-level). User write → mark not-auto so backfill/
	// auto-regen never overwrites the choice (K3.3a).
	if hasShortDesc {
		if _, err := tx.Exec(ctx,
			`UPDATE glossary_entities SET short_description = $1, short_description_auto = false WHERE entity_id = $2`,
			shortDescPtr, entityID); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update short_description failed")
			return
		}
	}

	// Attribute values — each scoped to this entity (RowsAffected guards an
	// attr_value_id that doesn't belong → 422, whole tx rolls back).
	for i, a := range attrs {
		tag, err := tx.Exec(ctx,
			`UPDATE entity_attribute_values SET original_value = $1 WHERE attr_value_id = $2 AND entity_id = $3`,
			a.OriginalValue, attrIDs[i], entityID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update attribute failed")
			return
		}
		if tag.RowsAffected() == 0 {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_ATTRIBUTE",
				"attribute does not belong to this entity")
			return
		}
	}

	// Did any changed attribute carry the 'description' code? (drives the
	// post-commit short_description auto-regen, at patchAttributeValue parity.)
	descriptionChanged := false
	if len(attrIDs) > 0 {
		if err := tx.QueryRow(ctx, `
			SELECT EXISTS(
				SELECT 1 FROM entity_attribute_values eav
				JOIN attribute_definitions ad ON ad.attr_def_id = eav.attr_def_id
				WHERE eav.attr_value_id = ANY($1) AND ad.code = 'description')`,
			attrIDs).Scan(&descriptionChanged); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "attr lookup failed")
			return
		}
	}

	// One updated_at bump for the whole edit (the single H5 version token).
	if _, err := tx.Exec(ctx,
		`UPDATE glossary_entities SET updated_at = now() WHERE entity_id = $1`, entityID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "version bump failed")
		return
	}

	// AFTER snapshot (cached_name/aliases already refreshed by the K2a trigger on
	// the EAV writes) + ONE transactional glossary.entity_updated event.
	afterName, afterKind, afterAliases, afterShortDesc, _ := loadEntityEventFields(ctx, tx, entityID)
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

	// K3.3b parity: if the description attr changed and short_description is still
	// auto, regenerate it (best-effort, post-commit, never fails the request).
	if descriptionChanged {
		if err := s.regenerateAutoShortDescription(ctx, entityID); err != nil {
			slog.Warn("apply-edit: regenerate short_description failed",
				"entity_id", entityID.String(), "error", err.Error())
		}
	}

	detail, err := s.loadEntityDetail(ctx, bookID, entityID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
		return
	}
	writeJSON(w, http.StatusOK, detail)
}
