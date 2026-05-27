package api

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
)

// parse.go — P1 (hierarchical extraction T1) book-service side.
//
// Two pieces:
//   1. parseClientCall — thin HTTP client to knowledge-service /internal/parse
//      (mirrors worker-infra/internal/tasks/parse_client.go but kept local
//      to avoid an import cycle between book-service and worker-infra).
//   2. processTxtImport — synchronous orchestrator for the .txt branch of
//      startImport: POST /internal/parse + write parts/chapters/scenes
//      + chapter_raw_objects (preserves the legacy "includeRaw=true" for .txt).
//
// Spec: docs/specs/2026-05-23-p1-structural-decomposer.md §D3/§D7.

// parsedScene / parsedChapter / parsedPart / parsedTree mirror loreweave_parse.
type parsedScene struct {
	SortOrder   int    `json:"sort_order"`
	Path        string `json:"path"`
	LeafText    string `json:"leaf_text"`
	ContentHash string `json:"content_hash"`
}

type parsedChapter struct {
	SortOrder int             `json:"sort_order"`
	Title     *string         `json:"title"`
	Path      string          `json:"path"`
	HTML      string          `json:"html"`
	Scenes    []parsedScene   `json:"scenes"`
}

type parsedPart struct {
	SortOrder int             `json:"sort_order"`
	Title     *string         `json:"title"`
	Path      string          `json:"path"`
	Chapters  []parsedChapter `json:"chapters"`
}

type parsedTree struct {
	SourceFormat     string       `json:"source_format"`
	DetectedLanguage *string      `json:"detected_language"`
	WalkerPath       string       `json:"walker_path"`
	BookTitle        *string      `json:"book_title"`
	Parts            []parsedPart `json:"parts"`
}

type parseReq struct {
	SourceFormat string  `json:"source_format"`
	Content      string  `json:"content"`
	Language     *string `json:"language,omitempty"`
	Filename     *string `json:"filename,omitempty"`
}

// parseClientCall issues a single POST /internal/parse. IQ4: no retry —
// /internal/parse is deterministic.
func (s *Server) parseClientCall(
	ctx context.Context,
	sourceFormat string,
	content string,
	language string,
	filename string,
) (*parsedTree, error) {
	body := parseReq{SourceFormat: sourceFormat, Content: content}
	if language != "" {
		body.Language = &language
	}
	if filename != "" {
		body.Filename = &filename
	}
	jsonBody, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("marshal: %w", err)
	}
	req, err := http.NewRequestWithContext(
		ctx, "POST", s.cfg.KnowledgeServiceURL+"/internal/parse",
		bytes.NewReader(jsonBody),
	)
	if err != nil {
		return nil, fmt.Errorf("request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("do: %w", err)
	}
	defer resp.Body.Close()

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("status %d: %s", resp.StatusCode, string(respBytes))
	}
	var tree parsedTree
	if err := json.Unmarshal(respBytes, &tree); err != nil {
		return nil, fmt.Errorf("unmarshal: %w", err)
	}
	return &tree, nil
}

