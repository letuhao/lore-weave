package api

import (
	"context"
	"database/sql"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"slices"
	"strconv"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/loreweave/grantclient"
	"github.com/loreweave/glossary-service/internal/textnorm"
)

// pgxRWQuerier is the read+write querier shared by *pgxpool.Pool and pgx.Tx —
// like pgxExecQuerier (attribute_handler.go) but also exposes multi-row Query,
// so the extraction writeback's resolver/create/merge helpers run either
// standalone on the pool (the MCP propose-entity path) OR enlisted in the
// per-chapter writeback transaction (bulkExtractEntities), where every write
// for a chapter must commit or roll back as one unit (INV-C1). (The package's
// existing pgxQuerier in outbox.go is read-only QueryRow; extraction needs all three.)
type pgxRWQuerier interface {
	Query(ctx context.Context, sql string, args ...any) (pgx.Rows, error)
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
	Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error)
}

// extractionWritebackLockNS namespaces the per-book advisory lock taken around a
// whole-chapter extraction writeback (INV-C1: per-book serialized). The 2-key
// pg_advisory_xact_lock(ns, hashtext(book)) form keeps extraction locks from
// colliding with the migration lock or any single-key advisory use elsewhere.
// Value is the ASCII bytes of "EXTW".
const extractionWritebackLockNS int32 = 0x45585457

// getExtractionProfile auto-resolves entity kinds + attributes for extraction
// based on the book's genre groups. JWT + book grant (public route only).
//
//   - Public:   GET /v1/glossary/books/{book_id}/extraction-profile
//   - Internal: GET /internal/books/{book_id}/extraction-profile → internalExtractionProfile
func (s *Server) getExtractionProfile(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
		return
	}
	s.writeExtractionProfile(w, r.Context(), bookID)
}

// internalExtractionProfile serves workers (translation-service) via X-Internal-Token
// only — no JWT. Must not delegate to getExtractionProfile (that broke extraction
// jobs: kinds_metadata empty → 0 LLM batches).
func (s *Server) internalExtractionProfile(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	s.writeExtractionProfile(w, r.Context(), bookID)
}

func (s *Server) writeExtractionProfile(w http.ResponseWriter, ctx context.Context, bookID uuid.UUID) {
	// G4: the extraction profile is BOOK-LOCAL (sovereign instance). A book MUST be
	// adopted (book_kinds populated) before extraction can run — an un-adopted book
	// yields zero kinds, which the worker treats as "book not scaffolded".
	//
	// 1. The book's ACTIVE genres (book_active_genres) drive attribute auto-selection.
	//    `universal` is mandatory + always-active (O4) even if not explicitly active.
	gRows, err := s.pool.Query(ctx, `
		SELECT bg.genre_id, bg.code
		FROM book_active_genres bag
		JOIN book_genres bg ON bg.genre_id = bag.genre_id
		WHERE bag.book_id = $1 AND bg.deprecated_at IS NULL`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to fetch genres")
		return
	}
	activeGenreIDs := map[uuid.UUID]struct{}{}
	for gRows.Next() {
		var id uuid.UUID
		var code string
		if err := gRows.Scan(&id, &code); err != nil {
			gRows.Close()
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scan genre")
			return
		}
		activeGenreIDs[id] = struct{}{}
	}
	gRows.Close()

	// 2. Fetch all book kinds (book-local). All adopted/native book kinds are
	//    auto-selected (the user already scaffolded them); is_hidden kinds excluded.
	kindRows, err := s.pool.Query(ctx, `
		SELECT book_kind_id, code, name, icon, description
		FROM book_kinds
		WHERE book_id = $1 AND is_hidden = false AND deprecated_at IS NULL
		ORDER BY sort_order, name
	`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to fetch kinds")
		return
	}
	defer kindRows.Close()

	type attrOut struct {
		Code           string  `json:"code"`
		Name           string  `json:"name"`
		FieldType      string  `json:"field_type"`
		Description    *string `json:"description"`
		AutoFillPrompt *string `json:"auto_fill_prompt"`
		IsRequired     bool    `json:"is_required"`
		AutoSelected   bool    `json:"auto_selected"`
	}
	type kindOut struct {
		KindID       string    `json:"kind_id"`
		Code         string    `json:"code"`
		Name         string    `json:"name"`
		Description  *string   `json:"description"` // bug #33 — fed to the extraction prompt so the model picks the right kind
		Icon         string    `json:"icon"`
		AutoSelected bool      `json:"auto_selected"`
		Attributes   []attrOut `json:"attributes"`
	}

	var kinds []kindOut
	for kindRows.Next() {
		var kindID uuid.UUID
		var code, name, icon string
		var description *string
		if err := kindRows.Scan(&kindID, &code, &name, &icon, &description); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scan kind")
			return
		}

		// Book kinds are book-local → always auto-selected for extraction.
		// Fetch attributes for this kind from book_attributes, carrying the genre so
		// auto-selection can honour the book's active genres.
		attrRows, err := s.pool.Query(ctx, `
			SELECT ba.code, ba.name, ba.field_type, ba.description, ba.auto_fill_prompt,
			       ba.is_required, ba.genre_id, (g.code = 'universal') AS is_universal
			FROM book_attributes ba
			JOIN book_genres g ON g.genre_id = ba.genre_id
			WHERE ba.book_id = $1 AND ba.kind_id = $2 AND ba.deprecated_at IS NULL
			ORDER BY ba.sort_order, ba.name
		`, bookID, kindID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to fetch attributes")
			return
		}

		var attrs []attrOut
		for attrRows.Next() {
			var a attrOut
			var genreID uuid.UUID
			var isUniversal bool
			if err := attrRows.Scan(&a.Code, &a.Name, &a.FieldType, &a.Description,
				&a.AutoFillPrompt, &a.IsRequired, &genreID, &isUniversal); err != nil {
				attrRows.Close()
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scan attribute")
				return
			}
			// Auto-select when:
			//   - is_required → always (mandatory attr), OR
			//   - the attr's genre is `universal` (O4 — always-active base attrs), OR
			//   - the attr's genre is one of the book's active genres.
			_, genreActive := activeGenreIDs[genreID]
			a.AutoSelected = a.IsRequired || isUniversal || genreActive
			attrs = append(attrs, a)
		}
		attrRows.Close()

		if attrs == nil {
			attrs = []attrOut{}
		}
		kinds = append(kinds, kindOut{
			KindID:       kindID.String(),
			Code:         code,
			Name:         name,
			Description:  description,
			Icon:         icon,
			AutoSelected: true,
			Attributes:   attrs,
		})
	}

	if kinds == nil {
		kinds = []kindOut{}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"kinds":         kinds,
		"saved_profile": nil, // saved_profile lives on books table (book-service); frontend has it from GET /books/{id}
	})
}

// getKnownEntities returns filtered entities for extraction prompt context.
// 3-layer filtering: alive flag, frequency (chapter_entity_links count), recency window.
//
//	GET /internal/books/{book_id}/known-entities
//	  ?alive=true               (default true — exclude dead entities)
//	  &min_frequency=2          (default 2 — min chapter appearances)
//	  &before_chapter_index=50  (optional — only count links before this chapter)
//	  &recency_window=100       (default 100 — seen in last N chapters relative to before_chapter_index)
//	  &limit=50                 (default 50 — max entities returned)
func (s *Server) getKnownEntities(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		KnownEntitiesTotal.WithLabelValues(OutcomeValidationError).Inc()
		return
	}
	ctx := r.Context()
	q := r.URL.Query()

	alive := q.Get("alive") != "false" // default true
	minFreq := queryInt(q.Get("min_frequency"), 2)
	beforeIdx := queryInt(q.Get("before_chapter_index"), -1)
	recencyWindow := queryInt(q.Get("recency_window"), 100)
	if recencyWindow > 1000 {
		recencyWindow = 1000
	}
	limit := queryInt(q.Get("limit"), 50)
	if limit > 500 {
		limit = 500
	}
	if limit < 1 {
		limit = 1
	}
	// D-ANCHOR-PRELOAD-50-CAP: `offset` makes the 500-row page cap PAGEABLE, so a
	// caller wanting every entity (extraction's anchor pre-load, the WS-4B graph
	// projection) can walk the whole glossary instead of being silently truncated
	// at the default 50. Requires the deterministic ORDER BY tiebreak below.
	offset := queryInt(q.Get("offset"), 0)
	if offset < 0 {
		offset = 0
	}
	// D-GLOSSARY-KNOWN-ENTITIES-STATUS-PARAM: `status` was accepted by every caller
	// (GlossaryClient.list_entities sent `status=active`) but NEVER read here — a
	// write-only parameter that silently lied. Now honored: absent/empty ⇒ no status
	// filter (the historical effective behavior, preserved for existing callers);
	// a value must be one of the closed set or the request is rejected.
	status := q.Get("status")
	if status != "" && !validEntityStatus(status) {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_STATUS",
			"status must be one of: active, inactive, draft, rejected")
		KnownEntitiesTotal.WithLabelValues(OutcomeValidationError).Inc()
		return
	}

	// Build the query dynamically based on filters.
	// We join glossary_entities with system_kinds and aggregate chapter_entity_links
	// to compute frequency and max chapter_index (recency).
	//
	// The entity "name" comes from entity_attribute_values where the attribute code = 'name'.
	// Aliases come from attribute code = 'aliases'.
	var args []any
	argIdx := 1

	var conditions []string
	conditions = append(conditions, "e.book_id = $"+strconv.Itoa(argIdx))
	args = append(args, bookID)
	argIdx++

	// Never surface soft-deleted entities. Soft-delete is a pure `SET deleted_at`
	// (it leaves status/alive untouched and does NOT cascade chapter_entity_links),
	// so without this a deleted `status='active'` entity still passes the frequency
	// HAVING — and the W11-M3 public lore route would serve author-removed content to
	// anonymous readers. Mirrors every sibling entity read (entity_handler.go).
	conditions = append(conditions, "e.deleted_at IS NULL")

	if alive {
		conditions = append(conditions, "e.alive = true")
	}

	// D-GLOSSARY-KNOWN-ENTITIES-STATUS-PARAM — only filter when explicitly asked.
	if status != "" {
		conditions = append(conditions, "e.status = $"+strconv.Itoa(argIdx))
		args = append(args, status)
		argIdx++
	}

	// Chapter link subquery for frequency + recency
	linkCondition := "cl.entity_id = e.entity_id"
	if beforeIdx >= 0 {
		linkCondition += " AND cl.chapter_index < $" + strconv.Itoa(argIdx)
		args = append(args, beforeIdx)
		argIdx++
	}

	// Recency: max chapter_index must be within recency_window of before_chapter_index
	var havingClauses []string
	havingClauses = append(havingClauses, "COUNT(cl.link_id) >= $"+strconv.Itoa(argIdx))
	args = append(args, minFreq)
	argIdx++

	if beforeIdx >= 0 && recencyWindow > 0 {
		recencyThreshold := beforeIdx - recencyWindow
		if recencyThreshold < 0 {
			recencyThreshold = 0
		}
		havingClauses = append(havingClauses, "MAX(cl.chapter_index) >= $"+strconv.Itoa(argIdx))
		args = append(args, recencyThreshold)
		argIdx++
	}

	args = append(args, limit)
	limitParam := "$" + strconv.Itoa(argIdx)
	argIdx++
	args = append(args, offset)
	offsetParam := "$" + strconv.Itoa(argIdx)

	query := `
		SELECT
			e.entity_id,
			k.code AS kind_code,
			COALESCE(name_av.original_value, '') AS entity_name,
			COALESCE(alias_av.original_value, '') AS aliases_raw,
			COUNT(cl.link_id) AS frequency
		FROM glossary_entities e
		JOIN book_kinds k ON k.book_kind_id = e.kind_id
		LEFT JOIN entity_attribute_values name_av
			ON name_av.entity_id = e.entity_id
			AND name_av.attr_def_id = (
				SELECT ba.attr_id FROM book_attributes ba
				JOIN book_genres g ON g.genre_id = ba.genre_id
				WHERE ba.kind_id = e.kind_id AND ba.code = 'name'
				ORDER BY (g.code = 'universal') DESC LIMIT 1
			)
		LEFT JOIN entity_attribute_values alias_av
			ON alias_av.entity_id = e.entity_id
			AND alias_av.attr_def_id = (
				SELECT ba.attr_id FROM book_attributes ba
				JOIN book_genres g ON g.genre_id = ba.genre_id
				WHERE ba.kind_id = e.kind_id AND ba.code = 'aliases'
				ORDER BY (g.code = 'universal') DESC LIMIT 1
			)
		LEFT JOIN chapter_entity_links cl
			ON ` + linkCondition + `
		WHERE ` + strings.Join(conditions, " AND ") + `
		GROUP BY e.entity_id, k.code, name_av.original_value, alias_av.original_value
		HAVING ` + strings.Join(havingClauses, " AND ") + `
		ORDER BY COUNT(cl.link_id) DESC, e.entity_id ASC
		LIMIT ` + limitParam + ` OFFSET ` + offsetParam

	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		KnownEntitiesTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to query known entities")
		return
	}
	defer rows.Close()

	type entityOut struct {
		EntityID string   `json:"entity_id"`
		Name     string   `json:"name"`
		KindCode string   `json:"kind_code"`
		Aliases  []string `json:"aliases"`
		Freq     int      `json:"frequency"`
	}

	var result []entityOut
	for rows.Next() {
		var entityID, kindCode, name, aliasesRaw string
		var freq int
		if err := rows.Scan(&entityID, &kindCode, &name, &aliasesRaw, &freq); err != nil {
			KnownEntitiesTotal.WithLabelValues(OutcomeQueryFailed).Inc()
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scan entity")
			return
		}
		// aliases are stored as a JSON array string in the text field, e.g. '["alias1","alias2"]'
		var aliases []string
		if aliasesRaw != "" {
			_ = json.Unmarshal([]byte(aliasesRaw), &aliases)
		}
		if aliases == nil {
			aliases = []string{}
		}
		if name == "" {
			continue // skip entities without a name
		}
		result = append(result, entityOut{
			EntityID: entityID,
			Name:     name,
			KindCode: kindCode,
			Aliases:  aliases,
			Freq:     freq,
		})
	}
	if result == nil {
		result = []entityOut{}
	}
	KnownEntitiesTotal.WithLabelValues(OutcomeOK).Inc()
	writeJSON(w, http.StatusOK, result)
}

