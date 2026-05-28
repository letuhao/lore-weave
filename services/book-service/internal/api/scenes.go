package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// scenes.go — P2 (hierarchical extraction T3) book-service side.
//
// Two NEW internal HTTP endpoints consumed by knowledge-service's P2
// leaf orchestrator:
//
//   GET /internal/books/{book_id}/chapters/{chapter_id}/scenes
//       -> list active scenes for the chapter (post-P1 decomposed)
//   GET /internal/books/{book_id}/chapters/{chapter_id}/draft-text
//       -> plain-text projection of chapter_drafts.body (Tiptap JSON)
//          used by the legacy-chapter fallback (P1 R-SELF-1 + P2 D8).
//
// Spec: docs/specs/2026-05-23-p2-parallel-map-checkpoint.md §D8 + §2 items 7-8.

type sceneRow struct {
	ID            string `json:"id"`
	SortOrder     int    `json:"sort_order"`
	Path          string `json:"path"`
	LeafText      string `json:"leaf_text"`
	ContentHash   string `json:"content_hash"`
	ParseVersion  int    `json:"parse_version"`
}

// getInternalScenesByChapter handles GET /internal/books/{book_id}/chapters/{chapter_id}/scenes.
//
// Returns active scenes for one chapter ordered by sort_order. Empty
// list when chapter has no scenes (legacy chapter — caller must use
// the draft-text fallback endpoint per spec D8).
func (s *Server) getInternalScenesByChapter(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chapterID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}

	// Verify chapter exists + belongs to the named book.
	var exists bool
	err := s.pool.QueryRow(r.Context(), `
SELECT EXISTS(SELECT 1 FROM chapters WHERE id=$1 AND book_id=$2 AND lifecycle_state='active')
`, chapterID, bookID).Scan(&exists)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "lookup failed")
		return
	}
	if !exists {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found in book")
		return
	}

	rows, err := s.pool.Query(r.Context(), `
SELECT id, sort_order, path, leaf_text, content_hash, parse_version
FROM scenes
WHERE chapter_id=$1 AND lifecycle_state='active'
ORDER BY sort_order
`, chapterID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "query failed")
		return
	}
	defer rows.Close()

	scenes := []sceneRow{}
	for rows.Next() {
		var s sceneRow
		var id uuid.UUID
		if err := rows.Scan(&id, &s.SortOrder, &s.Path, &s.LeafText, &s.ContentHash, &s.ParseVersion); err != nil {
			continue
		}
		s.ID = id.String()
		scenes = append(scenes, s)
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"chapter_id": chapterID,
		"book_id":    bookID,
		"scenes":     scenes,
		"count":      len(scenes),
	})
}

// getInternalChapterDraftText handles GET /internal/books/{book_id}/chapters/{chapter_id}/draft-text.
//
// Returns the plain-text projection of chapter_drafts.body (Tiptap JSON).
// Used by P2's legacy-chapter fallback: chapters without parts/scenes
// (NULL structural_path, predates P1) get one virtual scene whose
// leaf_text is this projection.
func (s *Server) getInternalChapterDraftText(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chapterID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}

	var body []byte
	err := s.pool.QueryRow(r.Context(), `
SELECT cd.body::text::bytea
FROM chapter_drafts cd
JOIN chapters c ON c.id = cd.chapter_id
WHERE cd.chapter_id=$1 AND c.book_id=$2 AND c.lifecycle_state='active'
`, chapterID, bookID).Scan(&body)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter or draft not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "query failed")
		return
	}

	text := tiptapJSONToPlainText(body)
	writeJSON(w, http.StatusOK, map[string]any{
		"chapter_id": chapterID,
		"book_id":    bookID,
		"text":       text,
		"length":     len(text),
	})
}

// tiptapJSONToPlainText walks a Tiptap doc JSON and concatenates the
// `text` properties depth-first. Block nodes (paragraph, heading) get
// their text joined by "\n\n"; inline nodes' text concatenated.
//
// Mirrors the algorithm of sdks/python/loreweave_parse/_text_strip.py
// html_to_leaf_text — kept here as a pure helper rather than a cross-
// service call.
func tiptapJSONToPlainText(body []byte) string {
	var doc map[string]any
	if err := json.Unmarshal(body, &doc); err != nil {
		return ""
	}
	content, _ := doc["content"].([]any)
	var paragraphs []string
	for _, node := range content {
		nm, _ := node.(map[string]any)
		if nm == nil {
			continue
		}
		paragraph := walkInlineText(nm)
		paragraph = strings.TrimSpace(paragraph)
		if paragraph != "" {
			paragraphs = append(paragraphs, paragraph)
		}
	}
	return strings.Join(paragraphs, "\n\n")
}

// walkInlineText collects text from a Tiptap node's content tree.
func walkInlineText(node map[string]any) string {
	if text, ok := node["text"].(string); ok {
		return text
	}
	content, ok := node["content"].([]any)
	if !ok {
		return ""
	}
	var sb strings.Builder
	for _, child := range content {
		cm, _ := child.(map[string]any)
		if cm == nil {
			continue
		}
		// "hardBreak" node -> newline within paragraph
		if t, _ := cm["type"].(string); t == "hardBreak" {
			sb.WriteString("\n")
			continue
		}
		sb.WriteString(walkInlineText(cm))
	}
	return sb.String()
}

// Wire into server.go via parseUUIDParam helper.
var _ = context.TODO  // import-keepalive
