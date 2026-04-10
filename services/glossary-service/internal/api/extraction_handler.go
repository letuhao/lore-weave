package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"regexp"
	"strconv"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"golang.org/x/text/unicode/norm"
)

// getExtractionProfile auto-resolves entity kinds + attributes for extraction
// based on the book's genre groups. Returns the full kinds metadata so the
// frontend can render the extraction profile dialog.
//
// Two routes share this handler:
//   - Public:   GET /v1/glossary/books/{book_id}/extraction-profile  (JWT auth)
//   - Internal: GET /internal/books/{book_id}/extraction-profile     (service token)
func (s *Server) getExtractionProfile(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	ctx := r.Context()

	// 1. Fetch the book's genre names from genre_groups table
	rows, err := s.pool.Query(ctx, `SELECT name FROM genre_groups WHERE book_id=$1 ORDER BY sort_order`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to fetch genres")
		return
	}
	var bookGenres []string
	for rows.Next() {
		var g string
		if err := rows.Scan(&g); err != nil {
			rows.Close()
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scan genre")
			return
		}
		bookGenres = append(bookGenres, g)
	}
	rows.Close()

	// 2. Fetch all entity kinds with their attributes, apply genre filtering
	//
	// Resolution rules from design doc §4.2:
	//   - Include system kinds where genre_tags overlap with book's genres
	//   - Always include system kinds with genre_tags containing 'universal'
	//   - Always include user-created kinds (is_default = false)
	//   - Exclude kinds where is_hidden = true
	kindRows, err := s.pool.Query(ctx, `
		SELECT kind_id, code, name, icon, is_default, genre_tags
		FROM entity_kinds
		WHERE is_hidden = false
		ORDER BY sort_order, name
	`)
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
		Icon         string    `json:"icon"`
		AutoSelected bool      `json:"auto_selected"`
		Attributes   []attrOut `json:"attributes"`
	}

	var kinds []kindOut
	for kindRows.Next() {
		var kindID, code, name, icon string
		var isDefault bool
		var kindGenreTags []string
		if err := kindRows.Scan(&kindID, &code, &name, &icon, &isDefault, &kindGenreTags); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scan kind")
			return
		}

		// Determine if this kind is auto-selected
		autoSelected := false
		if !isDefault {
			// User-created kinds are always included
			autoSelected = true
		} else {
			// System kind: check genre overlap or universal
			autoSelected = tagsOverlap(kindGenreTags, bookGenres) || containsTag(kindGenreTags, "universal")
		}

		// Fetch attributes for this kind
		attrRows, err := s.pool.Query(ctx, `
			SELECT code, name, field_type, description, auto_fill_prompt,
			       is_required, is_active, genre_tags
			FROM attribute_definitions
			WHERE kind_id = $1
			ORDER BY sort_order, name
		`, kindID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to fetch attributes")
			return
		}

		var attrs []attrOut
		for attrRows.Next() {
			var a attrOut
			var isActive bool
			var attrGenreTags []string
			if err := attrRows.Scan(&a.Code, &a.Name, &a.FieldType, &a.Description,
				&a.AutoFillPrompt, &a.IsRequired, &isActive, &attrGenreTags); err != nil {
				attrRows.Close()
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to scan attribute")
				return
			}

			// Determine auto_selected for this attribute:
			//   - is_required → always selected
			//   - !is_active → never selected
			//   - user-created kind → all active attrs selected (no genre filtering)
			//   - system kind → genre_tags empty OR overlaps with book's genres
			if !isActive {
				a.AutoSelected = false
			} else if a.IsRequired {
				a.AutoSelected = true
			} else if !isDefault {
				// User-created kind: all active attrs are auto-selected
				a.AutoSelected = true
			} else {
				a.AutoSelected = len(attrGenreTags) == 0 || tagsOverlap(attrGenreTags, bookGenres)
			}
			attrs = append(attrs, a)
		}
		attrRows.Close()

		if attrs == nil {
			attrs = []attrOut{}
		}
		kinds = append(kinds, kindOut{
			KindID:       kindID,
			Code:         code,
			Name:         name,
			Icon:         icon,
			AutoSelected: autoSelected,
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

// internalExtractionProfile is an alias for the same handler, used on the internal route.
func (s *Server) internalExtractionProfile(w http.ResponseWriter, r *http.Request) {
	s.getExtractionProfile(w, r)
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
		return
	}
	ctx := r.Context()
	q := r.URL.Query()

	alive := q.Get("alive") != "false" // default true
	minFreq := queryInt(q.Get("min_frequency"), 2)
	beforeIdx := queryInt(q.Get("before_chapter_index"), -1)
	recencyWindow := queryInt(q.Get("recency_window"), 100)
	limit := queryInt(q.Get("limit"), 50)

	// Build the query dynamically based on filters.
	// We join glossary_entities with entity_kinds and aggregate chapter_entity_links
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

	if alive {
		conditions = append(conditions, "e.alive = true")
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

	query := `
		SELECT
			e.entity_id,
			k.code AS kind_code,
			COALESCE(name_av.original_value, '') AS entity_name,
			COALESCE(alias_av.original_value, '') AS aliases_raw,
			COUNT(cl.link_id) AS frequency
		FROM glossary_entities e
		JOIN entity_kinds k ON k.kind_id = e.kind_id
		LEFT JOIN entity_attribute_values name_av
			ON name_av.entity_id = e.entity_id
			AND name_av.attr_def_id = (
				SELECT attr_def_id FROM attribute_definitions
				WHERE kind_id = e.kind_id AND code = 'name' LIMIT 1
			)
		LEFT JOIN entity_attribute_values alias_av
			ON alias_av.entity_id = e.entity_id
			AND alias_av.attr_def_id = (
				SELECT attr_def_id FROM attribute_definitions
				WHERE kind_id = e.kind_id AND code = 'aliases' LIMIT 1
			)
		LEFT JOIN chapter_entity_links cl
			ON ` + linkCondition + `
		WHERE ` + strings.Join(conditions, " AND ") + `
		GROUP BY e.entity_id, k.code, name_av.original_value, alias_av.original_value
		HAVING ` + strings.Join(havingClauses, " AND ") + `
		ORDER BY COUNT(cl.link_id) DESC
		LIMIT ` + limitParam

	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to query known entities")
		return
	}
	defer rows.Close()

	type entityOut struct {
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
			Name:     name,
			KindCode: kindCode,
			Aliases:  aliases,
			Freq:     freq,
		})
	}
	if result == nil {
		result = []entityOut{}
	}
	writeJSON(w, http.StatusOK, result)
}