// ── GEP-BE-03: Bulk upsert endpoint ─────────────────────────────────────────

// bulkUpsertRequest is the request body for POST /internal/books/{book_id}/extract-entities.
type bulkUpsertRequest struct {
	SourceLanguage   string                       `json:"source_language"`
	AttributeActions map[string]map[string]string `json:"attribute_actions"` // kind_code → attr_code → "fill"|"overwrite"
	Entities         []extractedEntity            `json:"entities"`
	// ParkUnknownKinds gates the unknown-bucket fallback (D-GLOSSARY-UNKNOWN-BLAST-RADIUS).
	// nil/true (default) → an entity whose kind_code matches neither a kind nor an
	// alias is PARKED under 'unknown' for author triage (never silently dropped — the
	// "never drop" design). A caller that emits noisy/experimental kinds (e.g. the
	// knowledge-service extraction pipeline) can send false to opt OUT and have such
	// entities SKIPPED instead of flooding the review queue. Pointer so an omitted
	// field keeps the park-by-default behavior (backward-compatible).
	ParkUnknownKinds *bool `json:"park_unknown_kinds"`
	// DefaultTags are applied (on CREATE only) to every entity this batch
	// creates. The knowledge-service writeback loop sends `["ai-suggested"]`
	// so the FE can surface AI-discovered drafts as a reviewable inbox
	// (GET /entities?status=draft&tags=ai-suggested). When the batch is an
	// AI writeback (DefaultTags contains "ai-suggested"), a proposed name
	// that resolves to an existing entity carrying the `ai-rejected`
	// tombstone is SKIPPED — a user-rejected suggestion is not re-proposed.
	// nil/empty → no tags applied, no tombstone gate (backward-compatible).
	DefaultTags []string `json:"default_tags"`
	// ── Extraction pipeline FND/M1 — two-ledger writeback (all additive/optional;
	//    an omitting caller keeps today's non-idempotent, lock-free behavior) ──
	// ChapterID scopes this writeback to ONE chapter (the per-chapter atomic unit,
	// design §3.3). Used for the writeback-log row + the advisory lock is per-book.
	ChapterID string `json:"chapter_id"`
	// WritebackKey = the worker-computed idempotency key hash(book, chapter,
	// content_hash, kinds, profile_hash). When present and ALREADY committed in
	// extraction_writeback_log, the whole apply is a no-op returning the original
	// counts (INV-C3: retry = replay = concurrent fresh land once). Empty → no
	// idempotency record (legacy callers / the MCP single-entity path).
	WritebackKey string `json:"writeback_key"`
	// ContentHash of the prepared chapter text the entities were extracted from —
	// stored on the log row for provenance + the worker-side source-drift
	// precondition (INV-C4). Glossary records it; the 409-on-drift check is upstream.
	ContentHash string `json:"content_hash"`
	// OwnerUserID stamps the writeback-log row for tenancy/redaction (INV-6). The
	// worker resolves it from extraction_jobs; omitted → NULL (book_id still scopes).
	OwnerUserID string `json:"owner_user_id"`
	// ChapterOrdinal is the chapter's story-time position (0-based chapter_index). When
	// present (with ChapterID + ContentHash), the writeback ALSO emits append-only
	// bi-temporal facts into entity_facts (the temporal-knowledge SSOT, §12 Path A):
	// it ingests the immutable episode for this chapter revision and opens one fact per
	// written attribute valid-from this ordinal, citing the episode. Omitted (legacy
	// caller) → no fact emission, today's flat EAV behavior unchanged (additive).
	ChapterOrdinal *int64 `json:"chapter_ordinal"`
}

type extractedEntity struct {
	KindCode     string          `json:"kind_code"`
	Name         string          `json:"name"`
	Attributes   map[string]any  `json:"attributes"`
	Evidence     string          `json:"evidence"`
	ChapterLinks []chapterLinkIn `json:"chapter_links"`
	// PROV/M3 — VALIDATED evidence provenance (INV-7 / T1). The worker is the only
	// component holding the chapter text, so it locates the `evidence` quote in the
	// REAL text and sends offsets it already verified + a closed-enum trust status.
	// Glossary persists them DEFENSIVELY (evidenceProvenanceFields): it accepts only
	// the {exact,resolved,ambiguous,unmatched} enum, clamps the offsets (non-negative,
	// start<=end) and keeps them only for exact/resolved — a raw model number is NEVER
	// persisted unvalidated. Omitted (legacy callers / the MCP path) ⇒ status defaults
	// to 'unverified' with NULL offsets (the migration-0033 column default).
	EvidenceProvenanceStatus string `json:"evidence_provenance_status"`
	EvidenceCharStart        *int   `json:"evidence_char_start"`
	EvidenceCharEnd          *int   `json:"evidence_char_end"`
	EvidenceBlockOrLine      *int   `json:"evidence_block_or_line"`
	// Translation (M4d-2b) — optional target-language rendering of the name, seeded
	// by the translation 2-pass cold-start writeback. Written to the name attr's
	// attribute_translations at confidence='machine' (the M1d trust ladder treats
	// it as a soft hint, not canon). Omitted ⇒ no translation written (backward-
	// compatible). Never overwrites a human-verified translation (see §upsert).
	Translation *translationIn `json:"translation"`
}

type translationIn struct {
	LanguageCode string `json:"language_code"`
	Value        string `json:"value"`
}

type chapterLinkIn struct {
	ChapterID    string `json:"chapter_id"`
	ChapterTitle string `json:"chapter_title"`
	ChapterIndex int    `json:"chapter_index"`
	Relevance    string `json:"relevance"`
	// MentionCount (M7) — per-chapter mention frequency for this entity, computed by
	// the translation-service producer (CJK-aware longest-match over canonical+aliases,
	// presence-gated). Omitted ⇒ 0 (backward-compatible: a producer predating M7 leaves
	// the column at its default). The upsert overwrites with EXCLUDED so a recount lands
	// the fresh value.
	MentionCount int `json:"mention_count"`
}

type entityResult struct {
	EntityID          string   `json:"entity_id"`
	Name              string   `json:"name"`
	KindCode          string   `json:"kind_code"`
	Status            string   `json:"status"` // "created" | "updated" | "skipped"
	AttributesWritten []string `json:"attributes_written"`
	AttributesSkipped []string `json:"attributes_skipped"`
	// AttributesSkippedReasons (MERGE/M5) carries WHY each attribute was skipped — the
	// skip-reason taxonomy that ends the silent-skip gap (F-append). Additive to the bare
	// AttributesSkipped code list (kept for back-compat). Reasons: no_action | fill_occupied
	// | verified (the verified-clobber guard fired, INV-8) | tombstoned (Slice-2 append).
	AttributesSkippedReasons []attrSkip `json:"attributes_skipped_reasons,omitempty"`
	SkipReason               string     `json:"skip_reason,omitempty"` // e.g. "tombstoned" when an ai-rejected name is re-proposed
}

// attrSkip pairs a skipped attribute code with the reason it was skipped (MERGE/M5).
type attrSkip struct {
	Code   string `json:"code"`
	Reason string `json:"reason"`
}

const (
	// tagAISuggested marks an entity created by the knowledge-service
	// writeback loop, so the FE can list it as a reviewable AI suggestion.
	tagAISuggested = "ai-suggested"
	// tagAIRejected is the tombstone a user sets when rejecting an AI
	// suggestion; an AI writeback batch skips names that carry it.
	tagAIRejected = "ai-rejected"
)

// evidenceProvenanceFields returns the (provenance_status, char_start, char_end,
// block_or_line) to persist for an evidence row — the DEFENSIVE glossary side of the
// model-offset-trust contract (INV-7 / T1). The worker already validated the quote's
// location against the real chapter text; glossary still trusts no raw number:
//
//   - Only the closed enum {exact,resolved,ambiguous,unmatched} is honored; anything
//     else (incl. an omitting legacy caller) degrades to 'unverified' with NULL offsets.
//   - Offsets are persisted ONLY for exact/resolved (a single verified location) AND only
//     when sane (non-negative, start<=end). A status that claims exact/resolved without
//     valid offsets is downgraded to 'unverified' rather than stored half-trusted.
//   - ambiguous/unmatched keep the status but carry NULL offsets (no blind pick / no
//     fabricated citation — the quote is still stored via original_text).
//
// block_or_line is TEXT NOT NULL DEFAULT '' (the legacy column), so a present block index
// is rendered as a decimal string and absence is the empty string.
func evidenceProvenanceFields(ent extractedEntity) (status string, charStart, charEnd *int, blockOrLine string) {
	status = "unverified"
	switch ent.EvidenceProvenanceStatus {
	case "exact", "resolved":
		if ent.EvidenceCharStart != nil && ent.EvidenceCharEnd != nil &&
			*ent.EvidenceCharStart >= 0 && *ent.EvidenceCharEnd >= *ent.EvidenceCharStart {
			status = ent.EvidenceProvenanceStatus
			charStart = ent.EvidenceCharStart
			charEnd = ent.EvidenceCharEnd
			if ent.EvidenceBlockOrLine != nil && *ent.EvidenceBlockOrLine >= 0 {
				blockOrLine = strconv.Itoa(*ent.EvidenceBlockOrLine)
			}
		}
		// else: claimed exact/resolved but no/invalid offset → stay 'unverified'.
	case "ambiguous", "unmatched":
		status = ent.EvidenceProvenanceStatus // keep the quote; offsets stay NULL
	}
	return
}

