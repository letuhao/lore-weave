package tasks

// import_processor_pdf.go — PDF book import per-chunk pipeline
// (docs/specs/2026-07-06-pdf-book-import.md L6).
//
// Unlike processImport (pandoc + one whole-book /internal/parse call),
// this loops page-range chunks itself, calling knowledge-service's
// /internal/parse/pdf-chunk ONCE PER CHUNK — bounding each HTTP call's
// duration/payload to one chunk's worth of images (spec §6.1/§6.5/§6.8)
// and bounding a worker crash's blast radius to the single in-flight
// chunk (§6.7, paired with the chapters.import_job_id idempotency
// constraint added in book-service's migration).

import (
	"bytes"
	"context"
	"encoding/base64"
	"fmt"
	"html"
	"io"
	"log/slog"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/minio/minio-go/v7"
)

// processPdfImport handles the pdf branch of import.requested. Returns
// the FINAL chapter count for this job (re-queried from the DB at the
// end, not accumulated — see the ON CONFLICT DO NOTHING handling below,
// which makes an accumulated counter wrong under outbox redelivery).
func (t *ImportProcessor) processPdfImport(ctx context.Context, payload importRequestedPayload) (int, error) {
	// 1. Download the PDF from MinIO (same pattern as processImport).
	obj, err := t.Minio.GetObject(ctx, t.Cfg.MinioBucket, payload.FileStorageKey, minio.GetObjectOptions{})
	if err != nil {
		return 0, fmt.Errorf("minio get: %w", err)
	}
	defer obj.Close()
	pdfBytes, err := io.ReadAll(obj)
	if err != nil {
		return 0, fmt.Errorf("minio read: %w", err)
	}

	// 2. Defensive re-check (spec §6.2) — book-service's pdf-peek endpoint
	// should have already rejected an encrypted/corrupted PDF before this
	// job was ever queued, but re-verify here too (the same page count is
	// also what drives the chunk loop below).
	pageCount, err := t.parseClient.PdfPeek(ctx, pdfBytes)
	if err != nil {
		return 0, fmt.Errorf("pdf peek: %w", err)
	}
	if pageCount < 1 {
		return 0, fmt.Errorf("pdf has no pages")
	}
	pagesPerChunk := payload.PagesPerChunk
	if pagesPerChunk < 1 {
		pagesPerChunk = 1 // defensive floor — book-service already validates >=1
	}

	lang := payload.OriginalLanguage
	if lang == "" {
		lang = "auto"
	}

	// 3. One synthetic Part for the whole PDF import, using the same
	// "next available sort_order" pattern as chapterGlobalSort below —
	// NOT a hardcoded sort_order=1, which would collide with
	// insertPart's ON CONFLICT (book_id, sort_order) DO UPDATE and
	// silently overwrite an existing part from a prior docx/txt import
	// (spec §6.11).
	var maxPartSort int
	_ = t.BookDB.QueryRow(ctx,
		`SELECT COALESCE(MAX(sort_order),0) FROM parts WHERE book_id=$1`,
		payload.BookID).Scan(&maxPartSort)
	partSortOrder := maxPartSort + 1
	partID, err := t.insertPart(ctx, payload.BookID, partSortOrder,
		nil, fmt.Sprintf("book/part-%d", partSortOrder))
	if err != nil {
		return 0, fmt.Errorf("insert part: %w", err)
	}

	// 4. Book-global chapter sort_order counter (same pattern as processImport).
	var maxSort int
	_ = t.BookDB.QueryRow(ctx,
		`SELECT COALESCE(MAX(sort_order),0) FROM chapters WHERE book_id=$1 AND lifecycle_state='active'`,
		payload.BookID).Scan(&maxSort)
	chapterGlobalSort := maxSort + 1

	numChunks := (pageCount + pagesPerChunk - 1) / pagesPerChunk
	for chunkIdx := 0; chunkIdx < numChunks; chunkIdx++ {
		pageStart := chunkIdx*pagesPerChunk + 1
		pageEnd := (chunkIdx + 1) * pagesPerChunk
		if pageEnd > pageCount {
			pageEnd = pageCount
		}

		result, err := t.parseClient.CallPdfChunk(ctx, PdfChunkParams{
			BookID:        payload.BookID,
			PdfBytes:      pdfBytes,
			PageStart:     pageStart,
			PageEnd:       pageEnd,
			ChunkIndex:    chunkIdx,
			CaptionImages: payload.CaptionImages,
			Language:      lang,
			UserID:        payload.UserID,
			ModelSource:   payload.VisionModelSource,
			ModelRef:      payload.VisionModelRef,
		})
		if err != nil {
			// A chunk-call failure means the parse/LLM infra itself is
			// down for this chunk's TEXT extraction — unlike a per-image
			// caption failure (handled as non-fatal INSIDE the endpoint),
			// this is fatal for the whole job. The already-committed
			// chunks before this one stay committed (per-chunk Tx below).
			return t.countPdfChapters(ctx, payload.JobID), fmt.Errorf("parse chunk %d: %w", chunkIdx, err)
		}

		ch := result.Chapter
		chapterTitle := ""
		if ch.Title != nil {
			chapterTitle = *ch.Title
		}
		leafText := ""
		if len(ch.Scenes) > 0 {
			leafText = ch.Scenes[0].LeafText
		}
		tiptapJSON := htmlToTiptapJSON(plainTextToHTML(leafText))

		storageKey := fmt.Sprintf("chapters/%s/import-%s-pdf-chunk-%d", payload.BookID, payload.JobID, chunkIdx)

		tx, err := t.BookDB.Begin(ctx)
		if err != nil {
			return t.countPdfChapters(ctx, payload.JobID), fmt.Errorf("db begin: %w", err)
		}

		var chapterID string
		err = tx.QueryRow(ctx, `
INSERT INTO chapters(book_id, title, original_filename, original_language, content_type, byte_size, sort_order, storage_key, lifecycle_state, draft_updated_at, updated_at, part_id, structural_path, import_job_id)
VALUES($1, $2, $3, $4, 'application/json', $5, $6, $7, 'active', now(), now(), $8, $9, $10)
ON CONFLICT (book_id, import_job_id, structural_path) WHERE import_job_id IS NOT NULL DO NOTHING
RETURNING id
`, payload.BookID, nullIfEmpty(chapterTitle),
			fmt.Sprintf("import-pdf-chunk-%03d.pdf", chunkIdx), lang,
			len(tiptapJSON), chapterGlobalSort, storageKey,
			partID, ch.Path, payload.JobID,
		).Scan(&chapterID)
		if err != nil {
			tx.Rollback(ctx)
			if err == pgx.ErrNoRows {
				// L9 idempotency — this chunk was already committed by an
				// earlier (crashed/redelivered) attempt at this same job.
				// Skip its scenes/images too (re-inserting those for an
				// already-existing chapter would create orphan duplicates
				// even though the chapter insert itself was a no-op).
				slog.Info("import-processor(pdf): chunk already processed, skipping",
					"job_id", payload.JobID, "chunk_index", chunkIdx)
				chapterGlobalSort++
				continue
			}
			return t.countPdfChapters(ctx, payload.JobID), fmt.Errorf("insert chapter: %w", err)
		}

		_, _ = tx.Exec(ctx,
			`INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_updated_at, draft_version) VALUES($1, $2, 'json', now(), 1)`,
			chapterID, tiptapJSON)
		// 26 IX-1 corollary: the PDF worker importer gains the sync .txt path's
		// auto-publish so every import path births index rows that parse the pinned
		// PUBLISHED revision (F1). Capture the import revision id (error-checked) and
		// mark the index fresh (last_parsed_revision_id=importRevID) — the scenes
		// inserted below ARE that revision's parse, so the chapter is born
		// published+fresh and is never needlessly re-swept.
		var importRevID string
		if err := tx.QueryRow(ctx,
			`INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id) VALUES($1, $2, 'json', $3, $4) RETURNING id`,
			chapterID, tiptapJSON, fmt.Sprintf("imported from PDF (pages %d-%d)", pageStart, pageEnd), payload.UserID).Scan(&importRevID); err != nil {
			tx.Rollback(ctx)
			return t.countPdfChapters(ctx, payload.JobID), fmt.Errorf("insert revision: %w", err)
		}
		if _, err := tx.Exec(ctx,
			// WS-0.3 (spec §3.2): same as import_processor.go — worker-infra writes
			// book-service's chapters table directly and must set the KG pointer, else
			// PDF-imported books never reach the knowledge graph.
			`UPDATE chapters SET draft_revision_count=1, editorial_status='published', published_revision_id=$2, kg_indexed_revision_id=$2, last_parsed_revision_id=$2 WHERE id=$1`,
			chapterID, importRevID); err != nil {
			tx.Rollback(ctx)
			return t.countPdfChapters(ctx, payload.JobID), fmt.Errorf("publish imported chapter: %w", err)
		}

		anyLinked := false
		for _, sc := range ch.Scenes {
			// 22-A5: set book_id (SC1) AND source_scene_id (SC7 anchor, when present)
			// at INSERT — closes the A1 window for the PDF import branch too.
			ssid := sceneSourceSceneIDArg(sc.SourceSceneID)
			if _, err := tx.Exec(ctx,
				`INSERT INTO scenes(chapter_id, book_id, sort_order, path, leaf_text, content_hash, source_scene_id, parse_version) VALUES($1, $2, $3, $4, $5, $6, $7, 1)`,
				chapterID, payload.BookID, sc.SortOrder, sc.Path, sc.LeafText, sc.ContentHash, ssid,
			); err != nil {
				tx.Rollback(ctx)
				return t.countPdfChapters(ctx, payload.JobID), fmt.Errorf("insert scene: %w", err)
			}
			if ssid != nil {
				anyLinked = true
			}
		}

		// SC11-amendment Phase 0 — WRITER #4. Same reason as the HTML/txt path: a scene born with an
		// anchor is never touched by the IX-12 write-back (it only fills NULLs), so without this the
		// link exists and nothing announces it. Same tx as the INSERTs (INV-O12).
		if anyLinked {
			if err := emitScenesLinkedTx(ctx, tx, payload.BookID, chapterID); err != nil {
				tx.Rollback(ctx)
				return t.countPdfChapters(ctx, payload.JobID), fmt.Errorf("emit scenes_linked: %w", err)
			}
		}

		for imgIdx, img := range result.Images {
			imgData, decErr := base64.StdEncoding.DecodeString(img.ImageBytesB64)
			if decErr != nil {
				slog.Warn("import-processor(pdf): bad image base64 — skipping image", "chunk_index", chunkIdx, "img_index", imgIdx)
				continue
			}
			imgStorageKey, upErr := t.uploadPdfImage(ctx, payload.BookID, payload.JobID, chunkIdx, imgIdx, imgData, img.Ext)
			if upErr != nil {
				slog.Warn("import-processor(pdf): image upload failed — skipping image",
					"chunk_index", chunkIdx, "img_index", imgIdx, "error", upErr)
				continue
			}
			if _, err := tx.Exec(ctx,
				`INSERT INTO chapter_page_images(chapter_id, page_number, storage_key, caption, model_ref) VALUES($1, $2, $3, $4, $5)`,
				chapterID, img.PageNumber, imgStorageKey, img.Caption, img.ModelRef,
			); err != nil {
				slog.Warn("import-processor(pdf): chapter_page_images insert failed", "error", err)
			}
		}

		if err := tx.Commit(ctx); err != nil {
			return t.countPdfChapters(ctx, payload.JobID), fmt.Errorf("commit chapter: %w", err)
		}
		chapterGlobalSort++

		// Incremental progress (spec §4.6) — the FE progress step polls/
		// listens for this instead of one opaque "processing" state.
		t.publishWSEvent(ctx, payload.UserID, payload.JobID, "processing", chunkIdx+1, nil)
	}

	// 4.5 — 26 IX-12 decompile write-back (mirrors processImport step 5.5). Best-effort.
	t.writeBackSceneLinks(ctx, payload.BookID, payload.UserID)

	// 5. Clean up the source PDF from MinIO (mirrors processImport step 6).
	_ = t.Minio.RemoveObject(ctx, t.Cfg.MinioBucket, payload.FileStorageKey, minio.RemoveObjectOptions{})

	return t.countPdfChapters(ctx, payload.JobID), nil
}

