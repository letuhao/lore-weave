package api

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/minio/minio-go/v7"
)

const maxImportSize = 200 << 20 // 200 MB

var allowedImportFormats = map[string]string{
	".docx": "docx",
	".epub": "epub",
	".txt":  "txt",
	".md":   "markdown", // P1 (2026-05-23) — pandoc -f markdown -t html in worker-infra.
	".pdf":  "pdf",      // docs/specs/2026-07-06-pdf-book-import.md
}

// startImport handles POST /v1/books/{book_id}/import
// It saves the uploaded file to MinIO, creates an import_jobs record,
// and writes an outbox event for the worker-infra import-processor task.
func (s *Server) startImport(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}

	// E0-2: edit grant required. The import is attributed to the CALLER (the
	// editor who initiated it) — import_jobs.user_id drives both author_user_id
	// and the WS progress notification in the worker, both of which belong to the
	// initiator. The book `owner` is needed only for storage-quota billing on the
	// synchronous .txt path (the async worker charges no quota). (D-E0-2-IMPORT-ATTRIBUTION)
	caller, ownerID, lifecycle, ok := s.authBook(w, r, bookID, GrantEdit)
	if !ok {
		return
	}
	if lifecycle != "active" {
		writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "book not active")
		return
	}

	// Parse multipart — limit to maxImportSize
	r.Body = http.MaxBytesReader(w, r.Body, maxImportSize)
	if err := r.ParseMultipartForm(maxImportSize); err != nil {
		writeError(w, http.StatusRequestEntityTooLarge, "FILE_TOO_LARGE",
			fmt.Sprintf("file exceeds %d MB limit", maxImportSize>>20))
		return
	}

	f, fh, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "file is required")
		return
	}
	defer f.Close()

	// Validate format
	ext := strings.ToLower(filepath.Ext(fh.Filename))
	fileFormat, ok := allowedImportFormats[ext]
	if !ok {
		writeError(w, http.StatusBadRequest, "UNSUPPORTED_FORMAT",
			"supported formats: .docx, .epub, .md, .pdf, .txt")
		return
	}

	// docs/specs/2026-07-06-pdf-book-import.md — pages_per_chunk/caption_images
	// are only meaningful (and only read) for the pdf format. Validated here
	// (server-side floor, not just the FE clamp — defense in depth across the
	// book-service -> worker-infra -> knowledge-service hop chain, spec §6.1).
	var pagesPerChunk int
	var captionImages bool
	var visionModelSource, visionModelRef string
	if fileFormat == "pdf" {
		pagesPerChunk, err = strconv.Atoi(r.FormValue("pages_per_chunk"))
		if err != nil || pagesPerChunk < 1 {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR",
				"pages_per_chunk must be a positive integer")
			return
		}
		captionImages = r.FormValue("caption_images") == "true"
		if captionImages {
			// BYOK — the vision op has no platform default (Provider gateway
			// invariant: explicit model_ref, never a hardcoded model). The FE
			// must let the user pick a vision-capable model when they enable
			// captioning.
			visionModelSource = r.FormValue("model_source")
			visionModelRef = r.FormValue("model_ref")
			if visionModelSource == "" || visionModelRef == "" {
				writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR",
					"model_source and model_ref are required when caption_images=true")
				return
			}
		}
	}

	// P1 (H1 fix): .txt path now goes through knowledge-service /internal/parse
	// (source_format=plain) for multi-language structural decomposition.
	// Synchronous because .txt files are small; preserves existing UX.
	if fileFormat == "txt" {
		data, _ := io.ReadAll(f)
		lang := r.FormValue("original_language")
		if lang == "" {
			lang = "auto"
		}
		s.processTxtImport(w, r, caller, ownerID, bookID, fh.Filename, string(data), lang)
		return
	}

	// Read file into memory for MinIO upload
	data, err := io.ReadAll(f)
	if err != nil {
		writeError(w, http.StatusRequestEntityTooLarge, "FILE_TOO_LARGE", "failed to read file")
		return
	}

	// Upload to MinIO
	jobID := uuid.New()
	storageKey := fmt.Sprintf("imports/%s/%s%s", bookID, jobID, ext)
	if s.minio != nil {
		// Ensure bucket exists
		exists, _ := s.minio.BucketExists(r.Context(), s.cfg.BooksStorageBucket)
		if !exists {
			_ = s.minio.MakeBucket(r.Context(), s.cfg.BooksStorageBucket, minio.MakeBucketOptions{})
		}
		_, err = s.minio.PutObject(r.Context(), s.cfg.BooksStorageBucket, storageKey,
			bytes.NewReader(data), int64(len(data)),
			minio.PutObjectOptions{ContentType: fh.Header.Get("Content-Type")})
		if err != nil {
			slog.ErrorContext(r.Context(), "import: minio upload failed", "error", err)
			writeError(w, http.StatusInternalServerError, "IMPORT_UPLOAD_FAILED", "failed to store file")
			return
		}
	}

	// Create import job + outbox event in one transaction
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "internal error")
		return
	}
	defer tx.Rollback(r.Context())

	var pagesPerChunkParam, visionModelSourceParam, visionModelRefParam any
	if fileFormat == "pdf" {
		pagesPerChunkParam = pagesPerChunk
		if captionImages {
			visionModelSourceParam = visionModelSource
			visionModelRefParam = visionModelRef
		}
	}
	_, err = tx.Exec(r.Context(), `
INSERT INTO import_jobs (id, book_id, user_id, status, filename, file_format, file_size, file_storage_key, pages_per_chunk, caption_images, vision_model_source, vision_model_ref)
VALUES ($1, $2, $3, 'pending', $4, $5, $6, $7, $8, $9, $10, $11)
`, jobID, bookID, caller, fh.Filename, fileFormat, int64(len(data)), storageKey,
		pagesPerChunkParam, captionImages, visionModelSourceParam, visionModelRefParam)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to create import job")
		return
	}

	// Outbox event for worker-infra to pick up. user_id = the initiating caller
	// (drives chapter author_user_id + the WS progress notification in the worker).
	outboxPayload := map[string]any{
		"job_id":            jobID,
		"book_id":           bookID,
		"user_id":           caller,
		"file_format":       fileFormat,
		"file_storage_key":  storageKey,
		"original_language": r.FormValue("original_language"),
	}
	if fileFormat == "pdf" {
		outboxPayload["pages_per_chunk"] = pagesPerChunk
		outboxPayload["caption_images"] = captionImages
		if captionImages {
			outboxPayload["vision_model_source"] = visionModelSource
			outboxPayload["vision_model_ref"] = visionModelRef
		}
	}
	if err := insertOutboxEvent(r.Context(), tx, "import.requested", jobID, outboxPayload); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to queue import")
		return
	}

	// Unified Job Control Plane (D-JOBS-BOOK-IMPORT-UNWIRED) — emit the 'pending' lifecycle
	// event in the SAME tx (H1) so the import is visible on the unified Jobs screen from
	// creation. Distinct from the `import.requested` (chapter-aggregate) worker trigger above.
	if err := emitJobEvent(r.Context(), tx, jobID, caller, "book_import", "pending", map[string]any{
		"title":  fh.Filename,
		"params": map[string]any{"file_format": fileFormat, "filename": fh.Filename},
	}); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to queue import")
		return
	}

	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to commit")
		return
	}

	writeJSON(w, http.StatusAccepted, map[string]any{
		"id":         jobID,
		"book_id":    bookID,
		"status":     "pending",
		"filename":   fh.Filename,
		"file_size":  int64(len(data)),
		"created_at": "now",
	})
}

