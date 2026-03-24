package api

import (
	"net/http"
	"time"

	"github.com/google/uuid"
)

// ── RAG export types ──────────────────────────────────────────────────────────

type ragTransExport struct {
	Language   string `json:"language"`
	Value      string `json:"value"`
	Confidence string `json:"confidence"`
}

type ragEvidExport struct {
	Type         string  `json:"type"`
	OriginalLang string  `json:"original_language"`
	Text         string  `json:"text"`
	Chapter      *string `json:"chapter,omitempty"`
	Location     string  `json:"location,omitempty"`
	Note         *string `json:"note,omitempty"`
}

type ragAttrExport struct {
	Code             string           `json:"code"`
	Name             string           `json:"name"`
	OriginalLanguage string           `json:"original_language"`
	OriginalValue    string           `json:"original_value"`
	Translations     []ragTransExport `json:"translations"`
	Evidences        []ragEvidExport  `json:"evidences"`
}

type ragLinkExport struct {
	ChapterTitle *string `json:"chapter_title"`
	Relevance    string  `json:"relevance"`
	Note         *string `json:"note,omitempty"`
}

type ragEntityExport struct {
	EntityID     string          `json:"entity_id"`
	Kind         string          `json:"kind"`
	DisplayName  string          `json:"display_name"`
	Status       string          `json:"status"`
	Tags         []string        `json:"tags"`
	ChapterLinks []ragLinkExport `json:"chapter_links"`
	Attributes   []ragAttrExport `json:"attributes"`
}

type ragExportResp struct {
	BookID      string            `json:"book_id"`
	ExportedAt  time.Time         `json:"exported_at"`
	ChapterID   *string           `json:"chapter_id,omitempty"`
	EntityCount int               `json:"entity_count"`
	Entities    []ragEntityExport `json:"entities"`
}

// ── GET /v1/glossary/books/{book_id}/export ───────────────────────────────────