// countPdfChapters re-queries the real chapter count for this import job —
// used instead of an accumulated counter because ON CONFLICT DO NOTHING
// (the L9 idempotency guard) can skip chunks on a redelivered run, which
// would make an accumulated count wrong (spec §6.7).
func (t *ImportProcessor) countPdfChapters(ctx context.Context, jobID string) int {
	var count int
	_ = t.BookDB.QueryRow(ctx, `SELECT COUNT(*) FROM chapters WHERE import_job_id=$1`, jobID).Scan(&count)
	return count
}

// plainTextToHTML wraps plain text (paragraphs separated by blank lines,
// as pdf_walker/the pdf-chunk endpoint produces) into simple <p> tags so
// the existing htmlToTiptapJSON converter can be reused instead of
// writing a second plain-text-to-tiptap path.
func plainTextToHTML(text string) string {
	paras := strings.Split(text, "\n\n")
	var b strings.Builder
	for _, p := range paras {
		p = strings.TrimSpace(p)
		if p == "" {
			continue
		}
		b.WriteString("<p>")
		b.WriteString(html.EscapeString(p))
		b.WriteString("</p>")
	}
	if b.Len() == 0 {
		return "<p></p>"
	}
	return b.String()
}

// pdfImageExtToContentType maps pdf_walker's fitz-reported extension to a
// MIME type for the MinIO PutObject call.
func pdfImageExtToContentType(ext string) string {
	switch strings.ToLower(ext) {
	case "png":
		return "image/png"
	case "jpg", "jpeg":
		return "image/jpeg"
	case "webp":
		return "image/webp"
	case "gif":
		return "image/gif"
	default:
		return "application/octet-stream"
	}
}

// uploadPdfImage uploads one extracted PDF image's raw bytes to MinIO
// (extends image_extractor.go's uploadDataURI pattern with a raw-bytes
// variant — PDF images arrive as bytes, not data: URIs) and returns the
// storage key (not a /media/ URL — chapter_page_images.storage_key
// stores the raw key, consistent with chapters.storage_key elsewhere).
func (t *ImportProcessor) uploadPdfImage(
	ctx context.Context, bookID, jobID string, chunkIdx, imgIdx int, data []byte, ext string,
) (string, error) {
	if ext == "" {
		ext = "png"
	}
	objectKey := fmt.Sprintf("chapters/%s/import-%s-pdf-chunk-%d/img-%03d.%s", bookID, jobID, chunkIdx, imgIdx, ext)
	_, err := t.Minio.PutObject(ctx, t.Cfg.MinioBucket, objectKey, bytes.NewReader(data), int64(len(data)),
		minio.PutObjectOptions{ContentType: pdfImageExtToContentType(ext)})
	if err != nil {
		return "", fmt.Errorf("minio put: %w", err)
	}
	return objectKey, nil
}
