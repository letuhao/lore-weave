package api

// Internal endpoints for the #26/#7 `summarize` merge-rewrite mode's CANONICAL layer.
//
// The summarize writeback (mergeExtractedEntity) keeps the lossless RAW item layer that
// append maintains AND flags entity_attribute_values.canonical_dirty whenever a summarize
// attribute's raw set changes. These two service-to-service endpoints (X-Internal-Token,
// via the /internal route group) drive the decoupled, end-of-extraction-job LLM pass that
// rewrites the accumulated raw mentions into one deduped canonical_value:
//
//   GET  /internal/books/{book_id}/canonical-dirty           → the dirty work items
//   POST /internal/books/{book_id}/entities/{entity_id}/canonical → write the synthesized value
//
// The LLM call itself lives in translation-service's extraction worker (which already holds
// the job's llm_client + model_ref + provider-registry routing) — glossary never calls an LLM
// (provider-gateway invariant) and never runs an LLM inside the writeback tx.

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"unicode/utf8"

	"github.com/loreweave/glossary-service/internal/sanitize"
)

// canonicalMaxRunes caps a synthesized canonical value. It is a merged description (longer
// than a short_description's 500), but still bounded so a runaway LLM output can't bloat a row.
const canonicalMaxRunes = 2000

// defaultCanonicalDirtyLimit bounds the dirty-work response so a book with many summarize
// attributes can't return an unbounded payload in one call (the worker re-polls if needed).
const defaultCanonicalDirtyLimit = 500
const maxCanonicalDirtyLimit = 2000

// canonicalDirtyItem is one (entity, summarize-attribute) unit awaiting resynthesis.
type canonicalDirtyItem struct {
	EntityID       string   `json:"entity_id"`
	EntityName     string   `json:"entity_name"`
	AttrCode       string   `json:"attr_code"`
	AttrLabel      string   `json:"attr_label"`
	RawValues      []string `json:"raw_values"`
	SourceLanguage string   `json:"source_language"`
	// RawFingerprint pins the raw set the worker is about to summarize. It is echoed back
	// on the write so the dirty flag is cleared with COMPARE-AND-CLEAR semantics: if a
	// concurrent extraction appended a new raw mention between this fetch and the write,
	// the fingerprints differ and the row stays dirty for the next pass (no lost update).
	RawFingerprint string `json:"raw_fingerprint"`
}

// internalCanonicalDirty lists the summarize attributes whose canonical value is stale.
//
//	GET /internal/books/{book_id}/canonical-dirty?limit=N
func (s *Server) internalCanonicalDirty(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	limit := defaultCanonicalDirtyLimit
	if q := strings.TrimSpace(r.URL.Query().Get("limit")); q != "" {
		if n, err := strconv.Atoi(q); err == nil && n > 0 {
			limit = n
		}
	}
	if limit > maxCanonicalDirtyLimit {
		limit = maxCanonicalDirtyLimit
	}

	ctx := r.Context()
	rows, err := s.pool.Query(ctx, `
		SELECT ge.entity_id, COALESCE(ge.cached_name, ''), ba.code, COALESCE(ba.name, ba.code),
		       eav.original_value, COALESCE(eav.original_language, ''), md5(eav.original_value)
		  FROM entity_attribute_values eav
		  JOIN glossary_entities ge ON ge.entity_id = eav.entity_id
		  JOIN book_attributes ba ON ba.attr_id = eav.attr_def_id
		 WHERE ge.book_id = $1 AND ge.deleted_at IS NULL
		   AND eav.canonical_dirty = true
		   AND ba.merge_strategy = 'summarize'
		 ORDER BY ge.entity_id, ba.sort_order
		 LIMIT $2`, bookID, limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer rows.Close()

	items := make([]canonicalDirtyItem, 0)
	for rows.Next() {
		var (
			entityID, name, code, label, rawVal, lang, fp string
		)
		if err := rows.Scan(&entityID, &name, &code, &label, &rawVal, &lang, &fp); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return
		}
		// original_value is the write-synced cache of the ACTIVE raw items (a JSON array for
		// list attrs; a bare scalar for a legacy single value). parseListValue handles both.
		raw := parseListValue(rawVal)
		if len(raw) == 0 {
			// A dirty row with no parseable raw value is nothing to summarize — skip it
			// (defensive: the writeback only dirties on a real append, so this is rare).
			continue
		}
		items = append(items, canonicalDirtyItem{
			EntityID:       entityID,
			EntityName:     name,
			AttrCode:       code,
			AttrLabel:      label,
			RawValues:      raw,
			SourceLanguage: lang,
			RawFingerprint: fp,
		})
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "iteration failed")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"book_id": bookID.String(),
		"items":   items,
		"count":   len(items),
	})
}