// ── Bulk plain-text chapter create ───────────────────────────────────────────

const maxBulkChapters = 500 // per request; the FE sends naturally-sorted batches

// chapterTitleRe extracts the title from a CJK chapter header line like
// "第1章 八百年后" / "第 12 章   標題". Used only as a fallback when the client
// did not supply a title (the FE parses + lets the user edit it before import).
var chapterTitleRe = regexp.MustCompile(`^\s*第\s*\d+\s*[章节回卷]\s*(.+?)\s*$`)

func extractChapterTitle(content string) string {
	for _, line := range strings.SplitN(content, "\n", 6) {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		if m := chapterTitleRe.FindStringSubmatch(line); m != nil {
			return strings.TrimSpace(m[1])
		}
		// First non-empty line that isn't a marker — use it (capped).
		if utf8.RuneCountInString(line) > 120 {
			return string([]rune(line)[:120])
		}
		return line
	}
	return ""
}

type bulkChapterItem struct {
	OriginalFilename string  `json:"original_filename"`
	Content          string  `json:"content"`
	Title            *string `json:"title,omitempty"`
}

type bulkChaptersReq struct {
	Chapters         []bulkChapterItem `json:"chapters"`
	OriginalLanguage string            `json:"original_language"`
}

// bulkCreateChapters handles POST /v1/books/{book_id}/chapters/bulk — creates many
// plain-text chapters in one request (one chapter per item, no structural parse),
// used by the folder/large-import flow. The FE sends naturally-sorted, exclude-
// filtered batches SEQUENTIALLY so a monotonic sort_order (max+1) preserves order.
// Imported chapters are published canon (parity with the single-file .txt import).
// Scenes are intentionally skipped here (a chapter without scenes is valid; the
// draft body is the canonical edit/translation source) — the structural decomposer
// is the single-file path's job, not the bulk one.
func (s *Server) bulkCreateChapters(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	caller, owner, lifecycle, ok := s.authBook(w, r, bookID, GrantEdit)
	if !ok {
		return
	}
	if lifecycle != "active" {
		writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "book not active")
		return
	}

	var req bulkChaptersReq
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxImportSize)).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid JSON body")
		return
	}
	if len(req.Chapters) == 0 {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "chapters must not be empty")
		return
	}
	if len(req.Chapters) > maxBulkChapters {
		writeError(w, http.StatusUnprocessableEntity, "BOOK_TOO_MANY",
			fmt.Sprintf("at most %d chapters per request", maxBulkChapters))
		return
	}
	lang := req.OriginalLanguage
	if lang == "" {
		lang = "auto"
	}

	// Quota: content bills the book owner. Check the whole batch up front.
	var batchBytes int64
	for _, it := range req.Chapters {
		batchBytes += int64(len(it.Content))
	}
	_ = s.ensureQuotaRow(r.Context(), owner)
	_ = s.recalcQuota(r.Context(), owner)
	var used, quota int64
	_ = s.pool.QueryRow(r.Context(),
		`SELECT used_bytes, quota_bytes FROM user_storage_quota WHERE owner_user_id=$1`,
		owner).Scan(&used, &quota)
	if used+batchBytes > quota { // same gate as the single-file .txt import (processTxtImport)
		writeError(w, http.StatusInsufficientStorage, "STORAGE_QUOTA_EXCEEDED", "quota exceeded")
		return
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "db begin failed")
		return
	}
	defer tx.Rollback(r.Context())

	var maxSort int
	_ = tx.QueryRow(r.Context(),
		`SELECT COALESCE(MAX(sort_order),0) FROM chapters WHERE book_id=$1 AND lifecycle_state='active'`,
		bookID).Scan(&maxSort)
	sortOrder := maxSort + 1

	// Idempotent re-import: skip items whose original_filename already exists (active)
	// in this book. A 4000-file import that fails on a mid batch leaves the earlier
	// batches committed; re-running then resumes (already-imported files skip) instead
	// of duplicating every chapter. Updating an existing chapter's content is the
	// editor's job, not import's — so a same-filename re-import is intentionally a no-op.
	existing := map[string]struct{}{}
	if rows, err := tx.Query(r.Context(),
		`SELECT original_filename FROM chapters WHERE book_id=$1 AND lifecycle_state='active'`, bookID); err == nil {
		for rows.Next() {
			var fn string
			if rows.Scan(&fn) == nil {
				existing[fn] = struct{}{}
			}
		}
		rows.Close()
	}

	created, skipped := 0, 0
	for _, it := range req.Chapters {
		title := ""
		if it.Title != nil {
			title = strings.TrimSpace(*it.Title)
		}
		if title == "" {
			title = extractChapterTitle(it.Content)
		}
		filename := strings.TrimSpace(it.OriginalFilename)
		if filename == "" {
			filename = fmt.Sprintf("chapter-%04d.txt", sortOrder)
		}
		if _, dup := existing[filename]; dup {
			skipped++
			continue
		}
		existing[filename] = struct{}{} // guard against duplicate filenames within this batch too
		jsonBody := plainTextToTiptapJSON(it.Content)
		storageKey := fmt.Sprintf("chapters/%s/%s", bookID, uuid.New().String())

		var chapterID uuid.UUID
		if err := tx.QueryRow(r.Context(), `
INSERT INTO chapters(book_id, title, original_filename, original_language, content_type, byte_size, sort_order, storage_key, lifecycle_state, draft_updated_at, updated_at)
VALUES($1,$2,$3,$4,'text/plain',$5,$6,$7,'active',now(),now())
RETURNING id
`, bookID, nullIfEmpty(title), filename, lang, int64(len(it.Content)), sortOrder, storageKey).Scan(&chapterID); err != nil {
			writeError(w, http.StatusConflict, "BOOK_CONFLICT", fmt.Sprintf("insert chapter %q: %v", filename, err))
			return
		}
		_, _ = tx.Exec(r.Context(),
			`INSERT INTO chapter_raw_objects(chapter_id, body_text) VALUES($1,$2)`, chapterID, it.Content)
		_, _ = tx.Exec(r.Context(),
			`INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_updated_at, draft_version) VALUES($1,$2,'json',now(),1)`,
			chapterID, jsonBody)
		var importRevID uuid.UUID
		if err := tx.QueryRow(r.Context(),
			`INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id) VALUES($1,$2,'json',$3,$4) RETURNING id`,
			chapterID, jsonBody, "bulk import from "+filename, caller).Scan(&importRevID); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", fmt.Sprintf("insert revision: %v", err))
			return
		}
		if _, err := tx.Exec(r.Context(),
			// WS-0.3 — THE dangerous writer (spec §3.2). This site auto-publishes WITHOUT
			// setting last_parsed_revision_id and inserts no scenes rows: it relies entirely
			// on the reparse sweeper to index it later. Once the sweeper is re-keyed onto
			// kg_indexed_revision_id (WS-0.5), a bulk-imported book that never got the
			// pointer would be INVISIBLE TO THE SWEEPER FOREVER → scenes never parsed →
			// extraction_leaves has no scene to key on → KG extraction silently degrades.
			// The WS-0.2 migration backfill hides this on existing books, so a smoke test
			// on today's corpus would pass while every FUTURE import is broken.
			`UPDATE chapters SET draft_revision_count=1, editorial_status='published', published_revision_id=$2, kg_indexed_revision_id=$2 WHERE id=$1`,
			chapterID, importRevID); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", fmt.Sprintf("publish chapter: %v", err))
			return
		}
		if err := insertOutboxEvent(r.Context(), tx, "chapter.created", chapterID,
			map[string]any{"book_id": bookID}); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to queue chapter event")
			return
		}
		sortOrder++
		created++
	}

	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", fmt.Sprintf("commit failed: %v", err))
		return
	}
	_ = s.recalcQuota(r.Context(), owner)

	writeJSON(w, http.StatusCreated, map[string]any{
		"chapters_created": created,
		"skipped_existing": skipped,
		"book_id":          bookID,
	})
}