// bulkExtractEntities receives extracted entities from translation-service and upserts them.
//
//	POST /internal/books/{book_id}/extract-entities
func (s *Server) bulkExtractEntities(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		BulkExtractTotal.WithLabelValues(OutcomeValidationError).Inc()
		return
	}
	ctx := r.Context()

	var req bulkUpsertRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		BulkExtractTotal.WithLabelValues(OutcomeInvalidBody).Inc()
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON body")
		return
	}
	if req.SourceLanguage == "" {
		req.SourceLanguage = "zh"
	}
	if len(req.Entities) == 0 {
		// Empty batch is a valid no-op — count as OK so dashboards
		// don't treat pre-filter zero-arrays as errors.
		BulkExtractTotal.WithLabelValues(OutcomeOK).Inc()
		writeJSON(w, http.StatusOK, map[string]any{
			"created": 0, "updated": 0, "skipped": 0, "entities": []entityResult{},
		})
		return
	}

	// Pre-load kind_id map (code → book_kind_id) for THIS book (G4 book tier).
	kindMap, err := s.loadKindMap(ctx, bookID)
	if err != nil {
		BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to load kinds")
		return
	}
	// An adopted book always has at least the 'unknown' kind, so an empty kind map
	// means the book has no ontology yet — extraction would silently skip every entity
	// (D-GKA-EXTRACT-UNADOPTED-GUARD). Fail fast with a clear, actionable error instead.
	if len(kindMap) == 0 {
		BulkExtractTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_BOOK_NOT_SCAFFOLDED",
			"book ontology not adopted — call POST /v1/glossary/books/{book_id}/adopt first")
		return
	}

	// Pre-load attr_def map (book_kind_id+code → attr_id) for THIS book (G4 book tier).
	// These two reads are book CONFIG — left on the pool, BEFORE the writeback tx, to
	// keep the per-book advisory lock window tight (only the actual writes are locked).
	attrDefMap, err := s.loadAttrDefMap(ctx, s.pool, bookID)
	if err != nil {
		BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to load attribute definitions")
		return
	}
	// MERGE/M5 slice 2 — the authored per-attribute merge_strategy (the default the
	// profile overrides). Book CONFIG, read on the pool before the writeback tx.
	strategyMap, err := s.loadAttrStrategyMap(ctx, bookID)
	if err != nil {
		BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to load merge strategies")
		return
	}

	// ── M1: parse the optional two-ledger writeback fields (additive/back-compat) ──
	var chapterID uuid.UUID
	if req.ChapterID != "" {
		chapterID, err = uuid.Parse(req.ChapterID)
		if err != nil {
			BulkExtractTotal.WithLabelValues(OutcomeValidationError).Inc()
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid chapter_id")
			return
		}
	}
	var ownerUserID uuid.UUID
	if req.OwnerUserID != "" {
		ownerUserID, _ = uuid.Parse(req.OwnerUserID) // best-effort tenancy stamp; nil if malformed
	}

	// ── M1: per-book serialized, whole-chapter transactional writeback (INV-C1) ──
	// One transaction for the whole chapter's entities: partial failure rolls the
	// entire chapter back (no half-written chapter), and a per-book advisory lock
	// serializes concurrent jobs so the app-layer resolver is race-free (two jobs on
	// the same chapter no longer both miss-then-create the same entity — the TOCTOU
	// duplicate). defer-rollback is a no-op after a successful Commit.
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to begin writeback tx")
		return
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1, hashtext($2))`,
		extractionWritebackLockNS, bookID.String()); err != nil {
		BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to take book writeback lock")
		return
	}

	// Idempotency (INV-C3): a writeback_key already 'committed' means this chapter's
	// entities ALREADY landed (a retry, a redelivery, or a concurrent fresh run that
	// won the lock). Return the original counts without re-applying — duplicate apply
	// is a no-op. The check runs INSIDE the lock so a same-key concurrent request that
	// lost the lock sees the committed row here.
	if req.WritebackKey != "" {
		var prevStatus string
		var pc, pu, ps int
		ierr := tx.QueryRow(ctx,
			`SELECT status, entities_created, entities_updated, entities_skipped
			   FROM extraction_writeback_log WHERE writeback_key = $1`, req.WritebackKey,
		).Scan(&prevStatus, &pc, &pu, &ps)
		if ierr == nil && prevStatus == "committed" {
			_ = tx.Rollback(ctx)
			BulkExtractTotal.WithLabelValues(OutcomeOK).Inc()
			writeJSON(w, http.StatusOK, map[string]any{
				"created": pc, "updated": pu, "skipped": ps,
				"entities": []entityResult{}, "idempotent_replay": true,
			})
			return
		}
		if ierr != nil && ierr != pgx.ErrNoRows {
			BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "writeback-log lookup failed")
			return
		}
	}

	// The 'unknown' review bucket: a kind_code that resolves to neither a kind nor
	// an alias is PARKED here (never silently dropped) so the author can triage it
	// (alias it to a kind, or create a kind from it) — the entity remembers the code
	// it arrived as in source_kind_code. uuid.Nil only if the migration hasn't seeded
	// 'unknown' yet, in which case we preserve the legacy skip (fail-safe).
	unknownKindID := kindMap["unknown"]
	// D-GLOSSARY-UNKNOWN-BLAST-RADIUS: parking is the default; a caller may opt out
	// (park_unknown_kinds=false) to SKIP unrecognised kinds instead of flooding the
	// review queue. Omitted → park (backward-compatible).
	parkUnknown := req.ParkUnknownKinds == nil || *req.ParkUnknownKinds
	// isAIWriteback gates the tombstone skip: only an AI writeback batch
	// (marked by the ai-suggested default tag) suppresses ai-rejected names.
	isAIWriteback := slices.Contains(req.DefaultTags, tagAISuggested)

	var (
		results []entityResult
		created int
		updated int
		skipped int
	)

	// Temporal-knowledge Path A (§12): when the caller supplies the chapter ordinal, ingest
	// the immutable episode for this chapter revision ONCE (UNIQUE(chapter_id, content_hash)
	// → resumes, never re-mints) so the per-entity fact emission below can cite it. Sealed
	// 'pending'; reconciled after the entity loop commits the facts (§12.2.5).
	var factEpisodeID *uuid.UUID
	if req.ChapterOrdinal != nil && chapterID != uuid.Nil && req.ContentHash != "" {
		epID, _, eerr := ingestEpisode(ctx, tx, bookID, chapterID, *req.ChapterOrdinal, req.ContentHash, req.WritebackKey)
		if eerr != nil {
			BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to ingest episode: "+eerr.Error())
			return
		}
		factEpisodeID = &epID
	}

	for _, ent := range req.Entities {
		kindID, kindOK := kindMap[ent.KindCode]
		sourceKindCode := "" // non-empty only when parked under 'unknown'
		if !kindOK {
			if !parkUnknown || unknownKindID == uuid.Nil {
				// Caller opted out of parking, OR no unknown bucket seeded yet
				// (legacy fail-safe) → skip the unrecognised kind.
				continue
			}
			kindID = unknownKindID
			sourceKindCode = ent.KindCode // remember the original code for review
		}
		if ent.Name == "" {
			continue
		}

		actions := req.AttributeActions[ent.KindCode]
		if actions == nil {
			actions = map[string]string{}
		}

		// 1. Find existing entity by normalized name or alias match (same kind).
		// "" scope: the bulk extraction pipeline has no scope concept yet (out of
		// scope for this pass — D-GLOSSARY-ENTITY-SCOPE only covers the interactive
		// MCP creation path); this preserves its exact prior dedup behavior.
		existingID, err := s.findEntityByNameOrAlias(ctx, tx, bookID, kindID, ent.Name, "")
		if err != nil {
			BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "entity lookup failed")
			return
		}
		// mergeKindID is the kind to merge incoming attributes under. It equals the
		// extraction kind for a same-kind hit; for a cross-kind hit (#38/#39) it is the
		// MATCHED entity's actual kind, so attributes resolve against that entity's
		// schema (compatible codes merge, the rest skip) instead of orphaning onto the
		// wrong kind.
		mergeKindID := kindID
		// 1b. #38/#39 — cross-kind dedup: if the same name already exists under ANOTHER
		// kind, reuse that entity instead of creating a duplicate. This kills both the
		// one-name-under-N-kinds explosion (#38) and the re-run-with-changed-kinds
		// duplication (#39, where the per-chapter writeback_key changes and the per-kind
		// resolver misses the prior run's entity).
		if existingID == uuid.Nil {
			crossID, crossKindID, cerr := s.findEntityCrossKind(ctx, tx, bookID, ent.Name, "")
			if cerr != nil {
				BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "cross-kind entity lookup failed")
				return
			}
			if crossID != uuid.Nil {
				existingID = crossID
				mergeKindID = crossKindID
			}
		}

		var result entityResult
		result.Name = ent.Name
		result.KindCode = ent.KindCode

		// Tombstone gate (P5): when this batch is an AI writeback, a name
		// that resolves to an entity the user previously rejected
		// (tag 'ai-rejected') is skipped without touching the row — a
		// rejected suggestion must not be re-proposed every extraction.
		if existingID != uuid.Nil && isAIWriteback {
			rejected, terr := s.entityHasTag(ctx, tx, existingID, tagAIRejected)
			if terr != nil {
				BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tombstone check failed")
				return
			}
			if rejected {
				result.EntityID = existingID.String()
				result.Status = "skipped"
				result.SkipReason = "tombstoned"
				result.AttributesWritten = []string{}
				result.AttributesSkipped = []string{}
				skipped++
				results = append(results, result)
				continue
			}
		}

		if existingID == uuid.Nil {
			// 2. CREATE new entity — default tags (e.g. ai-suggested) are
			// applied on create only, so an AI writeback never re-tags a
			// user's existing/active entity into the suggestion inbox.
			entityID, written, skippedAttrs, err := s.createExtractedEntity(ctx, tx, bookID, kindID, ent, actions, attrDefMap, req.SourceLanguage, req.DefaultTags)
			if err != nil {
				BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to create entity: "+err.Error())
				return
			}
			result.EntityID = entityID.String()
			result.Status = "created"
			// Parked under 'unknown' → remember the code it arrived as, so the review
			// GUI can offer "alias <code> → <kind>" / "create kind from <code>".
			if sourceKindCode != "" {
				if _, uerr := tx.Exec(ctx,
					`UPDATE glossary_entities SET source_kind_code = $1 WHERE entity_id = $2`,
					sourceKindCode, entityID,
				); uerr != nil {
					BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
					writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to record source kind: "+uerr.Error())
					return
				}
			}
			// /review-impl HIGH fix: report only codes that actually matched an attr_def
			// (+ "description" when the unmatched-attr fallback fired) — NOT every raw
			// key in ent.Attributes. AttributesWritten feeds emitChapterFacts below,
			// which emits a fact per code; a phantom code with no attr_def would mint an
			// entity_facts row (INV-FACTS SSOT) that can never agree with the EAV
			// projection, since that value actually lives inside "description".
			result.AttributesWritten = written
			skippedCodes := make([]string, 0, len(skippedAttrs))
			for _, sa := range skippedAttrs {
				skippedCodes = append(skippedCodes, sa.Code)
			}
			result.AttributesSkipped = skippedCodes
			result.AttributesSkippedReasons = skippedAttrs
			created++
		} else {
			// 3. MERGE with existing entity — under mergeKindID (the matched entity's
			// own kind, which equals kindID for a same-kind hit and the cross-kind
			// match's kind for #38/#39 dedup) so attributes resolve against the
			// entity's real schema.
			written, skippedAttrs, err := s.mergeExtractedEntity(ctx, tx, existingID, mergeKindID, ent, actions, strategyMap, attrDefMap, req.SourceLanguage)
			if err != nil {
				BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to merge entity: "+err.Error())
				return
			}
			result.EntityID = existingID.String()
			result.AttributesWritten = written
			// Surface both the bare code list (back-compat) and the structured reasons.
			skippedCodes := make([]string, 0, len(skippedAttrs))
			for _, sa := range skippedAttrs {
				skippedCodes = append(skippedCodes, sa.Code)
			}
			result.AttributesSkipped = skippedCodes
			result.AttributesSkippedReasons = skippedAttrs
			if len(written) > 0 {
				result.Status = "updated"
				updated++
			} else {
				result.Status = "skipped"
				skipped++
			}
		}

		// 3b. Temporal-knowledge Path A: emit one append-only fact per WRITTEN attribute,
		// valid-from this chapter ordinal, citing the episode. Additive — the EAV write above
		// stays the live "current" projection; entity_facts accumulates as the SSOT (§12).
		if factEpisodeID != nil && result.EntityID != "" {
			entID, perr := uuid.Parse(result.EntityID)
			if perr == nil {
				if ferr := s.emitChapterFacts(ctx, tx, bookID, entID, ent, result.AttributesWritten, *req.ChapterOrdinal, *factEpisodeID); ferr != nil {
					BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
					writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to emit facts: "+ferr.Error())
					return
				}
			}
		}

		// 4. Add chapter links
		for _, cl := range ent.ChapterLinks {
			chID, err := uuid.Parse(cl.ChapterID)
			if err != nil {
				continue
			}
			entID, _ := uuid.Parse(result.EntityID)
			relevance := cl.Relevance
			if relevance == "" {
				relevance = "appears"
			}
			if _, err := tx.Exec(ctx, `
				INSERT INTO chapter_entity_links (entity_id, chapter_id, chapter_title, chapter_index, relevance, mention_count)
				VALUES ($1, $2, $3, $4, $5, $6)
				ON CONFLICT (entity_id, chapter_id) DO UPDATE SET
					chapter_title = EXCLUDED.chapter_title,
					chapter_index = EXCLUDED.chapter_index,
					relevance = EXCLUDED.relevance,
					mention_count = EXCLUDED.mention_count
			`, entID, chID, cl.ChapterTitle, cl.ChapterIndex, relevance, cl.MentionCount); err != nil {
				// In a tx a failed statement poisons it, so this must not error in
				// practice — the ON CONFLICT makes the insert total. Roll back + 500
				// rather than swallow (a swallowed error would abort every later
				// statement in this tx anyway).
				BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to link chapter: "+err.Error())
				return
			}
		}

		// 5. Add evidence (extraction quote)
		if ent.Evidence != "" {
			entID, _ := uuid.Parse(result.EntityID)
			nameAttrDefID, nameOK := attrDefMap[kindID.String()+":name"]
			if nameOK {
				// Get the name attr_value_id
				var nameAVID uuid.UUID
				err := tx.QueryRow(ctx, `
					SELECT attr_value_id FROM entity_attribute_values
					WHERE entity_id = $1 AND attr_def_id = $2
				`, entID, nameAttrDefID).Scan(&nameAVID)
				if err == nil {
					// PROV/M3 — populate CHAPTER-LEVEL provenance (chapter_title +
					// chapter_index) from the entity's first chapter link, so a quote
					// traces at least to its chapter (was: only chapter_id + text). The
					// finer block_or_line/char offsets + the trust taxonomy stay at the
					// safe DEFAULT 'unverified' until the translation-side offset map +
					// validation populate them (INV-7: model offsets are validated, never
					// trusted — that's the model-offset-trust step, deliberately not here).
					// M2 — the quote's chapter is the chapter THIS writeback processed
					// (req.ChapterID), not the entity's first-ever appearance.
					evChapterID, evChapterTitle, evChapterIndex := evidenceChapterFor(req.ChapterID, ent.ChapterLinks)
					// PROV/M3 — VALIDATED offset + trust status (INV-7). The worker already
					// located the quote in the real text; glossary trusts no raw number —
					// evidenceProvenanceFields clamps + enum-gates, degrading anything
					// off-contract to 'unverified' with NULL offsets (keep the quote, never
					// fabricate a citation).
					provStatus, provCS, provCE, provBlk := evidenceProvenanceFields(ent)
					// INV-C5: idempotent evidence — uq_evidence_dedup keeps ONE row per
					// (attr_value_id, evidence_type, quote), so re-extraction/redelivery
					// of the same quote never duplicates, and (crucial inside a tx) the
					// ON CONFLICT keeps a duplicate from raising an error that would poison
					// the whole writeback. A TRUE replay is already short-circuited upstream
					// by the writeback_key guard, so this conflict path is reached only by a
					// DISTINCT writeback that re-asserts the same quote (e.g. a re-extraction
					// after the chapter was edited so a byte-identical quote MOVED). There we
					// DO UPDATE the PROVENANCE columns only — latest-validated-wins — so the
					// stored offset/trust tracks the current text instead of going stale on
					// the first-writer's coordinates. original_text is the conflict key (so
					// it's identical); the chapter pointer (M5 backfill of the firstChapterID bug) + the validated
					// offsets can legitimately differ, so only they refresh.
					if _, err := tx.Exec(ctx, `
						INSERT INTO evidences (attr_value_id, chapter_id, chapter_title, chapter_index,
						                       block_or_line, char_start, char_end, provenance_status,
						                       evidence_type, original_language, original_text, note)
						VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
						        'extraction_quote', $9, $10, 'auto-extracted by glossary extraction pipeline')
						ON CONFLICT (attr_value_id, evidence_type, md5(original_text)) DO UPDATE SET
							chapter_id        = EXCLUDED.chapter_id,
							chapter_title     = EXCLUDED.chapter_title,
							chapter_index     = EXCLUDED.chapter_index,
							block_or_line     = EXCLUDED.block_or_line,
							char_start        = EXCLUDED.char_start,
							char_end          = EXCLUDED.char_end,
							provenance_status = EXCLUDED.provenance_status
					`, nameAVID, evChapterID, evChapterTitle, evChapterIndex,
						provBlk, provCS, provCE, provStatus,
						req.SourceLanguage, ent.Evidence); err != nil {
						BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
						writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to insert evidence: "+err.Error())
						return
					}
				}
			}
		}

		// 5b. M4d-2b — optional target translation for the name attribute. Seeds
		// the 2-pass cold-start source→target renderings as machine drafts.
		// Conditional upsert: insert when absent, overwrite a draft/machine value,
		// but NEVER a verified (human) translation (M1d trust ladder). An
		// overwritten machine value remains recoverable via the VG-1 revision
		// history. Best-effort (the entity already committed above).
		translationChanged := false
		if ent.Translation != nil && ent.Translation.LanguageCode != "" && ent.Translation.Value != "" {
			entID, _ := uuid.Parse(result.EntityID)
			nameAttrDefID, nameOK := attrDefMap[kindID.String()+":name"]
			if nameOK {
				var nameAVID uuid.UUID
				if err := tx.QueryRow(ctx, `
					SELECT attr_value_id FROM entity_attribute_values
					WHERE entity_id = $1 AND attr_def_id = $2
				`, entID, nameAttrDefID).Scan(&nameAVID); err == nil {
					ct, err := tx.Exec(ctx, `
						INSERT INTO attribute_translations (attr_value_id, language_code, value, confidence, translator)
						VALUES ($1, $2, $3, 'machine', 'translation-2pass')
						ON CONFLICT (attr_value_id, language_code) DO UPDATE
						  SET value = EXCLUDED.value, confidence = 'machine',
						      translator = EXCLUDED.translator, updated_at = now()
						  WHERE attribute_translations.confidence <> 'verified'
					`, nameAVID, ent.Translation.LanguageCode, ent.Translation.Value)
					if err != nil {
						BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
						writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to write name translation: "+err.Error())
						return
					} else if ct.RowsAffected() > 0 {
						translationChanged = true
					}
				}
			}
		}
		// review-impl: a translation-only change to an EXISTING entity merges to
		// "skipped" (no attr changed), but the translation DID change — it must
		// still emit so VG-1 versions it (recoverable) and M5c marks dependents
		// stale. Promote skipped→updated so the emit below fires.
		if translationChanged && result.Status == "skipped" {
			result.Status = "updated"
			updated++
			skipped--
		}

		// 6. C4 (K14) — emit ONE glossary.entity_updated per entity that
		// was actually written (created or updated). "skipped" entities
		// changed nothing, so no event. This is the bulk fan-out: a batch
		// of N written entities produces N events, never a single batch
		// event — so every extracted entity propagates to Neo4j. Built
		// from in-hand fields (name/kind from this request) rather than a
		// snapshot round-trip, since cached_name may lag the EAV write
		// within the same request. Best-effort (pool.Exec already
		// committed each entity above; a broker hiccup must not fail the
		// whole bulk response).
		if result.Status == "created" || result.Status == "updated" {
			entID, _ := uuid.Parse(result.EntityID)
			// Phase B: actor_type="pipeline" — this is the extraction's
			// ORIGINAL output, not a user correction. learning-service skips
			// pipeline events (no before/after attached).
			payload := buildEntityEventPayload(
				bookID.String(), result.EntityID, ent.Name, ent.KindCode,
				nil, "", result.Status, "pipeline", "", nil,
			)
			// Transactional outbox (INV-O12): the event row now commits ATOMICALLY
			// with the entity write in this same tx (it used to be a post-commit
			// best-effort pool write). A failed INSERT poisons the tx, so it's fatal
			// here — but it's a DB write, not a broker publish (the relay drains the
			// outbox table later), so this does not couple the response to the broker.
			if err := insertEntityOutboxEvent(ctx, func(ctx context.Context, sql string, args ...any) error {
				_, e := tx.Exec(ctx, sql, args...)
				return e
			}, entID, payload); err != nil {
				BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to emit entity event: "+err.Error())
				return
			}
		}

		results = append(results, result)
	}

	if results == nil {
		results = []entityResult{}
	}

	// Temporal-knowledge Path A: the chapter's facts have landed → flip the episode
	// pending→reconciled in the same tx (§12.2.5 tx-2). A crash before here leaves a
	// resumable 'pending' episode, never a phantom sealed-empty one polluting retrieval.
	if factEpisodeID != nil {
		if err := reconcileEpisode(ctx, tx, *factEpisodeID); err != nil {
			BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to reconcile episode: "+err.Error())
			return
		}
	}

	// ── M1: record the WRITEBACK ledger row (INV-C3) + commit the chapter atomically.
	// Only when the caller supplied an idempotency key AND a chapter (the per-chapter
	// unit). ON CONFLICT DO NOTHING guards a concurrent winner (the advisory lock makes
	// that unreachable in practice, but it keeps the insert total inside the tx).
	if req.WritebackKey != "" && chapterID != uuid.Nil {
		var ownerArg any
		if ownerUserID != uuid.Nil {
			ownerArg = ownerUserID
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO extraction_writeback_log
			  (owner_user_id, book_id, chapter_id, writeback_key, content_hash, status,
			   entities_created, entities_updated, entities_skipped, committed_at)
			VALUES ($1, $2, $3, $4, $5, 'committed', $6, $7, $8, now())
			ON CONFLICT (writeback_key) DO NOTHING
		`, ownerArg, bookID, chapterID, req.WritebackKey, req.ContentHash,
			created, updated, skipped); err != nil {
			BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to record writeback log: "+err.Error())
			return
		}
	}

	if err := tx.Commit(ctx); err != nil {
		BulkExtractTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to commit writeback: "+err.Error())
		return
	}

	BulkExtractTotal.WithLabelValues(OutcomeOK).Inc()
	writeJSON(w, http.StatusOK, map[string]any{
		"created":  created,
		"updated":  updated,
		"skipped":  skipped,
		"entities": results,
	})
}