// ── GEP-BE-03: Bulk upsert endpoint ─────────────────────────────────────────

// bulkUpsertRequest is the request body for POST /internal/books/{book_id}/extract-entities.
type bulkUpsertRequest struct {
	SourceLanguage   string                       `json:"source_language"`
	AttributeActions map[string]map[string]string  `json:"attribute_actions"` // kind_code → attr_code → "fill"|"overwrite"
	Entities         []extractedEntity             `json:"entities"`
}

type extractedEntity struct {
	KindCode     string            `json:"kind_code"`
	Name         string            `json:"name"`
	Attributes   map[string]any    `json:"attributes"`
	Evidence     string            `json:"evidence"`
	ChapterLinks []chapterLinkIn   `json:"chapter_links"`
}

type chapterLinkIn struct {
	ChapterID    string `json:"chapter_id"`
	ChapterTitle string `json:"chapter_title"`
	ChapterIndex int    `json:"chapter_index"`
	Relevance    string `json:"relevance"`
}

type entityResult struct {
	EntityID          string   `json:"entity_id"`
	Name              string   `json:"name"`
	KindCode          string   `json:"kind_code"`
	Status            string   `json:"status"` // "created" | "updated" | "skipped"
	AttributesWritten []string `json:"attributes_written"`
	AttributesSkipped []string `json:"attributes_skipped"`
}