// getImportJob handles GET /v1/books/{book_id}/imports/{import_id}
func (s *Server) getImportJob(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	importID, err := uuid.Parse(chi.URLParam(r, "import_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_ID", "invalid import_id")
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantView); !ok {
		return
	}

	var job struct {
		ID              uuid.UUID `json:"id"`
		BookID          uuid.UUID `json:"book_id"`
		Status          string    `json:"status"`
		Filename        string    `json:"filename"`
		FileFormat      string    `json:"file_format"`
		FileSize        int64     `json:"file_size"`
		ChaptersCreated int       `json:"chapters_created"`
		Error           *string   `json:"error"`
		CreatedAt       string    `json:"created_at"`
		UpdatedAt       string    `json:"updated_at"`
		CompletedAt     *string   `json:"completed_at"`
	}
	err = s.pool.QueryRow(r.Context(), `
SELECT id, book_id, status, filename, file_format, file_size, chapters_created, error,
       created_at::text, updated_at::text,
       CASE WHEN completed_at IS NOT NULL THEN completed_at::text END
FROM import_jobs
WHERE id=$1 AND book_id=$2
`, importID, bookID).Scan(
		&job.ID, &job.BookID, &job.Status, &job.Filename, &job.FileFormat,
		&job.FileSize, &job.ChaptersCreated, &job.Error,
		&job.CreatedAt, &job.UpdatedAt, &job.CompletedAt,
	)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "import job not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "internal error")
		return
	}

	writeJSON(w, http.StatusOK, job)
}

