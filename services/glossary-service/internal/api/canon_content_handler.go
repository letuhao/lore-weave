package api

// POST /internal/books/{book_id}/entities/{entity_id}/canon-content
//
// Sets the CANONICAL content (short_description column) on an EXISTING
// glossary entity. Service-to-service only (X-Internal-Token via the
// /internal route group).
//
// Why this exists (lore-enrichment DEFERRED-053 / Q2):
//   The lore-enrichment promote flow writes enriched lore back THROUGH the
//   glossary SSOT (Q2: "author through glossary; glossary_sync propagates to
//   Neo4j"). The entity ANCHOR is created identity-only at write-back time
//   (quarantine). On author-promote the approved content must land on the
//   glossary entity's canonical content so glossary_sync carries it to Neo4j
//   as source_type='glossary' canon.
//
//   The bulk extract-entities path CANNOT do this: short_description is a
//   COLUMN on glossary_entities (not an attribute_definition in the EAV
//   table), so extract-entities silently no-ops on it (no matching attr_def).
//   The user-facing PATCH entity endpoint CAN set it, but it is JWT-scoped
//   (owner Bearer token) and not reachable from a service-to-service promote
//   that has already verified ownership against book-service. This internal
//   endpoint closes that gap additively.
//
// H0 note: this endpoint only sets CANONICAL content on an EXISTING entity.
//   It is the glossary SSOT write that the promote flow performs AFTER the
//   author-only ownership check + the KG promote. It is never called
//   pre-promote (the anchor stays identity-only / quarantined until then),
//   so it cannot leak enriched content onto a canon entity before promotion.
//
// Behaviour mirrors the short_description branch of patchEntity:
//   - short_description is trimmed; an empty/whitespace string or explicit
//     null clears it (kept for symmetry, though promote always sends content).
//   - capped at 500 runes (matches the DB CHECK + patchEntity).
//   - short_description_auto is set false (user/author-authored, sticky —
//     backfill/auto-regen must never overwrite it; same K3.3a rule as PATCH).
//   - emits glossary.entity_updated (op="updated") best-effort so the C4/K14
//     pipeline -> knowledge-service glossary_sync -> Neo4j propagation runs.

import (
	"encoding/json"
	"net/http"
	"strings"
	"unicode/utf8"
)

type canonContentRequest struct {
	// ShortDescription is the canonical content to write. A nil pointer or a
	// trimmed-empty string clears the field (parity with patchEntity).
	ShortDescription *string `json:"short_description"`
}

// internalSetCanonContent sets short_description on an existing entity.
//
//	POST /internal/books/{book_id}/entities/{entity_id}/canon-content
func (s *Server) internalSetCanonContent(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}

	var req canonContentRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON body")
		return
	}

	// Normalise: trim, cap at 500 runes, empty → NULL (clears). Same rules as
	// the patchEntity short_description branch so behaviour is identical
	// regardless of which write path set the value.
	var sdPtr *string
	if req.ShortDescription != nil {
		sd := strings.TrimSpace(*req.ShortDescription)
		if utf8.RuneCountInString(sd) > 500 {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_SHORT_DESCRIPTION",
				"short_description must be at most 500 characters")
			return
		}
		if sd != "" {
			sdPtr = &sd
		}
	}

	ctx := r.Context()
	// Mark short_description_auto=false (author-authored, sticky) exactly like
	// the user PATCH path. Scope on book_id + not-deleted so a stale/cross-book
	// entity_id is a 404 rather than a silent no-op on the wrong row.
	tag, err := s.pool.Exec(ctx,
		`UPDATE glossary_entities
		    SET short_description = $1,
		        short_description_auto = false,
		        updated_at = now()
		  WHERE entity_id = $2 AND book_id = $3 AND deleted_at IS NULL`,
		sdPtr, entityID, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found")
		return
	}

	// C4 (K14) — canonical content changed → emit best-effort (already
	// committed via pool.Exec; fire-and-forget so a broker hiccup can't fail
	// a successful write). This drives glossary_sync -> Neo4j (Q2 path):
	// knowledge-service merges the entity with source_type='glossary',
	// confidence=1.0, carrying this short_description.
	s.emitEntityUpdated(ctx, entityID, "updated")

	writeJSON(w, http.StatusOK, map[string]any{
		"entity_id":         entityID.String(),
		"book_id":           bookID.String(),
		"short_description": sdPtr,
	})
}
