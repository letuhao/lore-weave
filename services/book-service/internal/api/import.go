package api

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"path/filepath"
	"strings"

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
}

// startImport handles POST /v1/books/{book_id}/import
// It saves the uploaded file to MinIO, creates an import_jobs record,
// and writes an outbox event for the worker-infra import-processor task.
func (s *Server) startImport(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}

	// Verify book ownership
	var lifecycle string
	err := s.pool.QueryRow(r.Context(),
		`SELECT lifecycle_state FROM books WHERE id=$1 AND owner_user_id=$2`, bookID, ownerID,
	).Scan(&lifecycle)
	if err != nil {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
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
			"supported formats: .docx, .epub, .txt")
		return
	}

	// For .txt files, use existing path directly
	if fileFormat == "txt" {
		data, _ := io.ReadAll(f)
		title := strings.TrimSuffix(fh.Filename, ext)
		lang := r.FormValue("original_language")
		if lang == "" {
			lang = "auto"
		}
		s.createChapterRecord(w, r.Context(), ownerID, bookID, title, fh.Filename, lang, 0, string(data), "imported from "+fh.Filename, true)
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
`, jobID, bookID, ownerID, fh.Filename, fileFormat, int64(len(data)), storageKey)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to create import job")
		return
	}

	// Outbox event for worker-infra to pick up
	if err := insertOutboxEvent(r.Context(), tx, "import.requested", jobID, map[string]any{
		"job_id":           jobID,
		"book_id":          bookID,
		"user_id":          ownerID,
		"file_format":      fileFormat,
		"file_storage_key": storageKey,
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
		"id":        jobID,
		"book_id":   bookID,
		"status":    "pending",
		"filename":  fh.Filename,
		"file_size": int64(len(data)),
		"created_at": "now",
	})
}

// getImportJob handles GET /v1/books/{book_id}/imports/{import_id}
func (s *Server) getImportJob(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	importID, err := uuid.Parse(chi.URLParam(r, "import_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_ID", "invalid import_id")
		return
	}

	var job struct {
		ID              uuid.UUID  `json:"id"`
		BookID          uuid.UUID  `json:"book_id"`
		Status          string     `json:"status"`
		Filename        string     `json:"filename"`
		FileFormat      string     `json:"file_format"`
		FileSize        int64      `json:"file_size"`
		ChaptersCreated int        `json:"chapters_created"`
		Error           *string    `json:"error"`
		CreatedAt       string     `json:"created_at"`
		UpdatedAt       string     `json:"updated_at"`
		CompletedAt     *string    `json:"completed_at"`
	}
	err = s.pool.QueryRow(r.Context(), `
SELECT id, book_id, status, filename, file_format, file_size, chapters_created, error,
       created_at::text, updated_at::text,
       CASE WHEN completed_at IS NOT NULL THEN completed_at::text END
FROM import_jobs
WHERE id=$1 AND book_id=$2 AND user_id=$3
`, importID, bookID, ownerID).Scan(
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
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}

	rows, err := s.pool.Query(r.Context(), `
SELECT id, status, filename, file_format, file_size, chapters_created, error,
       created_at::text, updated_at::text,
       CASE WHEN completed_at IS NOT NULL THEN completed_at::text END
FROM import_jobs
WHERE book_id=$1 AND user_id=$2
ORDER BY created_at DESC
LIMIT 20
`, bookID, ownerID)
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