func (s *Server) exportGlossary(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.verifyBookOwner(w, r.Context(), bookID, userID) {
		return
	}

	ctx := r.Context()
	q := r.URL.Query()

	// Optional chapter_id filter — export only entities linked to that chapter.
	var chapterFilter *uuid.UUID
	if cid := q.Get("chapter_id"); cid != "" {
		id, err := uuid.Parse(cid)
		if err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_ID", "invalid chapter_id")
			return
		}
		chapterFilter = &id
	}

	// ── Step 1: load active entities (optionally filtered by chapter) ──────────

	var entitySQL string
	var entityArgs []any
	if chapterFilter != nil {
		entitySQL = `
			SELECT e.entity_id, e.status, e.tags,
			       ek.code AS kind_code,
			       COALESCE((
			           SELECT eav.original_value FROM entity_attribute_values eav
			           JOIN attribute_definitions ad ON ad.attr_def_id = eav.attr_def_id
			           WHERE eav.entity_id = e.entity_id AND ad.code IN ('name','term')
			           ORDER BY ad.sort_order LIMIT 1
			       ), '') AS display_name
			FROM glossary_entities e
			JOIN entity_kinds ek ON ek.kind_id = e.kind_id
			WHERE e.book_id = $1 AND e.status = 'active'
			  AND EXISTS (
			      SELECT 1 FROM chapter_entity_links
			      WHERE entity_id = e.entity_id AND chapter_id = $2
			  )
			ORDER BY ek.sort_order, e.updated_at DESC`
		entityArgs = []any{bookID, chapterFilter}
	} else {
		entitySQL = `
			SELECT e.entity_id, e.status, e.tags,
			       ek.code AS kind_code,
			       COALESCE((
			           SELECT eav.original_value FROM entity_attribute_values eav
			           JOIN attribute_definitions ad ON ad.attr_def_id = eav.attr_def_id
			           WHERE eav.entity_id = e.entity_id AND ad.code IN ('name','term')
			           ORDER BY ad.sort_order LIMIT 1
			       ), '') AS display_name
			FROM glossary_entities e
			JOIN entity_kinds ek ON ek.kind_id = e.kind_id
			WHERE e.book_id = $1 AND e.status = 'active'
			ORDER BY ek.sort_order, e.updated_at DESC`
		entityArgs = []any{bookID}
	}

	eRows, err := s.pool.Query(ctx, entitySQL, entityArgs...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer eRows.Close()

	entitiesByID := map[string]*ragEntityExport{}
	var entityOrder []string

	for eRows.Next() {
		var ent ragEntityExport
		if err := eRows.Scan(&ent.EntityID, &ent.Status, &ent.Tags, &ent.Kind, &ent.DisplayName); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return
		}
		if ent.Tags == nil {
			ent.Tags = []string{}
		}
		ent.ChapterLinks = []ragLinkExport{}
		ent.Attributes = []ragAttrExport{}
		entitiesByID[ent.EntityID] = &ent
		entityOrder = append(entityOrder, ent.EntityID)
	}
	if err := eRows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
		return
	}

	// Empty result shortcut
	if len(entityOrder) == 0 {
		var chapIDStr *string
		if chapterFilter != nil {
			s := chapterFilter.String()
			chapIDStr = &s
		}
		writeJSON(w, http.StatusOK, ragExportResp{
			BookID:      bookID.String(),
			ExportedAt:  time.Now().UTC(),
			ChapterID:   chapIDStr,
			EntityCount: 0,
			Entities:    []ragEntityExport{},
		})
		return
	}

	// ── Step 2: chapter links ─────────────────────────────────────────────────

	clRows, err := s.pool.Query(ctx, `
		SELECT entity_id, chapter_title, relevance, note
		FROM chapter_entity_links
		WHERE entity_id::text = ANY($1)`,
		entityOrder)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "links query failed")
		return
	}
	defer clRows.Close()

	for clRows.Next() {
		var entityIDStr string
		var link ragLinkExport
		if err := clRows.Scan(&entityIDStr, &link.ChapterTitle, &link.Relevance, &link.Note); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "link scan failed")
			return
		}
		if ent, ok := entitiesByID[entityIDStr]; ok {
			ent.ChapterLinks = append(ent.ChapterLinks, link)
		}
	}
	if err := clRows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "link rows error")
		return
	}

	// ── Step 3: attribute values ──────────────────────────────────────────────

	// Intermediate store: attrValueID → data; entity → ordered list of attrValueIDs
	type attrData struct {
		code             string
		name             string
		origLang         string
		origValue        string
		translations     []ragTransExport
		evidences        []ragEvidExport
	}
	attrByID := map[string]*attrData{}
	attrOrderByEntity := map[string][]string{} // entityID → []attrValueID

	avRows, err := s.pool.Query(ctx, `
		SELECT eav.attr_value_id, eav.entity_id, ad.code, ad.name,
		       eav.original_language, eav.original_value
		FROM entity_attribute_values eav
		JOIN attribute_definitions ad ON ad.attr_def_id = eav.attr_def_id
		WHERE eav.entity_id::text = ANY($1)
		ORDER BY eav.entity_id, ad.sort_order`,
		entityOrder)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "attrs query failed")
		return
	}
	defer avRows.Close()

	for avRows.Next() {
		var avID, entityID string
		a := &attrData{}
		if err := avRows.Scan(&avID, &entityID, &a.code, &a.name, &a.origLang, &a.origValue); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "attr scan failed")
			return
		}
		a.translations = []ragTransExport{}
		a.evidences = []ragEvidExport{}
		attrByID[avID] = a
		attrOrderByEntity[entityID] = append(attrOrderByEntity[entityID], avID)
	}
	if err := avRows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "attr rows error")
		return
	}

	// Collect all attr_value_ids for translation/evidence queries
	allAttrValueIDs := make([]string, 0, len(attrByID))
	for avID := range attrByID {
		allAttrValueIDs = append(allAttrValueIDs, avID)
	}

	// ── Step 4: translations ──────────────────────────────────────────────────

	if len(allAttrValueIDs) > 0 {
		trRows, err := s.pool.Query(ctx, `
			SELECT attr_value_id, language_code, value, confidence
			FROM attribute_translations
			WHERE attr_value_id::text = ANY($1)`,
			allAttrValueIDs)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "translations query failed")
			return
		}
		defer trRows.Close()

		for trRows.Next() {
			var avID, lang, value, conf string
			if err := trRows.Scan(&avID, &lang, &value, &conf); err != nil {
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "translation scan failed")
				return
			}
			if a, ok := attrByID[avID]; ok {
				a.translations = append(a.translations, ragTransExport{
					Language:   lang,
					Value:      value,
					Confidence: conf,
				})
			}
		}
		if err := trRows.Err(); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "translation rows error")
			return
		}
	}

	// ── Step 5: evidences ─────────────────────────────────────────────────────

	if len(allAttrValueIDs) > 0 {
		evRows, err := s.pool.Query(ctx, `
			SELECT attr_value_id, evidence_type, original_language, original_text,
			       chapter_title, block_or_line, note
			FROM evidences
			WHERE attr_value_id::text = ANY($1)`,
			allAttrValueIDs)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "evidences query failed")
			return
		}
		defer evRows.Close()

		for evRows.Next() {
			var avID, evType, origLang, origText string
			var chapTitle *string
			var blockOrLine string
			var note *string
			if err := evRows.Scan(&avID, &evType, &origLang, &origText, &chapTitle, &blockOrLine, &note); err != nil {
				writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "evidence scan failed")
				return
			}
			if a, ok := attrByID[avID]; ok {
				ev := ragEvidExport{
					Type:         evType,
					OriginalLang: origLang,
					Text:         origText,
					Chapter:      chapTitle,
					Note:         note,
				}
				if blockOrLine != "" {
					ev.Location = blockOrLine
				}
				a.evidences = append(a.evidences, ev)
			}
		}
		if err := evRows.Err(); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "evidence rows error")
			return
		}
	}

	// ── Assemble final response ───────────────────────────────────────────────

	result := make([]ragEntityExport, 0, len(entityOrder))
	for _, entityID := range entityOrder {
		ent := *entitiesByID[entityID]
		attrs := []ragAttrExport{}
		for _, avID := range attrOrderByEntity[entityID] {
			a := attrByID[avID]
			// Skip attributes with no content — keep export payload lean.
			if a.origValue == "" && len(a.translations) == 0 && len(a.evidences) == 0 {
				continue
			}
			attrs = append(attrs, ragAttrExport{
				Code:             a.code,
				Name:             a.name,
				OriginalLanguage: a.origLang,
				OriginalValue:    a.origValue,
				Translations:     a.translations,
				Evidences:        a.evidences,
			})
		}
		ent.Attributes = attrs
		result = append(result, ent)
	}

	var chapIDStr *string
	if chapterFilter != nil {
		s := chapterFilter.String()
		chapIDStr = &s
	}
	writeJSON(w, http.StatusOK, ragExportResp{
		BookID:      bookID.String(),
		ExportedAt:  time.Now().UTC(),
		ChapterID:   chapIDStr,
		EntityCount: len(result),
		Entities:    result,
	})
}