type writeCanonicalRequest struct {
	AttrCode       string `json:"attr_code"`
	CanonicalValue string `json:"canonical_value"`
	// RawFingerprint, when present, enables compare-and-clear: the dirty flag is cleared
	// only if the row's current raw set still hashes to this value. An empty fingerprint
	// clears dirty unconditionally (the caller opts out of the race guard).
	RawFingerprint string `json:"raw_fingerprint"`
}

// internalWriteCanonical stores the LLM-synthesized canonical value on a summarize attribute
// and clears canonical_dirty with compare-and-clear semantics.
//
//	POST /internal/books/{book_id}/entities/{entity_id}/canonical
func (s *Server) internalWriteCanonical(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	entityID, ok := parsePathUUID(w, r, "entity_id")
	if !ok {
		return
	}

	var req writeCanonicalRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON body")
		return
	}
	code := strings.TrimSpace(req.AttrCode)
	if code == "" {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "attr_code is required")
		return
	}

	// Untrusted LLM text → DATA, never instructions: neutralize structural injection markers
	// (chat-template / role-spoof tokens, zero-width smuggling) HERE, independent of the
	// caller — same canon-boundary defense as internalSetCanonContent. Neutralize BEFORE the
	// rune-cap (the inert placeholder changes length, and the stored value must satisfy it).
	cv := sanitize.NeutralizeCanonText(req.CanonicalValue)
	cv = strings.TrimSpace(cv)
	if utf8.RuneCountInString(cv) > canonicalMaxRunes {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_CANONICAL",
			"canonical_value exceeds the length cap")
		return
	}
	var cvPtr *string
	if cv != "" {
		cvPtr = &cv
	}

	ctx := r.Context()
	// Compare-and-clear: stay dirty if a concurrent extraction changed the raw set since the
	// fetch (fingerprint mismatch), else clear. An empty fingerprint clears unconditionally.
	// Scoped to book + the summarize attr so a stale/cross-book entity or a non-summarize
	// attr is a clean 404 rather than a silent write on the wrong row.
	tag, err := s.pool.Exec(ctx, `
		UPDATE entity_attribute_values eav
		   SET canonical_value = $1,
		       canonical_synced_at = now(),
		       canonical_dirty = ($2 <> '' AND md5(eav.original_value) <> $2)
		  FROM glossary_entities ge, book_attributes ba
		 WHERE eav.entity_id = ge.entity_id
		   AND eav.attr_def_id = ba.attr_id
		   AND ge.entity_id = $3 AND ge.book_id = $4 AND ge.deleted_at IS NULL
		   AND ba.code = $5 AND ba.merge_strategy = 'summarize'`,
		cvPtr, req.RawFingerprint, entityID, bookID, code)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND",
			"summarize attribute not found for this entity")
		return
	}

	// The canonical value is the entity's headline description for this attribute → emit
	// best-effort so the C4/K14 glossary_sync → Neo4j anchor + staleness refresh runs.
	s.emitEntityUpdated(ctx, entityID, "updated")

	writeJSON(w, http.StatusOK, map[string]any{
		"entity_id":       entityID.String(),
		"book_id":         bookID.String(),
		"attr_code":       code,
		"canonical_value": cvPtr,
	})
}