// loadKindMap returns a map of kind code → book_kind_id for the given book (G4:
// entities reference the BOOK tier). The book must be adopted first (book_kinds
// populated by the copy-down) — an un-adopted book yields an empty map, so every
// kind_code falls through to the 'unknown' park bucket (which adopt always copies).
func (s *Server) loadKindMap(ctx context.Context, bookID uuid.UUID) (map[string]uuid.UUID, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT book_kind_id, code FROM book_kinds WHERE book_id = $1 AND deprecated_at IS NULL`, bookID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	m := make(map[string]uuid.UUID)
	for rows.Next() {
		var id uuid.UUID
		var code string
		if err := rows.Scan(&id, &code); err != nil {
			return nil, err
		}
		m[code] = id
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	// Fold in kind ALIASES, resolved to a BOOK kind by CODE: an alias points at a
	// system kind; we map alias_code → the book_kind sharing that system kind's code.
	// A real book_kind.code ALWAYS wins (the IF-not-present guard below), so a code
	// that exists as a book kind takes precedence over a stale alias.
	arows, err := s.pool.Query(ctx, `
		SELECT a.alias_code, bk.book_kind_id
		FROM entity_kind_aliases a
		JOIN system_kinds sk ON sk.kind_id = a.kind_id
		JOIN book_kinds   bk ON bk.book_id = $1 AND bk.code = sk.code AND bk.deprecated_at IS NULL`, bookID)
	if err != nil {
		return nil, err
	}
	defer arows.Close()
	for arows.Next() {
		var id uuid.UUID
		var alias string
		if err := arows.Scan(&alias, &id); err != nil {
			return nil, err
		}
		if _, isKind := m[alias]; !isKind {
			m[alias] = id
		}
	}
	return m, arows.Err()
}

// loadBookKindCodes returns the set of LITERAL book_kind codes for a book (active
// only) — NO alias folding, unlike loadKindMap. This is the executor's existence
// domain: create_kinds inserts a book_kind by literal code and skips only on a
// unique violation against this set. The plan-card preview uses it so its
// "N new — M already exist" count matches what execute_plan will actually do; the
// alias-folded loadKindMap over-counts "exist" (an alias of an adopted kind, e.g.
// "faction"→organization, is NOT a book_kind, so create_kinds still creates it) —
// the drift D-PLAN-PREVIEW-COUNT-DRIFT fixes.
func (s *Server) loadBookKindCodes(ctx context.Context, bookID uuid.UUID) (map[string]struct{}, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT code FROM book_kinds WHERE book_id = $1 AND deprecated_at IS NULL`, bookID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	codes := make(map[string]struct{})
	for rows.Next() {
		var code string
		if err := rows.Scan(&code); err != nil {
			return nil, err
		}
		codes[code] = struct{}{}
	}
	return codes, rows.Err()
}

