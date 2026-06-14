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
	"strings"
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
			"supported formats: .docx, .epub, .md, .txt")
		return
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
			slog.Error("import: minio upload failed", "error", err)
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

	_, err = tx.Exec(r.Context(), `
INSERT INTO import_jobs (id, book_id, user_id, status, filename, file_format, file_size, file_storage_key)
VALUES ($1, $2, $3, 'pending', $4, $5, $6, $7)
`, jobID, bookID, caller, fh.Filename, fileFormat, int64(len(data)), storageKey)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to create import job")
		return
	}

	// Outbox event for worker-infra to pick up. user_id = the initiating caller
	// (drives chapter author_user_id + the WS progress notification in the worker).
	if err := insertOutboxEvent(r.Context(), tx, "import.requested", jobID, map[string]any{
		"job_id":            jobID,
		"book_id":           bookID,
		"user_id":           caller,
		"file_format":       fileFormat,
		"file_storage_key":  storageKey,
		"original_language": r.FormValue("original_language"),
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
			`UPDATE chapters SET draft_revision_count=1, editorial_status='published', published_revision_id=$2 WHERE id=$1`,
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

	_, err = s.pool.Exec(r.Context(), fmt.Sprintf(`
UPDATE import_jobs SET status=$1, chapters_created=$2, error=$3, updated_at=now()%s WHERE id=$4
`, completedSQL), body.Status, body.ChaptersCreated, body.Error, importID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "update failed")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}