// bulkExtractEntities receives extracted entities from translation-service and upserts them.
//
//	POST /internal/books/{book_id}/extract-entities
func (s *Server) bulkExtractEntities(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	ctx := r.Context()

	var req bulkUpsertRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON body")
		return
	}
	if req.SourceLanguage == "" {
		req.SourceLanguage = "zh"
	}
	if len(req.Entities) == 0 {
		writeJSON(w, http.StatusOK, map[string]any{
			"created": 0, "updated": 0, "skipped": 0, "entities": []entityResult{},
		})
		return
	}

	// Pre-load kind_id map (code → kind_id)
	kindMap, err := s.loadKindMap(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to load kinds")
		return
	}

	// Pre-load attr_def map (kind_id+code → attr_def_id)
	attrDefMap, err := s.loadAttrDefMap(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to load attribute definitions")
		return
	}

	var (
		results  []entityResult
		created  int
		updated  int
		skipped  int
	)

	for _, ent := range req.Entities {
		kindID, kindOK := kindMap[ent.KindCode]
		if !kindOK {
			continue // unknown kind, skip
		}
		if ent.Name == "" {
			continue
		}

		actions := req.AttributeActions[ent.KindCode]
		if actions == nil {
			actions = map[string]string{}
		}

		// 1. Find existing entity by normalized name or alias match
		existingID, err := s.findEntityByNameOrAlias(ctx, bookID, kindID, ent.Name)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "entity lookup failed")
			return
		}

		var result entityResult
		result.Name = ent.Name
		result.KindCode = ent.KindCode

		if existingID == uuid.Nil {
			// 2. CREATE new entity
			entityID, err := s.createExtractedEntity(ctx, bookID, kindID, ent, actions, attrDefMap, req.SourceLanguage)
			if err != nil {
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to create entity: "+err.Error())
				return
			}
			result.EntityID = entityID.String()
			result.Status = "created"
			// All provided attributes are written on create
			result.AttributesWritten = make([]string, 0, len(ent.Attributes)+1)
			result.AttributesWritten = append(result.AttributesWritten, "name")
			for code := range ent.Attributes {
				result.AttributesWritten = append(result.AttributesWritten, code)
			}
			result.AttributesSkipped = []string{}
			created++
		} else {
			// 3. MERGE with existing entity
			written, skippedAttrs, err := s.mergeExtractedEntity(ctx, existingID, kindID, ent, actions, attrDefMap, req.SourceLanguage)
			if err != nil {
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to merge entity: "+err.Error())
				return
			}
			result.EntityID = existingID.String()
			result.AttributesWritten = written
			result.AttributesSkipped = skippedAttrs
			if len(written) > 0 {
				result.Status = "updated"
				updated++
			} else {
				result.Status = "skipped"
				skipped++
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
			_, _ = s.pool.Exec(ctx, `
				INSERT INTO chapter_entity_links (entity_id, chapter_id, chapter_title, chapter_index, relevance)
				VALUES ($1, $2, $3, $4, $5)
				ON CONFLICT (entity_id, chapter_id) DO UPDATE SET
					chapter_title = EXCLUDED.chapter_title,
					chapter_index = EXCLUDED.chapter_index,
					relevance = EXCLUDED.relevance
			`, entID, chID, cl.ChapterTitle, cl.ChapterIndex, relevance)
		}

		// 5. Add evidence (extraction quote)
		if ent.Evidence != "" {
			entID, _ := uuid.Parse(result.EntityID)
			nameAttrDefID, nameOK := attrDefMap[kindID.String()+":name"]
			if nameOK {
				// Get the name attr_value_id
				var nameAVID uuid.UUID
				err := s.pool.QueryRow(ctx, `
					SELECT attr_value_id FROM entity_attribute_values
					WHERE entity_id = $1 AND attr_def_id = $2
				`, entID, nameAttrDefID).Scan(&nameAVID)
				if err == nil {
					_, _ = s.pool.Exec(ctx, `
						INSERT INTO evidences (attr_value_id, chapter_id, evidence_type, original_language, original_text, note)
						VALUES ($1, $2, 'extraction_quote', $3, $4, 'auto-extracted by glossary extraction pipeline')
					`, nameAVID, s.firstChapterID(ent.ChapterLinks), req.SourceLanguage, ent.Evidence)
				}
			}
		}

		results = append(results, result)
	}

	if results == nil {
		results = []entityResult{}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"created":  created,
		"updated":  updated,
		"skipped":  skipped,
		"entities": results,
	})
}

// loadKindMap returns a map of kind code → kind_id.
func (s *Server) loadKindMap(ctx context.Context) (map[string]uuid.UUID, error) {
	rows, err := s.pool.Query(ctx, `SELECT kind_id, code FROM entity_kinds`)
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
	return m, nil
}

