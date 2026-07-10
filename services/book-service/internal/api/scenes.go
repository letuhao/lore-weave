package api

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

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

	// D-KG-SUMMARIES-LIVE-SMOKE — scan the Tiptap draft as jsonb→text, NOT
	// through ::bytea. `text::bytea` makes Postgres parse the JSON string as a
	// bytea ESCAPE literal, which errors ("invalid input syntax for type bytea")
	// on any body containing a backslash escape — a latent 500 that only
	// surfaced once legacy-chapter summaries began reading the draft as their
	// text fallback. `body::text` yields the raw JSON string directly.
	var body string
	err := s.pool.QueryRow(r.Context(), `
SELECT cd.body::text
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

	text := tiptapJSONToPlainText([]byte(body))
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
var _ = context.TODO // import-keepalive

// ─────────────────────────────────────────────────────────────────────────────
// 22-A2/A3 — public, read-only /v1 scene routes (the scene browser + rail).
//
// SC5 inverted authoring to composition-only, so `scenes` is a derived INDEX and
// every WRITE verb dropped its author (spec 22 API amendment): the three routes
// below are READ-only, VIEW-gated. Writes go to composition's outline_node.
//
//   GET /v1/books/{book_id}/scenes                         book-wide, keyset-paged
//   GET /v1/books/{book_id}/chapters/{chapter_id}/scenes   chapter-scoped (the rail)
//   GET /v1/books/{book_id}/scenes/{scene_id}              one scene
//
// Each row carries source_scene_id — the browser's join key onto composition's
// spec (scenes.source_scene_id → outline_node.id, SC2/SC7). `status` and
// `pov_entity_id` are SPEC fields living in composition; per SC11 the browser
// joins them client-side, so they are NOT server-side filters here (marked, not
// hidden — API amendment).
// ─────────────────────────────────────────────────────────────────────────────

// sceneSelectCols is the shared column list for every public scene read, so the
// list and single-get responses stay identical in shape.
const sceneSelectCols = `id, book_id, chapter_id, sort_order, title, path, leaf_text, content_hash, source_scene_id, parse_version, lifecycle_state, created_at, updated_at`

// scanSceneRow scans one scenes row (in sceneSelectCols order) into the public
// response map. source_scene_id renders as null when absent (the "not yet
// planned / anchor lost" states the inspector distinguishes — OQ-5).
func scanSceneRow(rows pgx.Rows) (map[string]any, error) {
	var id, chapterID uuid.UUID
	var bookID, sourceSceneID *uuid.UUID
	var title, path, leafText, contentHash, lifecycle string
	var sortOrder, parseVersion int
	var createdAt, updatedAt *time.Time
	if err := rows.Scan(&id, &bookID, &chapterID, &sortOrder, &title, &path, &leafText, &contentHash, &sourceSceneID, &parseVersion, &lifecycle, &createdAt, &updatedAt); err != nil {
		return nil, err
	}
	return map[string]any{
		"scene_id":        id,
		"book_id":         bookID,
		"chapter_id":      chapterID,
		"sort_order":      sortOrder,
		"title":           title,
		"path":            path,
		"leaf_text":       leafText,
		"content_hash":    contentHash,
		"source_scene_id": sourceSceneID,
		"parse_version":   parseVersion,
		"lifecycle_state": lifecycle,
		"created_at":      createdAt,
		"updated_at":      updatedAt,
	}, nil
}

// encodeSceneCursor / parseSceneCursor pack the keyset tuple (chapter_id,
// sort_order) — GLOBALLY unique per the scenes UNIQUE(chapter_id, sort_order)
// constraint, so it is a stable total order with no drift as scenes are added or
// removed mid-scroll. Opaque, URL-safe; only this service decodes it. A malformed
// token → ok=false (caller returns 400), never a silent reset to page 1.
func encodeSceneCursor(chapterID uuid.UUID, sortOrder int) string {
	return base64.RawURLEncoding.EncodeToString(fmt.Appendf(nil, "%s|%d", chapterID.String(), sortOrder))
}

func parseSceneCursor(s string) (chapterID uuid.UUID, sortOrder int, ok bool) {
	raw, err := base64.RawURLEncoding.DecodeString(s)
	if err != nil {
		return uuid.Nil, 0, false
	}
	parts := strings.SplitN(string(raw), "|", 2)
	if len(parts) != 2 {
		return uuid.Nil, 0, false
	}
	cid, err := uuid.Parse(parts[0])
	if err != nil {
		return uuid.Nil, 0, false
	}
	n, err := strconv.Atoi(parts[1])
	if err != nil {
		return uuid.Nil, 0, false
	}
	return cid, n, true
}

// getBookScenes handles GET /v1/books/{book_id}/scenes — the book-wide browser
// list, VIEW-gated + keyset-paged (10k+ scene books are real). Ordered by
// (chapter_id, sort_order) to ride idx_scenes_book_active. Server-side filters:
// chapter_id, source_scene_id (the go-to-prose join key — 28 AN-5b), q (a bounded
// ILIKE over title + leaf_text). Response: {items, next_cursor, total} — total on
// the first page only (like the chapter navigator), next_cursor null on the last.
func (s *Server) getBookScenes(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantView); !ok {
		return
	}

	// book_id is the direct scope (SC1); after 22-A5 every active scene carries it.
	args := []any{bookID}
	where := `book_id=$1 AND lifecycle_state='active'`
	if v := r.URL.Query().Get("chapter_id"); v != "" {
		cid, err := uuid.Parse(v)
		if err != nil {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid chapter_id")
			return
		}
		args = append(args, cid)
		where += fmt.Sprintf(" AND chapter_id=$%d", len(args))
	}
	if v := r.URL.Query().Get("source_scene_id"); v != "" {
		sid, err := uuid.Parse(v)
		if err != nil {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid source_scene_id")
			return
		}
		args = append(args, sid)
		where += fmt.Sprintf(" AND source_scene_id=$%d", len(args))
	}
	if q := strings.TrimSpace(r.URL.Query().Get("q")); q != "" {
		if len([]rune(q)) > maxSearchQueryRunes {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "query too long")
			return
		}
		args = append(args, escapeLikePattern(q))
		where += fmt.Sprintf(" AND (title ILIKE $%d OR leaf_text ILIKE $%d)", len(args), len(args))
	}

	limit, _ := parseLimitOffset(r)
	if r.URL.Query().Get("limit") == "" {
		limit = 100 // a keyset page defaults to a full page, not the list default of 20
	}

	cursor := r.URL.Query().Get("cursor")
	var total any
	if cursor == "" {
		var n int
		_ = s.pool.QueryRow(r.Context(), `SELECT COUNT(*) FROM scenes WHERE `+where, append([]any{}, args...)...).Scan(&n)
		total = n
	} else {
		curChapter, curSort, valid := parseSceneCursor(cursor)
		if !valid {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid cursor")
			return
		}
		// Strictly after (chapter_id, sort_order) — row-value comparison matching ORDER BY.
		args = append(args, curChapter, curSort)
		where += fmt.Sprintf(" AND (chapter_id, sort_order) > ($%d, $%d)", len(args)-1, len(args))
	}

	args = append(args, limit+1) // fetch one extra to detect a further page
	rows, err := s.pool.Query(r.Context(),
		`SELECT `+sceneSelectCols+` FROM scenes WHERE `+where+` ORDER BY chapter_id, sort_order LIMIT $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to list scenes")
		return
	}
	defer rows.Close()

	items := make([]map[string]any, 0, limit)
	for rows.Next() {
		item, err := scanSceneRow(rows)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to scan scene")
			return
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to read scenes")
		return
	}

	// The extra (limit+1)th row means a next page exists → drop it and emit the
	// cursor of the last KEPT item so the next request starts strictly after it.
	var nextCursor any
	if len(items) > limit {
		items = items[:limit]
		last := items[limit-1]
		nextCursor = encodeSceneCursor(last["chapter_id"].(uuid.UUID), last["sort_order"].(int))
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":       items,
		"next_cursor": nextCursor,
		"total":       total,
	})
}