// processTxtImport handles the .txt branch of startImport (H1 fix in spec D3):
// 1. Call /internal/parse with source_format=plain.
// 2. For each part: insert one parts row in its own short Tx.
// 3. For each chapter: per-chapter Tx with chapters + drafts + revision + scenes
//    + chapter_raw_objects (.txt preserves the legacy includeRaw=true behaviour).
//
// On parse failure -> 502 BOOK_PARSE_UPSTREAM_FAILURE. Returns total chapters
// created via the response body (matches startImport's UX).
func (s *Server) processTxtImport(
	w http.ResponseWriter,
	r *http.Request,
	ownerID uuid.UUID,
	bookID uuid.UUID,
	originalFilename string,
	body string,
	lang string,
) {
	tree, err := s.parseClientCall(r.Context(), "plain", body, lang, originalFilename)
	if err != nil {
		writeError(w, http.StatusBadGateway, "BOOK_PARSE_UPSTREAM_FAILURE",
			fmt.Sprintf("parse: %v", err))
		return
	}

	// Find current max sort_order ONCE — book-global counter across parts.
	var maxSort int
	_ = s.pool.QueryRow(r.Context(),
		`SELECT COALESCE(MAX(sort_order),0) FROM chapters WHERE book_id=$1 AND lifecycle_state='active'`,
		bookID).Scan(&maxSort)
	chapterGlobalSort := maxSort + 1
	multiPart := len(tree.Parts) > 1

	// Quota check ONCE for the whole import body (cheaper than per-chapter).
	_ = s.ensureQuotaRow(r.Context(), ownerID)
	_ = s.recalcQuota(r.Context(), ownerID)
	var used, quota int64
	_ = s.pool.QueryRow(r.Context(),
		`SELECT used_bytes, quota_bytes FROM user_storage_quota WHERE owner_user_id=$1`,
		ownerID).Scan(&used, &quota)
	if used+int64(len(body)) > quota {
		writeError(w, http.StatusInsufficientStorage, "STORAGE_QUOTA_EXCEEDED", "quota exceeded")
		return
	}

	totalCount := 0
	var lastChapterID uuid.UUID

	for partIdx, part := range tree.Parts {
		// (a) Per-part Tx: one parts row.
		var titleArg any
		if part.Title != nil && strings.TrimSpace(*part.Title) != "" {
			titleArg = *part.Title
		}
		var partID uuid.UUID
		err := s.pool.QueryRow(r.Context(), `
INSERT INTO parts(book_id, sort_order, title, path)
VALUES($1, $2, $3, $4)
ON CONFLICT (book_id, sort_order) DO UPDATE SET title = EXCLUDED.title, path = EXCLUDED.path, updated_at = now()
RETURNING id
`, bookID, partIdx+1, titleArg, part.Path).Scan(&partID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT",
				fmt.Sprintf("insert part: %v", err))
			return
		}

		for chIdxInPart, ch := range part.Chapters {
			// Per-chapter body = concatenation of scene leaf_texts (joined by \n\n).
			// For plain-text imports, ch.HTML is "" (D8 — plain has no html slice).
			leaves := make([]string, 0, len(ch.Scenes))
			for _, sc := range ch.Scenes {
				leaves = append(leaves, sc.LeafText)
			}
			chapterBody := strings.Join(leaves, "\n\n")
			jsonBody := plainTextToTiptapJSON(chapterBody)

			// L3 — multi-part filename pattern. C3 fix: storage_key uniqueness
			// comes from uuid.New() alone; the per-part/per-chapter suffix in
			// the prior draft was redundant. Filename still encodes part+chapter
			// for human-readable UI listing.
			var chFilename string
			storageKey := fmt.Sprintf("chapters/%s/%s", bookID, uuid.New().String())
			if multiPart {
				chFilename = fmt.Sprintf("%s-pt%02d-ch%03d.txt",
					strings.TrimSuffix(originalFilename, ".txt"),
					partIdx+1, chIdxInPart+1)
			} else {
				chFilename = originalFilename
			}

			chapterTitle := ""
			if ch.Title != nil {
				chapterTitle = *ch.Title
			}

			tx, err := s.pool.Begin(r.Context())
			if err != nil {
				writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT",
					fmt.Sprintf("db begin: %v", err))
				return
			}

			var chapterID uuid.UUID
			err = tx.QueryRow(r.Context(), `
INSERT INTO chapters(book_id, title, original_filename, original_language, content_type, byte_size, sort_order, storage_key, lifecycle_state, draft_updated_at, updated_at, part_id, structural_path)
VALUES($1, $2, $3, $4, 'text/plain', $5, $6, $7, 'active', now(), now(), $8, $9)
RETURNING id
`, bookID, nullIfEmpty(chapterTitle), chFilename, lang,
				int64(len(chapterBody)), chapterGlobalSort, storageKey,
				partID, ch.Path,
			).Scan(&chapterID)
			if err != nil {
				tx.Rollback(r.Context())
				writeError(w, http.StatusConflict, "BOOK_CONFLICT",
					fmt.Sprintf("insert chapter: %v", err))
				return
			}

			// Preserve legacy includeRaw=true behaviour for .txt imports.
			// M2 (review round 2) semantic note: chapter_raw_objects.body_text
			// is now the PER-CHAPTER joined leaf_text (markers + scene-breaks
			// stripped), NOT the full original .txt body. Reader of this column
			// is GET /v1/books/{id}/chapters/{id}/raw — see book-service/internal
			// /api/server.go:1343. Pre-P1 readers expecting markers will see
			// stripped content; chapter_drafts.body remains the canonical edit
			// source. Tracked: D-P1-CHAPTER-RAW-AUDIT.
			_, _ = tx.Exec(r.Context(),
				`INSERT INTO chapter_raw_objects(chapter_id, body_text) VALUES($1,$2)`,
				chapterID, chapterBody)
			_, _ = tx.Exec(r.Context(),
				`INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_updated_at, draft_version) VALUES($1,$2,'json',now(),1)`,
				chapterID, jsonBody)
			_, _ = tx.Exec(r.Context(),
				`INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id) VALUES($1,$2,$3,$4,$5)`,
				chapterID, jsonBody, "json", "imported from "+originalFilename, ownerID)
			_, _ = tx.Exec(r.Context(),
				`UPDATE chapters SET draft_revision_count=1 WHERE id=$1`, chapterID)

			for _, sc := range ch.Scenes {
				_, err := tx.Exec(r.Context(),
					`INSERT INTO scenes(chapter_id, sort_order, path, leaf_text, content_hash, parse_version) VALUES($1, $2, $3, $4, $5, 1)`,
					chapterID, sc.SortOrder, sc.Path, sc.LeafText, sc.ContentHash)
				if err != nil {
					tx.Rollback(r.Context())
					writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT",
						fmt.Sprintf("insert scene: %v", err))
					return
				}
			}

			if err := insertOutboxEvent(r.Context(), tx, "chapter.created", chapterID,
				map[string]any{"book_id": bookID}); err != nil {
				tx.Rollback(r.Context())
				writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT",
					"failed to commit chapter")
				return
			}
			if err := tx.Commit(r.Context()); err != nil {
				writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT",
					fmt.Sprintf("commit chapter: %v", err))
				return
			}
			totalCount++
			chapterGlobalSort++
			lastChapterID = chapterID
		}
	}

	_ = s.recalcQuota(r.Context(), ownerID)

	// Match existing UX: respond with the (last) created chapter (or summary).
	if totalCount == 1 {
		s.getChapterByID(w, r.Context(), bookID, lastChapterID, ownerID, http.StatusCreated)
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"chapters_created": totalCount,
		"book_id":          bookID,
	})
}

// sceneContentHashFromBytes — exposed helper for tests that need to
// construct content_hash values matching the SDK.
func sceneContentHashFromBytes(b []byte) string {
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}
