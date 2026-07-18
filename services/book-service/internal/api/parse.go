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
	// SourceSceneID (22-A5/SC7) — the composition outline_node.id the parser
	// recovered from the drafted prose's `data-scene-id` heading anchor, when
	// present. Fresh imports (plain text / pandoc HTML) carry no anchor, so it is
	// absent → the index row's source_scene_id stays NULL ("not yet planned"),
	// exactly the SC7 degrade. A soft ref (no FK): it crosses the service/DB
	// boundary to composition.
	SourceSceneID *string `json:"source_scene_id,omitempty"`
	// AnchorSceneID (26 IX-5/IX-6) — the opening heading's `data-scene-id`
	// carried through by the tiptap walker on a re-parse (source_format='tiptap').
	// /internal/parse serializes the SDK `Scene.anchor_scene_id` field under THIS
	// name (the import formats plain/html never populate it, so the older
	// source_scene_id tag above stayed nil regardless). Evidence rule 1 in
	// reparse.go reads it to set scenes.source_scene_id.
	AnchorSceneID *string `json:"anchor_scene_id,omitempty"`
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
// processTxtImport — E0-2: `caller` is the importing editor (revision author);
// `owner` is the book owner whose storage quota the imported content bills.
func (s *Server) processTxtImport(
	w http.ResponseWriter,
	r *http.Request,
	caller uuid.UUID,
	owner uuid.UUID,
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
	// Content bills the book owner, not the importing editor.
	_ = s.ensureQuotaRow(r.Context(), owner)
	_ = s.recalcQuota(r.Context(), owner)
	var used, quota int64
	_ = s.pool.QueryRow(r.Context(),
		`SELECT used_bytes, quota_bytes FROM user_storage_quota WHERE owner_user_id=$1`,
		owner).Scan(&used, &quota)
	if used+int64(len(body)) > quota {
		writeError(w, http.StatusInsufficientStorage, "STORAGE_QUOTA_EXCEEDED", "quota exceeded")
		return
	}

	totalCount := 0
	var lastChapterID uuid.UUID

	// C-merge C4 — the import no longer creates book-service parts (parts moved to composition,
	// structure_node kind='part'). Chapters import FLAT (structure_node_id NULL); part grouping is a
	// post-import authoring act in the Studio (composition). The source's part boundaries still drive
	// the per-chapter filename + the global sort order below.
	for partIdx, part := range tree.Parts {
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
			// C-merge C4 — flat import: no part_id/structure_node_id (parts are a composition authoring
			// act now). structural_path keeps the source path for reference.
			err = tx.QueryRow(r.Context(), `
INSERT INTO chapters(book_id, title, original_filename, original_language, content_type, byte_size, sort_order, storage_key, lifecycle_state, draft_updated_at, updated_at, structural_path)
VALUES($1, $2, $3, $4, 'text/plain', $5, $6, $7, 'active', now(), now(), $8)
RETURNING id
`, bookID, nullIfEmpty(chapterTitle), chFilename, lang,
				int64(len(chapterBody)), chapterGlobalSort, storageKey,
				ch.Path,
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
			// Canon Model CM1: capture the import revision id (error-checked,
			// NOT fire-and-forget) so the chapter can be pinned as published.
			var importRevID uuid.UUID
			if err := tx.QueryRow(r.Context(),
				`INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id) VALUES($1,$2,$3,$4,$5) RETURNING id`,
				chapterID, jsonBody, "json", "imported from "+originalFilename, caller).Scan(&importRevID); err != nil {
				tx.Rollback(r.Context())
				writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT",
					fmt.Sprintf("insert revision: %v", err))
				return
			}
			// Imported content is finished canon → publish it and pin the import
			// revision (else CM3c has nothing to pin → imported canon never extracted).
			// Error-checked (NOT fire-and-forget): this UPDATE is what actually pins
			// the revision + flips to published — swallowing its error would commit an
			// orphan revision with the chapter stuck at 'draft' (adversary review-code W1).
			// 26 IX-1/IX-3: the just-inserted scenes ARE the parse of importRevID,
			// so mark the index fresh (last_parsed_revision_id=importRevID) at birth
			// — an imported chapter is born published AND fresh by the sweeper's own
			// `last_parsed_revision_id IS DISTINCT FROM published_revision_id`
			// predicate, so it is never needlessly re-swept.
			if _, err := tx.Exec(r.Context(),
				// WS-0.3: a freshly-imported chapter is never kg_exclude'd (column defaults
				// false), so the pointer is set unconditionally here.
				`UPDATE chapters SET draft_revision_count=1, editorial_status='published', published_revision_id=$2, kg_indexed_revision_id=$2, last_parsed_revision_id=$2 WHERE id=$1`,
				chapterID, importRevID); err != nil {
				tx.Rollback(r.Context())
				writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT",
					fmt.Sprintf("publish imported chapter: %v", err))
				return
			}

			// SC11-amendment Phase 0: did THIS import actually recover any spec back-link?
			// A link-less import (the common case — the parser only recovers an anchor from
			// an already-exported `data-scene-id`) must NOT fire a link event: the mirror has
			// nothing to reconcile, and a no-op event is noise the relay pays for. The IX-12
			// decompile write-back is what links a plain import, and it emits its own.
			anyLinked := false

			for _, sc := range ch.Scenes {
				// 22-A5: set book_id (the chapter's book — the SC1 direct scope) AND
				// source_scene_id (the SC7 `data-scene-id` anchor back-link, when the
				// parser recovered one) at INSERT, closing the A1 write-path gap.
				//
				// Resolve ONCE: `sceneSourceSceneIDArg` parses, and it is the same value that
				// decides both the bind and whether this import linked anything at all.
				ssid := sceneSourceSceneIDArg(sc.SourceSceneID)
				_, err := tx.Exec(r.Context(),
					`INSERT INTO scenes(chapter_id, book_id, sort_order, path, leaf_text, content_hash, source_scene_id, parse_version) VALUES($1, $2, $3, $4, $5, $6, $7, 1)`,
					chapterID, bookID, sc.SortOrder, sc.Path, sc.LeafText, sc.ContentHash, ssid)
				if err != nil {
					tx.Rollback(r.Context())
					writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT",
						fmt.Sprintf("insert scene: %v", err))
					return
				}
				if ssid != nil {
					anyLinked = true
				}
			}

			if err := insertOutboxEvent(r.Context(), tx, "chapter.created", chapterID,
				map[string]any{"book_id": bookID}); err != nil {
				tx.Rollback(r.Context())
				writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT",
					"failed to commit chapter")
				return
			}
			// In the SAME tx as the INSERTs above (INV-O12): if the emit cannot be written the
			// links must not exist either, or composition's mirror never learns of them.
			if anyLinked {
				if err := emitScenesLinked(r.Context(), tx, bookID, chapterID); err != nil {
					tx.Rollback(r.Context())
					writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT",
						"failed to commit chapter")
					return
				}
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

	_ = s.recalcQuota(r.Context(), owner)

	// Match existing UX: respond with the (last) created chapter (or summary).
	if totalCount == 1 {
		s.getChapterByID(w, r.Context(), bookID, lastChapterID, caller, http.StatusCreated)
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

// sceneSourceSceneIDArg maps the parser's optional `data-scene-id` anchor (SC7)
// to the scenes.source_scene_id INSERT bind: a valid UUID → that UUID, absent or
// malformed → NULL. A malformed anchor is deliberately NOT an error — the scene
// still gets its index row with a NULL back-link, which the inspector surfaces as
// "anchor lost" (the F6 ⚓ re-anchor path), never a silent drop of the whole scene.
func sceneSourceSceneIDArg(raw *string) any {
	if raw == nil {
		return nil
	}
	id, err := uuid.Parse(strings.TrimSpace(*raw))
	if err != nil {
		return nil
	}
	return id
}