// getChapterScenes handles GET /v1/books/{book_id}/chapters/{chapter_id}/scenes —
// the chapter-scoped rail, VIEW-gated. Distinct from the internal
// getInternalScenesByChapter (P2 orchestrator, X-Internal-Token): this is the
// public browser surface with the full scene shape incl. source_scene_id.
func (s *Server) getChapterScenes(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chapterID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantView); !ok {
		return
	}
	// Confirm the chapter belongs to this book (scope check; no cross-book leak).
	var exists bool
	if err := s.pool.QueryRow(r.Context(),
		`SELECT EXISTS(SELECT 1 FROM chapters WHERE id=$1 AND book_id=$2 AND lifecycle_state='active')`,
		chapterID, bookID).Scan(&exists); err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "lookup failed")
		return
	}
	if !exists {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found in book")
		return
	}

	rows, err := s.pool.Query(r.Context(),
		`SELECT `+sceneSelectCols+` FROM scenes WHERE chapter_id=$1 AND lifecycle_state='active' ORDER BY sort_order`, chapterID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to list scenes")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		item, err := scanSceneRow(rows)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to scan scene")
			return
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to read scenes")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":      items,
		"count":      len(items),
		"book_id":    bookID,
		"chapter_id": chapterID,
	})
}

// getBookScene handles GET /v1/books/{book_id}/scenes/{scene_id} — one scene,
// VIEW-gated, scoped to the book (a scene_id from another book 404s, no oracle).
// Includes source_scene_id — the browser's join key onto the spec.
func (s *Server) getBookScene(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	sceneID, ok := parseUUIDParam(w, r, "scene_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantView); !ok {
		return
	}
	rows, err := s.pool.Query(r.Context(),
		`SELECT `+sceneSelectCols+` FROM scenes WHERE id=$1 AND book_id=$2 AND lifecycle_state='active'`, sceneID, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to get scene")
		return
	}
	defer rows.Close()
	if !rows.Next() {
		writeError(w, http.StatusNotFound, "SCENE_NOT_FOUND", "scene not found in book")
		return
	}
	item, err := scanSceneRow(rows)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "failed to scan scene")
		return
	}
	writeJSON(w, http.StatusOK, item)
}