// listImportJobs handles GET /v1/books/{book_id}/imports
func (s *Server) listImportJobs(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantView); !ok {
		return
	}

	rows, err := s.pool.Query(r.Context(), `
SELECT id, status, filename, file_format, file_size, chapters_created, error,
       created_at::text, updated_at::text,
       CASE WHEN completed_at IS NOT NULL THEN completed_at::text END
FROM import_jobs
WHERE book_id=$1
ORDER BY created_at DESC
LIMIT 20
`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "internal error")
		return
	}
	defer rows.Close()

	type ImportJob struct {
		ID              uuid.UUID `json:"id"`
		Status          string    `json:"status"`
		Filename        string    `json:"filename"`
		FileFormat      string    `json:"file_format"`
		FileSize        int64     `json:"file_size"`
		ChaptersCreated int       `json:"chapters_created"`
		Error           *string   `json:"error"`
		CreatedAt       string    `json:"created_at"`
		UpdatedAt       string    `json:"updated_at"`
		CompletedAt     *string   `json:"completed_at"`
	}
	jobs := []ImportJob{}
	for rows.Next() {
		var j ImportJob
		if err := rows.Scan(&j.ID, &j.Status, &j.Filename, &j.FileFormat, &j.FileSize,
			&j.ChaptersCreated, &j.Error, &j.CreatedAt, &j.UpdatedAt, &j.CompletedAt); err != nil {
			continue
		}
		jobs = append(jobs, j)
	}

	writeJSON(w, http.StatusOK, map[string]any{"imports": jobs})
}