// loadAttrDefMap returns a map of "kind_id:code" → attr_def_id.
func (s *Server) loadAttrDefMap(ctx context.Context) (map[string]uuid.UUID, error) {
	rows, err := s.pool.Query(ctx, `SELECT attr_def_id, kind_id, code FROM attribute_definitions`)
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
	return m, nil
}

// findEntityByNameOrAlias looks up an existing entity by normalized name match,
// then by alias match if not found. Returns uuid.Nil if no match.
func (s *Server) findEntityByNameOrAlias(ctx context.Context, bookID, kindID uuid.UUID, name string) (uuid.UUID, error) {
	normalizedName := normalizeEntity(name)

	// Step 1: Try exact name match (normalized)
	rows, err := s.pool.Query(ctx, `
		SELECT ge.entity_id, eav.original_value
		FROM glossary_entities ge
		JOIN entity_attribute_values eav ON eav.entity_id = ge.entity_id
		JOIN attribute_definitions ad ON ad.attr_def_id = eav.attr_def_id
		WHERE ge.book_id = $1
		  AND ge.kind_id = $2
		  AND ad.code = 'name'
	`, bookID, kindID)
	if err != nil {
		return uuid.Nil, err
	}
	defer rows.Close()

	type nameEntry struct {
		entityID uuid.UUID
		name     string
	}
	var entries []nameEntry
	for rows.Next() {
		var e nameEntry
		if err := rows.Scan(&e.entityID, &e.name); err != nil {
			return uuid.Nil, err
		}
		if normalizeEntity(e.name) == normalizedName {
			return e.entityID, nil
		}
		entries = append(entries, e)
	}

	// Step 2: Check aliases (app-layer JSON parsing per design C1)
	aliasRows, err := s.pool.Query(ctx, `
		SELECT ge.entity_id, eav.original_value
		FROM glossary_entities ge
		JOIN entity_attribute_values eav ON eav.entity_id = ge.entity_id
		JOIN attribute_definitions ad ON ad.attr_def_id = eav.attr_def_id
		WHERE ge.book_id = $1
		  AND ge.kind_id = $2
		  AND ad.code = 'aliases'
		  AND eav.original_value != ''
	`, bookID, kindID)
	if err != nil {
		return uuid.Nil, err
	}
	defer aliasRows.Close()

	for aliasRows.Next() {
		var entityID uuid.UUID
		var aliasRaw string
		if err := aliasRows.Scan(&entityID, &aliasRaw); err != nil {
			return uuid.Nil, err
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

// createExtractedEntity creates a new entity with all provided attributes.
func (s *Server) createExtractedEntity(
	ctx context.Context,
	bookID, kindID uuid.UUID,
	ent extractedEntity,
	actions map[string]string,
	attrDefMap map[string]uuid.UUID,
	sourceLang string,
) (uuid.UUID, error) {
	var entityID uuid.UUID
	err := s.pool.QueryRow(ctx, `
		INSERT INTO glossary_entities (book_id, kind_id, status)
		VALUES ($1, $2, 'draft')
		RETURNING entity_id
	`, bookID, kindID).Scan(&entityID)
	if err != nil {
		return uuid.Nil, fmt.Errorf("insert entity: %w", err)
	}

	// Insert name attribute
	nameDefID, ok := attrDefMap[kindID.String()+":name"]
	if ok {
		_, err = s.pool.Exec(ctx, `
			INSERT INTO entity_attribute_values (entity_id, attr_def_id, original_language, original_value)
			VALUES ($1, $2, $3, $4)
			ON CONFLICT (entity_id, attr_def_id) DO NOTHING
		`, entityID, nameDefID, sourceLang, ent.Name)
		if err != nil {
			return uuid.Nil, fmt.Errorf("insert name attr: %w", err)
		}
	}

	// Insert other attributes
	for code, val := range ent.Attributes {
		defID, ok := attrDefMap[kindID.String()+":"+code]
		if !ok {
			continue
		}
		serialized := serializeValue(val)
		_, err = s.pool.Exec(ctx, `
			INSERT INTO entity_attribute_values (entity_id, attr_def_id, original_language, original_value)
			VALUES ($1, $2, $3, $4)
			ON CONFLICT (entity_id, attr_def_id) DO NOTHING
		`, entityID, defID, sourceLang, serialized)
		if err != nil {
			return uuid.Nil, fmt.Errorf("insert attr %s: %w", code, err)
		}
	}

	return entityID, nil
}

// mergeExtractedEntity merges attributes into an existing entity based on fill/overwrite actions.
func (s *Server) mergeExtractedEntity(
	ctx context.Context,
	entityID, kindID uuid.UUID,
	ent extractedEntity,
	actions map[string]string,
	attrDefMap map[string]uuid.UUID,
	sourceLang string,
) (written, skippedAttrs []string, err error) {
	for code, val := range ent.Attributes {
		defID, ok := attrDefMap[kindID.String()+":"+code]
		if !ok {
			continue
		}
		action := actions[code]
		if action == "" || action == "skip" {
			skippedAttrs = append(skippedAttrs, code)
			continue
		}

		serialized := serializeValue(val)

		// Check existing value
		var existingValue string
		var attrValueExists bool
		err := s.pool.QueryRow(ctx, `
			SELECT original_value FROM entity_attribute_values
			WHERE entity_id = $1 AND attr_def_id = $2
		`, entityID, defID).Scan(&existingValue)
		if err == nil {
			attrValueExists = true
		}

		if action == "fill" {
			if attrValueExists && existingValue != "" {
				skippedAttrs = append(skippedAttrs, code)
				continue
			}
			// Fill empty value
			if attrValueExists {
				_, err = s.pool.Exec(ctx, `
					UPDATE entity_attribute_values SET original_value = $1, original_language = $2
					WHERE entity_id = $3 AND attr_def_id = $4
				`, serialized, sourceLang, entityID, defID)
			} else {
				_, err = s.pool.Exec(ctx, `
					INSERT INTO entity_attribute_values (entity_id, attr_def_id, original_language, original_value)
					VALUES ($1, $2, $3, $4)
				`, entityID, defID, sourceLang, serialized)
			}
			if err != nil {
				return nil, nil, fmt.Errorf("fill attr %s: %w", code, err)
			}
			written = append(written, code)
		} else if action == "overwrite" {
			// Log to extraction_audit_log before overwriting
			if attrValueExists {
				chapterID := firstChapterIDFromLinks(ent.ChapterLinks)
				_, _ = s.pool.Exec(ctx, `
					INSERT INTO extraction_audit_log (entity_id, attr_def_id, chapter_id, old_value, new_value)
					VALUES ($1, $2, $3, $4, $5)
				`, entityID, defID, chapterID, existingValue, serialized)

				_, err = s.pool.Exec(ctx, `
					UPDATE entity_attribute_values SET original_value = $1, original_language = $2
					WHERE entity_id = $3 AND attr_def_id = $4
				`, serialized, sourceLang, entityID, defID)
			} else {
				_, err = s.pool.Exec(ctx, `
					INSERT INTO entity_attribute_values (entity_id, attr_def_id, original_language, original_value)
					VALUES ($1, $2, $3, $4)
				`, entityID, defID, sourceLang, serialized)
			}
			if err != nil {
				return nil, nil, fmt.Errorf("overwrite attr %s: %w", code, err)
			}
			written = append(written, code)
		}
	}

	// Touch updated_at
	if len(written) > 0 {
		_, _ = s.pool.Exec(ctx, `UPDATE glossary_entities SET updated_at = now() WHERE entity_id = $1`, entityID)
	}

	if written == nil {
		written = []string{}
	}
	if skippedAttrs == nil {
		skippedAttrs = []string{}
	}
	return written, skippedAttrs, nil
}

// firstChapterID extracts the first chapter UUID from chapter links input.
func (s *Server) firstChapterID(links []chapterLinkIn) *uuid.UUID {
	if len(links) == 0 {
		return nil
	}
	id, err := uuid.Parse(links[0].ChapterID)
	if err != nil {
		return nil
	}
	return &id
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

// ── Name normalization ──────────────────────────────────────────────────────

var wsCollapse = regexp.MustCompile(`\s+`)

// normalizeEntity prepares a name string for dedup comparison.
// Unicode NFC, trim, collapse whitespace, lowercase.
func normalizeEntity(s string) string {
	s = norm.NFC.String(s)
	s = strings.TrimSpace(s)
	s = wsCollapse.ReplaceAllString(s, " ")
	s = strings.ToLower(s)
	return s
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

