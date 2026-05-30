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

	"github.com/loreweave/glossary-service/internal/sanitize"
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

	// Normalise: neutralize injection, trim, cap at 500 runes, empty → NULL.
	//
	// WARN-2 (canon-boundary defense-in-depth, 050/C12): this endpoint exists to
	// carry enriched LLM short_description INTO canon. Untrusted LLM text must be
	// treated as DATA, never instructions — so we neutralize structural injection
	// markers (chat-template / role-spoof tokens, zero-width smuggling) HERE,
	// independent of the caller's own neutralization. NFC-safe: 封神演义 names pass
	// through untouched. Neutralization runs BEFORE the rune-cap because the
	// inert placeholder changes length, and the stored value must satisfy the cap.
	var sdPtr *string
	if req.ShortDescription != nil {
		sd := sanitize.NeutralizeCanonText(*req.ShortDescription)
		sd = strings.TrimSpace(sd)
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

// internalGetCanonContent reads the canonical short_description COLUMN of an
// existing entity.
//
//	GET /internal/books/{book_id}/entities/{entity_id}/canon-content
//
// Used by the lore-enrichment re-promote SELF-HEAL (adversary WARN-1): the
// idempotent re-promote branch reads this to decide whether a prior
// canon-content write actually landed. A NULL short_description (or a 404 for a
// missing entity) signals the caller to re-write the canon content, so a
// re-promote becomes the real recovery path for a transiently-failed write.
func (s *Server) internalGetCanonContent(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}

	ctx := r.Context()
	var sd *string
	err := s.pool.QueryRow(ctx,
		`SELECT short_description
		   FROM glossary_entities
		  WHERE entity_id = $1 AND book_id = $2 AND deleted_at IS NULL`,
		entityID, bookID).Scan(&sd)
	if err != nil {
		// pgx returns ErrNoRows for a missing/cross-book/deleted entity → 404,
		// mirroring the set path's not-found semantics.
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "entity not found")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"entity_id":         entityID.String(),
		"book_id":           bookID.String(),
		"short_description": sd,
	})
}