// updateImportJobStatus is called by the internal endpoint for worker-infra to update job status.
func (s *Server) updateImportJobStatus(w http.ResponseWriter, r *http.Request) {
	importID, err := uuid.Parse(chi.URLParam(r, "import_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_ID", "invalid import_id")
		return
	}

	var body struct {
		Status          string  `json:"status"`
		ChaptersCreated int     `json:"chapters_created"`
		Error           *string `json:"error"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "invalid JSON")
		return
	}

	completedSQL := ""
	if body.Status == "completed" || body.Status == "failed" {
		completedSQL = ", completed_at=now()"
	}

	// UPDATE + emit the JobEvent in one tx (H1). RETURNING user_id folds in the owner lookup
	// (the emit's owner); a missing job → no row → 404 (was a silent 204 before).
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "internal error")
		return
	}
	defer tx.Rollback(r.Context())

	var ownerUserID uuid.UUID
	err = tx.QueryRow(r.Context(), fmt.Sprintf(`
UPDATE import_jobs SET status=$1, chapters_created=$2, error=$3, updated_at=now()%s WHERE id=$4
RETURNING user_id
`, completedSQL), body.Status, body.ChaptersCreated, body.Error, importID).Scan(&ownerUserID)
	if err != nil {
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "import job not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "update failed")
		return
	}

	// Unified Job Control Plane — emit the transition (D-JOBS-BOOK-IMPORT-UNWIRED). The native
	// 'processing' canonicalizes to 'running'; carry chapters as progress + the error on failed.
	extra := map[string]any{"progress": map[string]any{"done": body.ChaptersCreated}}
	if body.Status == "failed" && body.Error != nil {
		extra["error"] = map[string]any{"code": "book_import_failed", "message": *body.Error}
	}
	if err := emitJobEvent(r.Context(), tx, importID, ownerUserID, "book_import", body.Status, extra); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "emit failed")
		return
	}

	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to commit")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

// reconcileImportJobs is the Unified Job Control Plane reconcile SOURCE (H1 backstop) for
// book-import jobs: rows whose effective last-touch is at/after `since` (oldest-first, capped
// at `limit`), in canonical JobEvent payload shape, for the jobs-service sweep to upsert.
// Internal-token (mounted under /internal); ALL owners. A row whose native status has no
// canonical JobStatus is SKIPPED (matches the live emit's skip-don't-poison behavior).
// GET /internal/book/jobs?since=<iso>&limit=<n>  (D-JOBS-BOOK-IMPORT-UNWIRED)
func (s *Server) reconcileImportJobs(w http.ResponseWriter, r *http.Request) {
	since, err := time.Parse(time.RFC3339, r.URL.Query().Get("since"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_SINCE", "since must be RFC3339")
		return
	}
	limit := 1000
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, e := strconv.Atoi(v); e == nil && n > 0 && n <= 5000 {
			limit = n
		}
	}
	// Effective last-touch (all three columns present on import_jobs).
	rows, err := s.pool.Query(r.Context(), `
SELECT id, user_id, status, chapters_created, error,
       GREATEST(created_at, updated_at, COALESCE(completed_at, created_at)) AS ts
FROM import_jobs
WHERE GREATEST(created_at, updated_at, COALESCE(completed_at, created_at)) >= $1
ORDER BY ts ASC LIMIT $2
`, since, limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "query failed")
		return
	}
	defer rows.Close()

	jobs := []map[string]any{}
	for rows.Next() {
		var id, userID uuid.UUID
		var nativeStatus string
		var chapters int
		var errMsg *string
		var ts time.Time
		if err := rows.Scan(&id, &userID, &nativeStatus, &chapters, &errMsg, &ts); err != nil {
			writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "scan failed")
			return
		}
		job, ok := importJobEventPayload(id, userID, nativeStatus, chapters, errMsg, ts)
		if !ok {
			continue // unmappable status → skip (don't ship one the projection can't parse)
		}
		jobs = append(jobs, job)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "iteration failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"jobs": jobs})
}
