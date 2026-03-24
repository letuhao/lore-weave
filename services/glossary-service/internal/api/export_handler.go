package api

import (
	"encoding/json"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
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

// ── Snapshot → RAG entity mapping ─────────────────────────────────────────────

// snapEntity is the intermediate struct that mirrors the entity_snapshot schema.
type snapEntity struct {
	EntityID string `json:"entity_id"`
	Kind     struct {
		Code string `json:"code"`
	} `json:"kind"`
	Status string   `json:"status"`
	Tags   []string `json:"tags"`
	Attributes []struct {
		Code             string `json:"code"`
		Name             string `json:"name"`
		OriginalLanguage string `json:"original_language"`
		OriginalValue    string `json:"original_value"`
		Translations     []struct {
			LanguageCode string `json:"language_code"`
			Value        string `json:"value"`
			Confidence   string `json:"confidence"`
		} `json:"translations"`
		Evidences []struct {
			EvidenceType     string  `json:"evidence_type"`
			OriginalLanguage string  `json:"original_language"`
			OriginalText     string  `json:"original_text"`
			ChapterTitle     *string `json:"chapter_title"`
			BlockOrLine      string  `json:"block_or_line"`
			Note             *string `json:"note"`
		} `json:"evidences"`
	} `json:"attributes"`
	ChapterLinks []struct {
		ChapterTitle *string `json:"chapter_title"`
		Relevance    string  `json:"relevance"`
		Note         *string `json:"note"`
	} `json:"chapter_links"`
}

// snapshotToRAGEntity maps a raw entity_snapshot JSONB value to the ragEntityExport
// shape used by the export endpoint. Mirrors the assembly logic of the old 5-query handler.
func snapshotToRAGEntity(raw []byte) (ragEntityExport, error) {
	var snap snapEntity
	if err := json.Unmarshal(raw, &snap); err != nil {
		return ragEntityExport{}, err
	}

	// Derive display_name: first non-empty value from 'name' or 'term' attribute.
	displayName := ""
	for _, a := range snap.Attributes {
		if (a.Code == "name" || a.Code == "term") && a.OriginalValue != "" {
			displayName = a.OriginalValue
			break
		}
	}

	// Map attributes; skip entries with no content (same rule as the old handler).
	attrs := []ragAttrExport{}
	for _, a := range snap.Attributes {
		if a.OriginalValue == "" && len(a.Translations) == 0 && len(a.Evidences) == 0 {
			continue
		}
		trans := make([]ragTransExport, len(a.Translations))
		for i, t := range a.Translations {
			trans[i] = ragTransExport{
				Language:   t.LanguageCode,
				Value:      t.Value,
				Confidence: t.Confidence,
			}
		}
		evids := make([]ragEvidExport, len(a.Evidences))
		for i, ev := range a.Evidences {
			e := ragEvidExport{
				Type:         ev.EvidenceType,
				OriginalLang: ev.OriginalLanguage,
				Text:         ev.OriginalText,
				Chapter:      ev.ChapterTitle,
				Note:         ev.Note,
			}
			if ev.BlockOrLine != "" {
				e.Location = ev.BlockOrLine
			}
			evids[i] = e
		}
		attrs = append(attrs, ragAttrExport{
			Code:             a.Code,
			Name:             a.Name,
			OriginalLanguage: a.OriginalLanguage,
			OriginalValue:    a.OriginalValue,
			Translations:     trans,
			Evidences:        evids,
		})
	}

	links := make([]ragLinkExport, len(snap.ChapterLinks))
	for i, cl := range snap.ChapterLinks {
		links[i] = ragLinkExport{
			ChapterTitle: cl.ChapterTitle,
			Relevance:    cl.Relevance,
			Note:         cl.Note,
		}
	}

	tags := snap.Tags
	if tags == nil {
		tags = []string{}
	}

	return ragEntityExport{
		EntityID:     snap.EntityID,
		Kind:         snap.Kind.Code,
		DisplayName:  displayName,
		Status:       snap.Status,
		Tags:         tags,
		ChapterLinks: links,
		Attributes:   attrs,
	}, nil
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

	var chapterFilter *uuid.UUID
	if cid := q.Get("chapter_id"); cid != "" {
		id, err := uuid.Parse(cid)
		if err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_ID", "invalid chapter_id")
			return
		}
		chapterFilter = &id
	}

	// Single query reads pre-assembled snapshots.
	// chapter_id filter uses the indexed chapter_entity_links table, not JSON path.
	const baseSQL = `
		SELECT entity_snapshot
		FROM glossary_entities
		WHERE book_id = $1
		  AND status  = 'active'
		  AND entity_snapshot IS NOT NULL`

	var rows pgx.Rows
	var err error

	if chapterFilter != nil {
		rows, err = s.pool.Query(ctx, baseSQL+`
		  AND EXISTS (
		      SELECT 1 FROM chapter_entity_links
		      WHERE entity_id = glossary_entities.entity_id
		        AND chapter_id = $2
		  )
		  ORDER BY entity_snapshot->'kind'->>'code',
		           updated_at DESC`,
			bookID, *chapterFilter)
	} else {
		rows, err = s.pool.Query(ctx, baseSQL+`
		  ORDER BY entity_snapshot->'kind'->>'code',
		           updated_at DESC`,
			bookID)
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer rows.Close()

	result := []ragEntityExport{}
	for rows.Next() {
		var snapshotBytes []byte
		if err := rows.Scan(&snapshotBytes); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return
		}
		ent, err := snapshotToRAGEntity(snapshotBytes)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "snapshot parse failed")
			return
		}
		result = append(result, ent)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
		return
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