// loadAttrDefMap returns a map of "book_kind_id:code" → attr_id for the given book
// (G4: book_attributes). Keyed by the UNIVERSAL-genre row — the seed lifts every
// kind's attrs into (kind, universal) and adopt copies them there, so extraction /
// entity attributes resolve under universal. DISTINCT ON (kind_id, code) preferring
// the universal row keeps one attr per (kind, code) even if a genre-specific row
// shares the code.
// q lets a caller that already holds a tx (e.g. under the per-book advisory
// lock, INV-C1) run this on that SAME connection instead of a second one from
// s.pool — the fix for D-GLOSSARY-PROPOSE-LOCK's connection-pool deadlock risk
// (a hardcoded s.pool here forced every tx-holding caller to need 2 connections
// at once). Callers with no open tx yet just pass s.pool.
func (s *Server) loadAttrDefMap(ctx context.Context, q pgxRWQuerier, bookID uuid.UUID) (map[string]uuid.UUID, error) {
	rows, err := q.Query(ctx, `
		SELECT DISTINCT ON (ba.kind_id, ba.code) ba.attr_id, ba.kind_id, ba.code
		FROM book_attributes ba
		JOIN book_genres g ON g.genre_id = ba.genre_id
		WHERE ba.book_id = $1 AND ba.deprecated_at IS NULL
		ORDER BY ba.kind_id, ba.code, (g.code = 'universal') DESC, ba.sort_order`, bookID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	m := make(map[string]uuid.UUID)
	for rows.Next() {
		var attrDefID, kindID uuid.UUID
		var code string
		if err := rows.Scan(&attrDefID, &kindID, &code); err != nil {
			return nil, err
		}
		m[kindID.String()+":"+code] = attrDefID
	}
	return m, rows.Err()
}

// loadAttrStrategyMap returns kindID:code → authored merge_strategy (MERGE/M5 slice 2).
// The authored strategy is the DEFAULT merge behavior; the per-extraction profile
// (attribute_actions) overrides it. Resolved book-tier (the same DISTINCT-ON universal-
// preferred selection as loadAttrDefMap) so a book override of the System default wins.
func (s *Server) loadAttrStrategyMap(ctx context.Context, bookID uuid.UUID) (map[string]string, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT DISTINCT ON (ba.kind_id, ba.code) ba.kind_id, ba.code, ba.merge_strategy
		FROM book_attributes ba
		JOIN book_genres g ON g.genre_id = ba.genre_id
		WHERE ba.book_id = $1 AND ba.deprecated_at IS NULL
		ORDER BY ba.kind_id, ba.code, (g.code = 'universal') DESC, ba.sort_order`, bookID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	m := make(map[string]string)
	for rows.Next() {
		var kindID uuid.UUID
		var code, strategy string
		if err := rows.Scan(&kindID, &code, &strategy); err != nil {
			return nil, err
		}
		m[kindID.String()+":"+code] = strategy
	}
	return m, rows.Err()
}

// seedMergeStrategy is the runtime twin of migration 0039's CASE (merge_strategy_heuristic.go):
// the default authored merge_strategy for a NEWLY-created ontology attribute, by type. It MUST
// stay in sync with that migration — identity (name/term, or a required text key)→fill_if_empty;
// tags→append; everything else→overwrite. Without it, an attribute created at runtime (book
// adoption clones a NEW source, custom kind/attr) lands on the column DEFAULT 'fill_if_empty' and
// silently re-freezes on re-extraction, even though the migration healed the rows that existed at
// migration time (D-EXTRACT-ATTR-MERGE-DEFAULTS — the one-time migration can't cover future rows).
func seedMergeStrategy(code, fieldType string, isRequired bool) string {
	switch {
	case code == "name" || code == "term":
		return "fill_if_empty"
	case isRequired && fieldType == "text":
		return "fill_if_empty"
	case fieldType == "tags":
		return "append"
	default:
		return "overwrite"
	}
}

// strategyToAction maps an authored merge_strategy to the runtime merge action the
// extraction writeback understands. 'manual' returns "" (the caller skips it with a
// 'manual' reason — queue for human review, never auto-write). Unknown/empty → the safe
// fill-if-empty default.
func strategyToAction(strategy string) string {
	switch strategy {
	case "replace", "overwrite":
		return "overwrite"
	case "append":
		return "append"
	case "summarize":
		// #26/#7 — merge-rewrite. Accumulates the raw layer exactly like append, then
		// flags the EAV for an end-of-job LLM canonical resynthesis (mergeExtractedEntity).
		return "summarize"
	case "manual":
		return "" // skip → 'manual'
	default: // "fill_if_empty" and anything unrecognized
		return "fill"
	}
}

// findEntityByNameOrAlias looks up an existing LIVE entity by normalized name match,
// then by alias match if not found. Returns uuid.Nil if no match.
//
// All steps exclude soft-deleted entities (`deleted_at IS NULL`): a deleted row must
// never be an extraction resolution target. This is the anti-resurrection contract — a
// merged-away loser is soft-deleted with its name/aliases folded into the WINNER, so an
// incoming name must resolve to the live winner (whose folded alias matches), never to the
// hidden loser. (/review-impl S6 #1 — Steps 1-2 previously omitted this; Step 3 inherited.)
// scope is an OPTIONAL disambiguation filter (glossary_entities.scope_label —
// a plain author-set text label, e.g. a world/realm name, added 2026-07-08 per
// real feedback: two entities can share a name+kind but genuinely be different
// "Lâm gia" in different worlds — the resolver used to always fold them
// together). Empty scope matches only entities whose OWN scope_label is also
// empty (today's default, unchanged behavior for every caller that doesn't
// pass one); a non-empty scope matches only entities carrying that EXACT
// label. This is an additional filter, not a relaxation — normalized name/alias
// still must match first.
func (s *Server) findEntityByNameOrAlias(ctx context.Context, q pgxRWQuerier, bookID, kindID uuid.UUID, name, scope string) (uuid.UUID, error) {
	normalizedName := normalizeEntity(name)

	// Step 1: Try exact name match (normalized)
	rows, err := q.Query(ctx, `
		SELECT ge.entity_id, eav.original_value, ge.scope_label
		FROM glossary_entities ge
		JOIN entity_attribute_values eav ON eav.entity_id = ge.entity_id
		JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
		WHERE ge.book_id = $1
		  AND ge.kind_id = $2
		  AND ge.deleted_at IS NULL
		  AND ad.code = 'name'
	`, bookID, kindID)
	if err != nil {
		return uuid.Nil, err
	}
	defer rows.Close()

	type nameEntry struct {
		entityID uuid.UUID
		name     string
		scope    string
	}
	var entries []nameEntry
	for rows.Next() {
		var e nameEntry
		if err := rows.Scan(&e.entityID, &e.name, &e.scope); err != nil {
			return uuid.Nil, err
		}
		if normalizeEntity(e.name) == normalizedName && e.scope == scope {
			return e.entityID, nil
		}
		entries = append(entries, e)
	}

	// Step 2: Check aliases (app-layer JSON parsing per design C1)
	aliasRows, err := q.Query(ctx, `
		SELECT ge.entity_id, eav.original_value, ge.scope_label
		FROM glossary_entities ge
		JOIN entity_attribute_values eav ON eav.entity_id = ge.entity_id
		JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
		WHERE ge.book_id = $1
		  AND ge.kind_id = $2
		  AND ge.deleted_at IS NULL
		  AND ad.code = 'aliases'
		  AND eav.original_value != ''
	`, bookID, kindID)
	if err != nil {
		return uuid.Nil, err
	}
	defer aliasRows.Close()

	for aliasRows.Next() {
		var entityID uuid.UUID
		var aliasRaw, entScope string
		if err := aliasRows.Scan(&entityID, &aliasRaw, &entScope); err != nil {
			return uuid.Nil, err
		}
		if entScope != scope {
			continue
		}
		var aliases []string
		if err := json.Unmarshal([]byte(aliasRaw), &aliases); err != nil {
			continue // not a valid JSON array, skip
		}
		for _, alias := range aliases {
			if normalizeEntity(alias) == normalizedName {
				return entityID, nil
			}
		}
	}

	// Step 3 (S6): check PER-LANGUAGE alias sets — the aliases attr's translations, each
	// a JSON array in some target language. This makes resolution cross-language: an
	// entity whose 'en' alias set contains the incoming name resolves to it even when the
	// source-language name/aliases don't match (anti-resurrection across languages). Same
	// book+kind scope as Steps 1-2.
	tRows, err := q.Query(ctx, `
		SELECT ge.entity_id, t.value, ge.scope_label
		FROM glossary_entities ge
		JOIN entity_attribute_values eav ON eav.entity_id = ge.entity_id
		JOIN book_attributes ad ON ad.attr_id = eav.attr_def_id
		JOIN attribute_translations t ON t.attr_value_id = eav.attr_value_id
		WHERE ge.book_id = $1
		  AND ge.kind_id = $2
		  AND ge.deleted_at IS NULL
		  AND ad.code = 'aliases'
		  AND t.value != ''
	`, bookID, kindID)
	if err != nil {
		return uuid.Nil, err
	}
	defer tRows.Close()

	for tRows.Next() {
		var entityID uuid.UUID
		var aliasRaw, entScope string
		if err := tRows.Scan(&entityID, &aliasRaw, &entScope); err != nil {
			return uuid.Nil, err
		}
		if entScope != scope {
			continue
		}
		var aliases []string
		if err := json.Unmarshal([]byte(aliasRaw), &aliases); err != nil {
			continue // not a valid JSON array, skip
		}
		for _, alias := range aliases {
			if normalizeEntity(alias) == normalizedName {
				return entityID, nil
			}
		}
	}

	return uuid.Nil, nil
}

// findEntityCrossKind resolves a name to an existing book entity REGARDLESS of kind
// (#38/#39). The per-kind findEntityByNameOrAlias above misses when the LLM tags the
// same character under a different kind (or a re-run with a changed kind set lands it
// elsewhere), so the resolver creates a duplicate. This fallback matches the same
// folded name across ALL kinds in the book via the app-maintained normalized_name
// column (the SAME textnorm.Normalize fold the per-kind resolver and the dedup
// backstop use — so 張若塵/张若尘/full-width/case variants all collapse), and returns
// the matched entity + its ACTUAL kind so the caller merges incoming attributes
// against that kind, not the (mis-tagged) extraction kind.
//
// Oldest-wins (created_at) makes the canonical entity deterministic. Name-only for
// now — a cross-kind ALIAS collision is rarer and left as a follow-up. Safe under the
// per-book extraction-writeback advisory lock (the loop is serialized per book), so a
// cross-kind check-then-merge can't race another job into a duplicate.
//
// scope (D-GLOSSARY-ENTITY-SCOPE) — same discipline as findEntityByNameOrAlias: the
// bulk extraction pipeline has no scope concept of its own (a caller here always
// passes ""), so this only matches an UNSCOPED entity. Without this filter, a
// human who had already disambiguated two same-named entities across worlds via
// scope_label could have a later extraction pass silently attach new attributes to
// WHICHEVER one is oldest, regardless of which world the chapter actually belongs
// to — worse than making a fresh unscoped draft, which is at least visibly wrong
// rather than silently mis-merged.
func (s *Server) findEntityCrossKind(ctx context.Context, q pgxRWQuerier, bookID uuid.UUID, name, scope string) (entityID, kindID uuid.UUID, err error) {
	normalized := normalizeEntity(name)
	if normalized == "" {
		return uuid.Nil, uuid.Nil, nil
	}
	err = q.QueryRow(ctx, `
		SELECT entity_id, kind_id FROM glossary_entities
		WHERE book_id = $1 AND normalized_name = $2 AND scope_label = $3 AND deleted_at IS NULL
		ORDER BY created_at, entity_id
		LIMIT 1`, bookID, normalized, scope).Scan(&entityID, &kindID)
	if err == pgx.ErrNoRows {
		return uuid.Nil, uuid.Nil, nil
	}
	if err != nil {
		return uuid.Nil, uuid.Nil, err
	}
	return entityID, kindID, nil
}

// entityHasTag reports whether the entity's tags array contains tag.
// Used by the AI-writeback tombstone gate (ai-rejected). Returns false
// if the entity is gone (no row) — a deleted target can't be tombstoned.
func (s *Server) entityHasTag(ctx context.Context, q pgxRWQuerier, entityID uuid.UUID, tag string) (bool, error) {
	var has bool
	err := q.QueryRow(ctx,
		`SELECT $2 = ANY(tags) FROM glossary_entities WHERE entity_id = $1`,
		entityID, tag,
	).Scan(&has)
	if err == pgx.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return has, nil
}

// createExtractedEntity creates a new entity with all provided attributes.
func (s *Server) createExtractedEntity(
	ctx context.Context,
	q pgxRWQuerier,
	bookID, kindID uuid.UUID,
	ent extractedEntity,
	actions map[string]string,
	attrDefMap map[string]uuid.UUID,
	sourceLang string,
	tags []string,
) (entityID uuid.UUID, written []string, skipped []attrSkip, err error) {
	if tags == nil {
		tags = []string{} // tags column is NOT NULL DEFAULT '{}'
	}
	err = q.QueryRow(ctx, `
		INSERT INTO glossary_entities (book_id, kind_id, status, tags)
		VALUES ($1, $2, 'draft', $3)
		RETURNING entity_id
	`, bookID, kindID, tags).Scan(&entityID)
	if err != nil {
		return uuid.Nil, nil, nil, fmt.Errorf("insert entity: %w", err)
	}

	// Insert name attribute
	nameDefID, ok := attrDefMap[kindID.String()+":name"]
	if ok {
		_, err = q.Exec(ctx, `
			INSERT INTO entity_attribute_values (entity_id, attr_def_id, original_language, original_value)
			VALUES ($1, $2, $3, $4)
			ON CONFLICT (entity_id, attr_def_id) DO NOTHING
		`, entityID, nameDefID, sourceLang, ent.Name)
		if err != nil {
			return uuid.Nil, nil, nil, fmt.Errorf("insert name attr: %w", err)
		}
		written = append(written, "name")
	}

	// Insert other attributes
	var unmatchedCodes, unmatchedNotes []string
	for code, val := range ent.Attributes {
		defID, ok := attrDefMap[kindID.String()+":"+code]
		if !ok {
			// D-GLOSSARY-UNMATCHED-ATTR-FALLBACK: a code the kind hasn't registered
			// (e.g. an AI proposal guessing a field name) is captured into the kind's
			// "description" catch-all below rather than dropped — glossary content is
			// authored prose, not a rigid schema; losing the observation is worse than
			// filing it under a generic heading (see appendUnmatchedAttrsToFallback).
			unmatchedCodes = append(unmatchedCodes, code)
			unmatchedNotes = append(unmatchedNotes, fmt.Sprintf("- %s: %s", code, serializeValue(val)))
			continue
		}
		serialized := serializeValue(val)
		_, err = q.Exec(ctx, `
			INSERT INTO entity_attribute_values (entity_id, attr_def_id, original_language, original_value)
			VALUES ($1, $2, $3, $4)
			ON CONFLICT (entity_id, attr_def_id) DO NOTHING
		`, entityID, defID, sourceLang, serialized)
		if err != nil {
			return uuid.Nil, nil, nil, fmt.Errorf("insert attr %s: %w", code, err)
		}
		// D-GLOSSARY-MULTIROW slice 2 — seed per-item rows for a list value on create
		// (scalar ⇒ no-op) so a freshly-created list attr is item-consistent for
		// verify/tombstone without waiting for a later append.
		if e := syncListItems(ctx, q, entityID, defID, serialized, "machine", firstChapterIDFromLinks(ent.ChapterLinks)); e != nil {
			return uuid.Nil, nil, nil, fmt.Errorf("insert attr %s (items): %w", code, e)
		}
		written = append(written, code)
	}
	if len(unmatchedNotes) > 0 {
		ok, reason, ferr := appendUnmatchedAttrsToFallback(ctx, q, entityID, kindID, attrDefMap, sourceLang, unmatchedNotes)
		if ferr != nil {
			return uuid.Nil, nil, nil, ferr
		}
		if ok {
			written = markDescriptionWritten(written)
		} else {
			for _, code := range unmatchedCodes {
				skipped = append(skipped, attrSkip{code, reason})
			}
		}
	}

	// D-GLOSSARY-ST-DEDUP M3a: stamp the app-maintained dedup key from the
	// just-landed name (cached_name is set by the snapshot trigger on the name EAV).
	if err := refreshEntityDedupKey(ctx, q, entityID); err != nil {
		return uuid.Nil, nil, nil, fmt.Errorf("refresh dedup key: %w", err)
	}
	if skipped == nil {
		skipped = []attrSkip{}
	}
	return entityID, written, skipped, nil
}

// appendUnmatchedAttrsToFallback captures attribute codes a kind hasn't registered
// into that kind's "description" textarea (D-GLOSSARY-UNMATCHED-ATTR-FALLBACK) instead
// of silently dropping them — a glossary/wiki entity is authored prose, not a rigid
// schema, so an unrecognized-but-real observation is worth keeping even if it can't be
// filed under its own field yet. Appends (never overwrites) so repeated extraction runs
// accumulate rather than clobber. Respects the INV-8 verified-clobber guard: a
// human-curated description is never machine-appended to. Returns appended=true (the
// caller should report the attr code as "description", per INV-FACTS/§12 — NEVER under
// its own original code, since no fact-worthy attr_def exists for it; see the two call
// sites) or appended=false with a reason ("unmapped" — the kind has no "description"
// attr_def at all, or "verified" — INV-8 blocked the write), in which case the caller
// keeps its prior silent-skip behavior for those attribute codes.
func appendUnmatchedAttrsToFallback(
	ctx context.Context, q pgxRWQuerier, entityID, kindID uuid.UUID,
	attrDefMap map[string]uuid.UUID, sourceLang string, lines []string,
) (appended bool, reason string, err error) {
	descID, ok := attrDefMap[kindID.String()+":description"]
	if !ok {
		return false, "unmapped", nil
	}
	var existingValue, existingConfidence string
	selErr := q.QueryRow(ctx, `
		SELECT original_value, confidence FROM entity_attribute_values
		WHERE entity_id = $1 AND attr_def_id = $2
	`, entityID, descID).Scan(&existingValue, &existingConfidence)
	exists := selErr == nil
	if exists && existingConfidence == "verified" {
		return false, "verified", nil
	}
	appendText := strings.Join(lines, "\n")
	if exists && existingValue != "" {
		appendText = existingValue + "\n" + appendText
	}
	if exists {
		_, err = q.Exec(ctx, `
			UPDATE entity_attribute_values SET original_value = $1
			WHERE entity_id = $2 AND attr_def_id = $3
		`, appendText, entityID, descID)
	} else {
		_, err = q.Exec(ctx, `
			INSERT INTO entity_attribute_values (entity_id, attr_def_id, original_language, original_value)
			VALUES ($1, $2, $3, $4)
		`, entityID, descID, sourceLang, appendText)
	}
	if err != nil {
		return false, "", fmt.Errorf("append unmatched attrs to description: %w", err)
	}
	return true, "", nil
}

// markDescriptionWritten adds "description" to a written-codes list exactly once —
// shared by create/merge so a fallback append is reported truthfully (Status/back-compat
// AttributesWritten) WITHOUT ever adding the original unmatched code. /review-impl HIGH:
// the original code has no attr_def, so passing it to emitChapterFacts's writtenCodes
// (which looks up ent.Attributes[code] and emits a fact under THAT code) would mint a
// phantom entity_facts row for an attribute that has no EAV cell — a fact SSOT (INV-FACTS)
// that permanently disagrees with the EAV projection it's supposed to back, surviving
// even after the description text is edited. "description" is always a real attr_def
// here (the fallback only fires when one exists), so it's fact-emission-safe: the shared
// emit path re-reads ent.Attributes["description"] and no-ops when that key is absent.
func markDescriptionWritten(written []string) []string {
	for _, c := range written {
		if c == "description" {
			return written
		}
	}
	return append(written, "description")
}

// mergeExtractedEntity merges attributes into an existing entity. The action is the
// per-extraction profile directive (fill/overwrite/append/skip); when the profile does NOT
// specify one, the attribute's AUTHORED merge_strategy is the default (MERGE/M5 slice 2 —
// strategy is the default, profile overrides). The verified-clobber guard (INV-8) supersedes
// whichever action results.
func (s *Server) mergeExtractedEntity(
	ctx context.Context,
	q pgxRWQuerier,
	entityID, kindID uuid.UUID,
	ent extractedEntity,
	actions map[string]string,
	strategyMap map[string]string,
	attrDefMap map[string]uuid.UUID,
	sourceLang string,
) (written []string, skipped []attrSkip, err error) {
	var unmatchedCodes []string
	var unmatchedNotes []string
	for code, val := range ent.Attributes {
		defID, ok := attrDefMap[kindID.String()+":"+code]
		if !ok {
			// D-GLOSSARY-UNMATCHED-ATTR-FALLBACK — see appendUnmatchedAttrsToFallback.
			unmatchedCodes = append(unmatchedCodes, code)
			unmatchedNotes = append(unmatchedNotes, fmt.Sprintf("- %s: %s", code, serializeValue(val)))
			continue
		}
		// Resolve the effective action: the profile overrides; otherwise the authored
		// merge_strategy default governs (fill_if_empty→fill, replace→overwrite,
		// append→append, manual→queue for review). An explicit profile 'skip' wins.
		action, specified := actions[code]
		if action == "skip" {
			skipped = append(skipped, attrSkip{code, "no_action"})
			continue
		}
		// "default" is the explicit "defer to the authored merge_strategy" sentinel
		// (D-EXTRACT-ATTR-MERGE-DEFAULTS) — the worker/FE send it instead of forcing
		// "fill", so the seeded heuristic (append/overwrite/fill) governs. Treated
		// identically to an omitted/empty action.
		if !specified || action == "" || action == "default" {
			strat := strategyMap[kindID.String()+":"+code]
			if strat == "manual" {
				skipped = append(skipped, attrSkip{code, "manual"})
				continue
			}
			action = strategyToAction(strat)
		}

		serialized := serializeValue(val)

		// Check existing value + its trust marker (MERGE/M5) + its surrogate id (the
		// child-item FK target, D-GLOSSARY-MULTIROW-ATTR-VALUES).
		var existingValue string
		var existingConfidence string
		var existingAttrValueID uuid.UUID
		var attrValueExists bool
		err := q.QueryRow(ctx, `
			SELECT attr_value_id, original_value, confidence FROM entity_attribute_values
			WHERE entity_id = $1 AND attr_def_id = $2
		`, entityID, defID).Scan(&existingAttrValueID, &existingValue, &existingConfidence)
		if err == nil {
			attrValueExists = true
		}

		// INV-8 verified-clobber guard — a human-authored ('verified') SOURCE value
		// supersedes the machine merge action: never overwrite it, queue for manual review
		// (skip-reason 'verified'). Checked at WRITE time against the stored marker, never
		// assumed. This is the T2 fix — a re-extraction can no longer silently clobber a
		// value the user curated via the editor / apply-edit.
		if attrValueExists && existingConfidence == "verified" {
			skipped = append(skipped, attrSkip{code, "verified"})
			continue
		}

		if action == "fill" {
			if attrValueExists && existingValue != "" {
				skipped = append(skipped, attrSkip{code, "fill_occupied"})
				continue
			}
			// Fill empty value
			if attrValueExists {
				_, err = q.Exec(ctx, `
					UPDATE entity_attribute_values SET original_value = $1, original_language = $2
					WHERE entity_id = $3 AND attr_def_id = $4
				`, serialized, sourceLang, entityID, defID)
			} else {
				_, err = q.Exec(ctx, `
					INSERT INTO entity_attribute_values (entity_id, attr_def_id, original_language, original_value)
					VALUES ($1, $2, $3, $4)
				`, entityID, defID, sourceLang, serialized)
			}
			if err != nil {
				return nil, nil, fmt.Errorf("fill attr %s: %w", code, err)
			}
			// D-GLOSSARY-MULTIROW slice 2 — keep the per-item rows in step for a list value
			// (scalar ⇒ no-op). A machine fill writes machine items with chapter provenance.
			if e := syncListItems(ctx, q, entityID, defID, serialized, "machine", firstChapterIDFromLinks(ent.ChapterLinks)); e != nil {
				return nil, nil, fmt.Errorf("fill attr %s (items): %w", code, e)
			}
			written = append(written, code)
		} else if action == "overwrite" {
			// Log to extraction_audit_log before overwriting
			if attrValueExists {
				chapterID := firstChapterIDFromLinks(ent.ChapterLinks)
				// /review-impl (M1) — must HARD-FAIL inside the writeback tx, not warn:
				// a swallowed Exec error POISONS the transaction (pgx aborts every later
				// statement until rollback), so the next attr's UPDATE would fail with a
				// confusing "current transaction is aborted" instead of this real cause.
				if _, auditErr := q.Exec(ctx, `
					INSERT INTO extraction_audit_log (entity_id, attr_def_id, chapter_id, old_value, new_value)
					VALUES ($1, $2, $3, $4, $5)
				`, entityID, defID, chapterID, existingValue, serialized); auditErr != nil {
					return nil, nil, fmt.Errorf("audit log attr %s: %w", code, auditErr)
				}

				_, err = q.Exec(ctx, `
					UPDATE entity_attribute_values SET original_value = $1, original_language = $2
					WHERE entity_id = $3 AND attr_def_id = $4
				`, serialized, sourceLang, entityID, defID)
			} else {
				_, err = q.Exec(ctx, `
					INSERT INTO entity_attribute_values (entity_id, attr_def_id, original_language, original_value)
					VALUES ($1, $2, $3, $4)
				`, entityID, defID, sourceLang, serialized)
			}
			if err != nil {
				return nil, nil, fmt.Errorf("overwrite attr %s: %w", code, err)
			}
			// D-GLOSSARY-MULTIROW slice 2 — replace the per-item rows for a list value
			// (scalar ⇒ no-op), closing the slice-1 overwrite→append divergence. Machine
			// items with chapter provenance.
			if e := syncListItems(ctx, q, entityID, defID, serialized, "machine", firstChapterIDFromLinks(ent.ChapterLinks)); e != nil {
				return nil, nil, fmt.Errorf("overwrite attr %s (items): %w", code, e)
			}
			written = append(written, code)
		} else if action == "append" || action == "summarize" {
			// D-GLOSSARY-MULTIROW-ATTR-VALUES slice 1 — per-item append. Each incoming
			// element becomes a child row (its own confidence/status/source-chapter); the
			// list is deduped by normalized value via UNIQUE(attr_value_id, item_norm) +
			// ON CONFLICT DO NOTHING, so a re-append is a no-op → skip 'unchanged'. The
			// whole op runs under the per-book writeback lock (this tx), so the cache
			// rebuild is race-free. original_value is kept as the write-synced cache of the
			// ACTIVE items (rebuildItemsCache) so every existing reader is unchanged.
			//
			// #26/#7 — `summarize` shares this RAW layer verbatim (lossless provenance);
			// it differs only in that a real change also flags canonical_dirty so the
			// end-of-extraction-job LLM pass rewrites the accumulated raw items into one
			// deduped canonical_value (see the dirty-set below + resummarize endpoints).
			incoming := parseListValue(serialized)
			if len(dedupNormalized(incoming)) == 0 {
				// nothing meaningful to append (empty/whitespace input)
				skipped = append(skipped, attrSkip{code, "unchanged"})
				continue
			}
			attrValueID := existingAttrValueID
			seeded := false
			if !attrValueExists {
				// Materialize the EAV first (cache seeded empty; rebuilt below). RETURNING
				// gives us the child-FK target.
				if err = q.QueryRow(ctx, `
					INSERT INTO entity_attribute_values (entity_id, attr_def_id, original_language, original_value)
					VALUES ($1, $2, $3, '[]')
					RETURNING attr_value_id
				`, entityID, defID, sourceLang).Scan(&attrValueID); err != nil {
					return nil, nil, fmt.Errorf("append attr %s (create): %w", code, err)
				}
			} else if seeded, err = ensureItemsMaterialized(ctx, q, attrValueID, existingValue, existingConfidence); err != nil {
				// First per-item touch of a value first written as a scalar/legacy list:
				// seed its existing elements so the cache rebuild doesn't drop them.
				return nil, nil, fmt.Errorf("append attr %s (materialize): %w", code, err)
			}
			added, err := appendListItems(ctx, q, attrValueID, incoming, firstChapterIDFromLinks(ent.ChapterLinks))
			if err != nil {
				return nil, nil, fmt.Errorf("append attr %s (items): %w", code, err)
			}
			// Rebuild the cache whenever the item set changed OR we just materialized a
			// legacy scalar (canonicalize it to the active-item JSON array — INV-MR1 never
			// diverges, even on a no-op re-append).
			if added > 0 || seeded {
				if err := rebuildItemsCache(ctx, q, attrValueID); err != nil {
					return nil, nil, fmt.Errorf("append attr %s (cache): %w", code, err)
				}
			}
			if added == 0 && attrValueExists {
				// no NEW element (every incoming item already present) → idempotent;
				// report 'unchanged' (the cache may have canonicalized, but the active set
				// is the same). Preserves the slice-2 'unchanged' contract. summarize does
				// NOT re-dirty here — an unchanged raw set means the canonical is still valid.
				skipped = append(skipped, attrSkip{code, "unchanged"})
				continue
			}
			// #26/#7 — summarize: a real raw-layer change invalidates the canonical value.
			// Flag it so the end-of-extraction-job resummarize pass rewrites it (the LLM
			// rewrite runs OUT of this tx — never inline). Same EAV, same book scope.
			if action == "summarize" {
				if _, err := q.Exec(ctx, `
					UPDATE entity_attribute_values SET canonical_dirty = true WHERE attr_value_id = $1
				`, attrValueID); err != nil {
					return nil, nil, fmt.Errorf("summarize attr %s (dirty): %w", code, err)
				}
			}
			written = append(written, code)
		}
	}

	if len(unmatchedNotes) > 0 {
		// /review-impl HIGH fix: report "description" (a real attr_def), never the
		// original unmatched codes — see markDescriptionWritten's doc comment for why
		// reporting the raw code here would mint a phantom INV-FACTS entity_facts row.
		ok, reason, ferr := appendUnmatchedAttrsToFallback(ctx, q, entityID, kindID, attrDefMap, sourceLang, unmatchedNotes)
		if ferr != nil {
			return nil, nil, ferr
		}
		if ok {
			written = markDescriptionWritten(written)
		} else {
			for _, code := range unmatchedCodes {
				skipped = append(skipped, attrSkip{code, reason})
			}
		}
	}

	// Touch updated_at. /review-impl (M1): hard-fail, not warn — a swallowed error
	// here poisons the writeback tx (this is the LAST statement of the merge, so the
	// poison would surface on the NEXT entity's resolver query or at commit).
	if len(written) > 0 {
		if _, err := q.Exec(ctx, `UPDATE glossary_entities SET updated_at = now() WHERE entity_id = $1`, entityID); err != nil {
			return nil, nil, fmt.Errorf("touch updated_at: %w", err)
		}
		// D-GLOSSARY-ST-DEDUP M3a: if the name/term was among the written attrs the
		// dedup key must follow it. Idempotent (no-op when cached_name is unchanged).
		if err := refreshEntityDedupKey(ctx, q, entityID); err != nil {
			return nil, nil, fmt.Errorf("refresh dedup key: %w", err)
		}
	}

	if written == nil {
		written = []string{}
	}
	if skipped == nil {
		skipped = []attrSkip{}
	}
	return written, skipped, nil
}

// evidenceChapterFor resolves the chapter an extracted quote belongs to: the chapter THIS
// writeback processed (reqChapterID — where the quote was extracted), with title/index from the
// matching ChapterLink. Falls back to the entity's FIRST link only when reqChapterID is unset
// (the legacy single-entity / MCP path). Fixes the firstChapterID bug (D-EVIDENCE-PROVENANCE-
// OVERHAUL M2) that stamped every quote with the entity's first-ever appearance — so a
// chapter-50 quote on a recurring character was labeled chapter 1, making evidence un-traceable.
func evidenceChapterFor(reqChapterID string, links []chapterLinkIn) (*uuid.UUID, string, *int) {
	if reqChapterID != "" {
		if id, err := uuid.Parse(reqChapterID); err == nil {
			for _, cl := range links {
				if cl.ChapterID == reqChapterID {
					ci := cl.ChapterIndex
					return &id, cl.ChapterTitle, &ci
				}
			}
			// Valid scope chapter but the worker didn't include a matching link → still stamp
			// the correct chapter id; title/index are then filled by the chapter-title backfill.
			return &id, "", nil
		}
	}
	if len(links) > 0 {
		if id, err := uuid.Parse(links[0].ChapterID); err == nil {
			ci := links[0].ChapterIndex
			return &id, links[0].ChapterTitle, &ci
		}
	}
	return nil, "", nil
}

// firstChapterIDFromLinks extracts the first chapter UUID (nullable) from chapter links.
func firstChapterIDFromLinks(links []chapterLinkIn) *uuid.UUID {
	if len(links) == 0 {
		return nil
	}
	id, err := uuid.Parse(links[0].ChapterID)
	if err != nil {
		return nil
	}
	return &id
}

// serializeValue converts an LLM output value to string for storage.
// Tags arrays are JSON-serialized; scalars are stringified.
func serializeValue(val any) string {
	switch v := val.(type) {
	case string:
		return v
	case []any:
		b, _ := json.Marshal(v)
		return string(b)
	case []string:
		b, _ := json.Marshal(v)
		return string(b)
	case float64:
		return strconv.FormatFloat(v, 'f', -1, 64)
	case bool:
		if v {
			return "true"
		}
		return "false"
	case nil:
		return ""
	default:
		b, _ := json.Marshal(v)
		return string(b)
	}
}

// parseListValue interprets a stored attribute value as a string list (delegates to
// the shared textnorm.ParseList — the single impl shared with the migration backfill,
// D-GLOSSARY-MULTIROW-ATTR-VALUES normalize-parity).
func parseListValue(s string) []string {
	return textnorm.ParseList(s)
}

// ── Name normalization ──────────────────────────────────────────────────────

// normalizeEntity prepares a name string for dedup comparison (delegates to the
// shared textnorm.Normalize — NFC, trim, collapse whitespace, lowercase). Shared
// with the migration backfill so the per-item child rows dedup identically to the
// runtime append path (D-GLOSSARY-MULTIROW-ATTR-VALUES normalize-parity).
func normalizeEntity(s string) string {
	return textnorm.Normalize(s)
}

// Ensure pgx import is used
var _ = pgx.ErrNoRows

// queryInt parses a query string value as int, returning defaultVal on failure.
func queryInt(s string, defaultVal int) int {
	if s == "" {
		return defaultVal
	}
	v, err := strconv.Atoi(s)
	if err != nil {
		return defaultVal
	}
	return v
}

// ── helpers ─────────────────────────────────────────────────────────────────

// tagsOverlap returns true if any element in a appears in b (case-sensitive).
func tagsOverlap(a, b []string) bool {
	set := make(map[string]struct{}, len(b))
	for _, v := range b {
		set[v] = struct{}{}
	}
	for _, v := range a {
		if _, ok := set[v]; ok {
			return true
		}
	}
	return false
}

// containsTag returns true if tags contains the given tag.
func containsTag(tags []string, tag string) bool {
	for _, t := range tags {
		if t == tag {
			return true
		}
	}
	return false
}

// ── K16.2: Entity count for cost estimation ───────────────────────────────

// internalEntityCount returns the count of non-deleted glossary entities
// for a book. Used by knowledge-service's extraction cost estimation
// endpoint (K16.2). Lightweight — single COUNT query, no pagination.
// Returns 0 for nonexistent books — safe default for cost estimation
// (the caller treats 0 as "no glossary entities to process").
//
// Route: GET /internal/books/{book_id}/entity-count
func (s *Server) internalEntityCount(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		EntityCountTotal.WithLabelValues(OutcomeValidationError).Inc()
		return
	}
	var count int
	err := s.pool.QueryRow(r.Context(),
		`SELECT COUNT(*) FROM glossary_entities WHERE book_id = $1 AND deleted_at IS NULL`,
		bookID,
	).Scan(&count)
	if err != nil {
		EntityCountTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to count entities")
		return
	}
	EntityCountTotal.WithLabelValues(OutcomeOK).Inc()
	writeJSON(w, http.StatusOK, map[string]any{"count": count})
}

// internalSuggestionsCount — GET /internal/books/{book_id}/suggestions-count.
//
// The entity-triage rail's completion signal for the Track-C rail driver: how many
// AI-suggested items still await a triage decision. It reuses the tool's OWN producer
// (queryAISuggestions with status="draft") rather than re-deriving the predicate, so the
// count the driver grounds on can never drift from the pile the agent actually sees via
// glossary_list_ai_suggestions — a keep/throw-out/combine decision moves an item off 'draft',
// so this counts DOWN as the user triages, reaching 0 exactly when the pile is clean.
// Auth-free like its siblings: this is an /internal route, the caller (chat-service) owns the
// grant check on the session's book.
func (s *Server) internalSuggestionsCount(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	_, total, err := s.queryAISuggestions(r.Context(), bookID, "draft")
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to count suggestions")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"count": total})
}

// ── C12c-a: glossary entities listing for knowledge-service sync ──────────

// entitiesListItem is a single entity in the listInternalEntities response.
// Matches the wire contract documented in C12c-a DESIGN: fields the
// knowledge-service sync helper (sync_glossary_entity_to_neo4j) consumes.
type entitiesListItem struct {
	EntityID         string   `json:"entity_id"`
	Name             string   `json:"name"`
	KindCode         string   `json:"kind_code"`
	Aliases          []string `json:"aliases"`
	ShortDescription *string  `json:"short_description"`
}

type entitiesListResp struct {
	Items      []entitiesListItem `json:"items"`
	NextCursor *string            `json:"next_cursor"`
}

// entitiesCursor is the decoded payload of the ?cursor=... query param.
// We encode/decode a single entity_id (UUID has total ordering, so
// (entity_id > $cursor) is a correct seek predicate). Wrapped in a
// struct so future additions (e.g. per-kind cursors) don't break
// forward compatibility of the opaque cursor.
type entitiesCursor struct {
	EntityID string `json:"entity_id"`
}

func encodeEntitiesCursor(entityID uuid.UUID) string {
	raw, _ := json.Marshal(entitiesCursor{EntityID: entityID.String()})
	return base64.RawURLEncoding.EncodeToString(raw)
}

func decodeEntitiesCursor(s string) (uuid.UUID, error) {
	if s == "" {
		return uuid.Nil, errEmptyCursor
	}
	raw, err := base64.RawURLEncoding.DecodeString(s)
	if err != nil {
		return uuid.Nil, fmt.Errorf("invalid base64: %w", err)
	}
	var c entitiesCursor
	if err := json.Unmarshal(raw, &c); err != nil {
		return uuid.Nil, fmt.Errorf("invalid json: %w", err)
	}
	if c.EntityID == "" {
		return uuid.Nil, fmt.Errorf("missing entity_id")
	}
	id, err := uuid.Parse(c.EntityID)
	if err != nil {
		return uuid.Nil, fmt.Errorf("invalid entity_id: %w", err)
	}
	return id, nil
}

var errEmptyCursor = fmt.Errorf("empty cursor")

// internalListEntities returns paginated, alive glossary entities for a
// book. Used by knowledge-service's extraction worker to drive the
// `scope='glossary_sync'` job branch (C12c-a).
//
// Query params:
//   - cursor: opaque base64 (b64-JSON{entity_id}) — null/missing starts
//     from the first entity (entity_id ASC).
//   - limit: page size, default 100, clamped to [1, 200].
//
// Response shape (matches entitiesListResp):
//
//	{"items": [{entity_id, name, kind_code, aliases, short_description}],
//	 "next_cursor": "<b64>" | null}
//
// Filters: alive = true AND deleted_at IS NULL (both checks; alive is
// the soft-delete flag from K15.x, deleted_at is the hard-delete
// tombstone — dropping either would leak tombstoned entities).
//
// Route: GET /internal/books/{book_id}/entities
func (s *Server) internalListEntities(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		EntitiesListTotal.WithLabelValues(OutcomeValidationError).Inc()
		return
	}
	q := r.URL.Query()

	limit := queryInt(q.Get("limit"), 100)
	if limit < 1 {
		limit = 1
	}
	if limit > 200 {
		limit = 200
	}

	var afterID uuid.UUID
	hasAfter := false
	if raw := q.Get("cursor"); raw != "" {
		id, err := decodeEntitiesCursor(raw)
		if err != nil {
			EntitiesListTotal.WithLabelValues(OutcomeValidationError).Inc()
			writeError(w, http.StatusBadRequest, "GLOSS_BAD_CURSOR",
				"invalid cursor: "+err.Error())
			return
		}
		afterID = id
		hasAfter = true
	}

	// Peek-ahead pattern: fetch limit+1; if we get that many back, the
	// (limit+1)-th row's entity_id becomes the next_cursor, and we
	// trim to `limit`.
	query := `
		SELECT
			e.entity_id,
			k.code AS kind_code,
			COALESCE(name_av.original_value, '') AS name,
			COALESCE(alias_av.original_value, '') AS aliases_raw,
			-- Prefer the AUTHORED canon column (the SSOT short_description set via
			-- the canon-content path / wiki — see DEFERRED-053) over the EAV
			-- attribute, which extract-entities cannot populate (silent no-op).
			-- The enrichment contradiction check (F-C12-1) reads this to detect a
			-- generated fact that NEGATES authored canon. Falls back to the EAV
			-- value when the column is null (backward-compatible).
			COALESCE(NULLIF(e.short_description, ''), short_av.original_value) AS short_description
		FROM glossary_entities e
		JOIN book_kinds k ON k.book_kind_id = e.kind_id
		LEFT JOIN entity_attribute_values name_av
			ON name_av.entity_id = e.entity_id
			AND name_av.attr_def_id = (
				SELECT ba.attr_id FROM book_attributes ba
				JOIN book_genres g ON g.genre_id = ba.genre_id
				WHERE ba.kind_id = e.kind_id AND ba.code = 'name'
				ORDER BY (g.code = 'universal') DESC LIMIT 1
			)
		LEFT JOIN entity_attribute_values alias_av
			ON alias_av.entity_id = e.entity_id
			AND alias_av.attr_def_id = (
				SELECT ba.attr_id FROM book_attributes ba
				JOIN book_genres g ON g.genre_id = ba.genre_id
				WHERE ba.kind_id = e.kind_id AND ba.code = 'aliases'
				ORDER BY (g.code = 'universal') DESC LIMIT 1
			)
		LEFT JOIN entity_attribute_values short_av
			ON short_av.entity_id = e.entity_id
			AND short_av.attr_def_id = (
				SELECT ba.attr_id FROM book_attributes ba
				JOIN book_genres g ON g.genre_id = ba.genre_id
				WHERE ba.kind_id = e.kind_id AND ba.code = 'short_description'
				ORDER BY (g.code = 'universal') DESC LIMIT 1
			)
		WHERE e.book_id = $1
		  AND e.alive = true
		  AND e.deleted_at IS NULL
		  AND ($2::uuid IS NULL OR e.entity_id > $2::uuid)
		ORDER BY e.entity_id ASC
		LIMIT $3
	`
	var afterArg any
	if hasAfter {
		afterArg = afterID
	} else {
		afterArg = nil
	}

	rows, err := s.pool.Query(r.Context(), query, bookID, afterArg, limit+1)
	if err != nil {
		EntitiesListTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL",
			"failed to query glossary entities")
		return
	}
	defer rows.Close()

	// /review-impl MED#1 — track rowsScanned separately from the
	// items-filtered count. If the DB returned `limit+1` rows but
	// one was dropped by the empty-name filter, `len(items)` would
	// be exactly `limit` and the naive `len(items) > limit`
	// cursor-set check would silently terminate pagination,
	// dropping entities beyond the page. We detect the peek-ahead
	// via rowsScanned, and separately carry forward the last
	// entity_id we SAW (valid or filtered) as the cursor boundary.
	items := make([]entitiesListItem, 0, limit)
	var lastSeenID uuid.UUID
	rowsScanned := 0
	scanErrorCount := 0
	for rows.Next() {
		var (
			entityID   uuid.UUID
			kindCode   string
			name       string
			aliasesRaw string
			shortDesc  sql.NullString
		)
		if err := rows.Scan(&entityID, &kindCode, &name, &aliasesRaw, &shortDesc); err != nil {
			scanErrorCount++
			continue
		}
		rowsScanned++
		lastSeenID = entityID
		// Once we have `limit` items AND we've seen one additional
		// row (the peek-ahead), the (limit+1)-th row confirms there's
		// more data and we should emit a cursor.
		if rowsScanned > limit {
			// Don't push the peek-ahead row into items; it just signals
			// pagination should continue. The cursor uses the LAST
			// pushed item's id (set below).
			break
		}
		var aliases []string
		if aliasesRaw != "" {
			_ = json.Unmarshal([]byte(aliasesRaw), &aliases)
		}
		if aliases == nil {
			aliases = []string{}
		}
		if name == "" {
			// Skip nameless entities — sync_glossary_entity_to_neo4j
			// requires a non-empty name for canonicalization. The row
			// still counts toward rowsScanned so pagination advances
			// past it (otherwise a name-less row at the page boundary
			// would make us re-fetch it forever).
			continue
		}
		var shortPtr *string
		if shortDesc.Valid && shortDesc.String != "" {
			s := shortDesc.String
			shortPtr = &s
		}
		items = append(items, entitiesListItem{
			EntityID:         entityID.String(),
			Name:             name,
			KindCode:         kindCode,
			Aliases:          aliases,
			ShortDescription: shortPtr,
		})
	}
	if err := rows.Err(); err != nil {
		EntitiesListTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL",
			"failed to iterate glossary entities")
		return
	}

	// Emit next_cursor when we observed a peek-ahead row (rowsScanned
	// > limit). Cursor = last entity_id we saw at-or-before position
	// `limit` — that's the LAST row in `items` if non-empty, OR the
	// last seen id if every visible row was name-filtered out (rare
	// but possible).
	var nextCursor *string
	if rowsScanned > limit {
		var boundaryID uuid.UUID
		if len(items) > 0 {
			boundaryID, err = uuid.Parse(items[len(items)-1].EntityID)
			if err != nil {
				boundaryID = lastSeenID
			}
		} else {
			boundaryID = lastSeenID
		}
		c := encodeEntitiesCursor(boundaryID)
		nextCursor = &c
	}

	EntitiesListTotal.WithLabelValues(OutcomeOK).Inc()
	writeJSON(w, http.StatusOK, entitiesListResp{
		Items:      items,
		NextCursor: nextCursor,
	})
}
