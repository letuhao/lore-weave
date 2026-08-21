package api

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

type epubImportJobResponse struct {
	JobID             uuid.UUID  `json:"job_id"`
	BookID            uuid.UUID  `json:"book_id"`
	SourceID          uuid.UUID  `json:"source_id"`
	Status            string     `json:"status"`
	PipelineVersion   string     `json:"pipeline_version"`
	ProgressTotal     int        `json:"progress_total"`
	ProgressCompleted int        `json:"progress_completed"`
	ProgressFailed    int        `json:"progress_failed"`
	ChaptersCreated   int        `json:"chapters_created"`
	CurrentItem       any        `json:"current_item,omitempty"`
	Warnings          any        `json:"warnings"`
	Errors            any        `json:"errors"`
	Resumable         bool       `json:"resumable"`
	Cancellable       bool       `json:"cancellable"`
	RollbackAvailable bool       `json:"rollback_available"`
	CreatedAt         time.Time  `json:"created_at"`
	UpdatedAt         time.Time  `json:"updated_at"`
	CompletedAt       *time.Time `json:"completed_at,omitempty"`
	CancelRequestedAt *time.Time `json:"cancel_requested_at,omitempty"`
}

// getEpubImportJob returns the durable job state the UI polls while the
// WebSocket is unavailable. It intentionally has no client-side deadline:
// queued work can wait for worker capacity without becoming a false failure.
func (s *Server) getEpubImportJob(w http.ResponseWriter, r *http.Request) {
	jobID, ok := parseEPUBImportJobID(w, r)
	if !ok {
		return
	}
	job, found := s.loadEPUBImportJob(r.Context(), jobID)
	if !found {
		writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "import job not found")
		return
	}
	if _, _, _, allowed := s.authBook(w, r, job.BookID, GrantView); !allowed {
		return
	}
	job.CurrentItem = s.currentEPUBImportItem(r.Context(), jobID)
	writeJSON(w, http.StatusOK, job)
}

func (s *Server) listEpubImportJobItems(w http.ResponseWriter, r *http.Request) {
	jobID, ok := parseEPUBImportJobID(w, r)
	if !ok {
		return
	}
	job, found := s.loadEPUBImportJob(r.Context(), jobID)
	if !found {
		writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "import job not found")
		return
	}
	if _, _, _, allowed := s.authBook(w, r, job.BookID, GrantView); !allowed {
		return
	}
	limit, offset := parseLimitOffset(r)
	statusFilter := strings.TrimSpace(r.URL.Query().Get("status"))
	roleFilter := strings.TrimSpace(r.URL.Query().Get("role"))
	search := strings.TrimSpace(r.URL.Query().Get("search"))
	args := []any{jobID}
	where := "job_id=$1"
	if statusFilter != "" {
		args = append(args, statusFilter)
		where += " AND status=$" + strconv.Itoa(len(args))
	}
	if roleFilter != "" {
		args = append(args, roleFilter)
		where += " AND role=$" + strconv.Itoa(len(args))
	}
	if search != "" {
		args = append(args, "%"+search+"%")
		where += " AND title ILIKE $" + strconv.Itoa(len(args))
	}
	args = append(args, limit, offset)
	rows, err := s.pool.Query(r.Context(), `
SELECT id, source_key, source_href, source_fragment, parent_source_key, depth, role,
       ordinal, title, selected, status, chapter_id, error_code, error_message,
       warnings_json, started_at, completed_at
FROM import_job_items
WHERE `+where+`
ORDER BY ordinal ASC
LIMIT $`+strconv.Itoa(len(args)-1)+` OFFSET $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to load import items")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		var (
			id                                                       uuid.UUID
			chapterID                                                *uuid.UUID
			sourceKey                                                string
			depth, ordinal                                           int
			sourceHref, sourceFragment, parentSourceKey, role, title *string
			selected                                                 bool
			itemStatus                                               string
			errorCode, errorMessage                                  *string
			warnings                                                 []byte
			startedAt, completedAt                                   *time.Time
		)
		if err := rows.Scan(&id, &sourceKey, &sourceHref, &sourceFragment, &parentSourceKey, &depth, &role,
			&ordinal, &title, &selected, &itemStatus, &chapterID, &errorCode, &errorMessage,
			&warnings, &startedAt, &completedAt); err != nil {
			writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to read import item")
			return
		}
		var warningList any = []any{}
		if len(warnings) > 0 {
			_ = json.Unmarshal(warnings, &warningList)
		}
		item := map[string]any{
			"item_id":           id,
			"source_key":        sourceKey,
			"source_href":       nullableStringPtr(sourceHref),
			"source_fragment":   nullableStringPtr(sourceFragment),
			"parent_source_key": nullableStringPtr(parentSourceKey),
			"depth":             depth,
			"role":              nullableStringPtr(role),
			"ordinal":           ordinal,
			"title":             nullableStringPtr(title),
			"selected":          selected,
			"status":            itemStatus,
			"error_code":        nullableStringPtr(errorCode),
			"error_message":     nullableStringPtr(errorMessage),
			"warnings":          warningList,
			"started_at":        startedAt,
			"completed_at":      completedAt,
		}
		if chapterID != nil {
			item["chapter_id"] = *chapterID
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to load import items")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "limit": limit, "offset": offset})
}

func (s *Server) loadEPUBImportJob(ctx context.Context, jobID uuid.UUID) (epubImportJobResponse, bool) {
	var job epubImportJobResponse
	var report []byte
	err := s.pool.QueryRow(ctx, `
SELECT id, book_id, source_id, status, pipeline_version, progress_total, progress_completed,
       progress_failed, chapters_created, report_json, created_at, updated_at, completed_at,
       cancel_requested_at
FROM import_jobs
WHERE id=$1 AND pipeline_version=$2
`, jobID, epubImportPipelineVersion).Scan(&job.JobID, &job.BookID, &job.SourceID, &job.Status,
		&job.PipelineVersion, &job.ProgressTotal, &job.ProgressCompleted, &job.ProgressFailed,
		&job.ChaptersCreated, &report, &job.CreatedAt, &job.UpdatedAt, &job.CompletedAt, &job.CancelRequestedAt)
	if err != nil {
		return epubImportJobResponse{}, false
	}
	job.Warnings = []any{}
	job.Errors = []any{}
	if len(report) > 0 {
		var parsed struct {
			Warnings any `json:"warnings"`
			Errors   any `json:"errors"`
		}
		if json.Unmarshal(report, &parsed) == nil {
			if parsed.Warnings != nil {
				job.Warnings = parsed.Warnings
			}
			if parsed.Errors != nil {
				job.Errors = parsed.Errors
			}
		}
	}
	job.Resumable = job.Status == "failed" || job.Status == "cancelled"
	job.Cancellable = job.Status == "queued" || job.Status == "running" || job.Status == "import_staging"
	job.RollbackAvailable = job.Status == "completed" || job.Status == "completed_with_warnings"
	return job, true
}

func (s *Server) currentEPUBImportItem(ctx context.Context, jobID uuid.UUID) any {
	var id uuid.UUID
	var title *string
	var ordinal int
	err := s.pool.QueryRow(ctx, `
SELECT id, title, ordinal
FROM import_job_items
WHERE job_id=$1 AND status IN ('processing', 'pending')
ORDER BY CASE WHEN status='processing' THEN 0 ELSE 1 END, ordinal ASC
LIMIT 1
`, jobID).Scan(&id, &title, &ordinal)
	if err != nil {
		return nil
	}
	return map[string]any{"item_id": id, "title": nullableStringPtr(title), "ordinal": ordinal}
}

func (s *Server) cancelEpubImportJob(w http.ResponseWriter, r *http.Request) {
	jobID, ok := parseEPUBImportJobID(w, r)
	if !ok {
		return
	}
	job, found := s.loadEPUBImportJob(r.Context(), jobID)
	if !found {
		writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "import job not found")
		return
	}
	if _, _, _, allowed := s.authBook(w, r, job.BookID, GrantEdit); !allowed {
		return
	}
	if job.Status == "completed" || job.Status == "completed_with_warnings" || job.Status == "cancelled" {
		writeJSON(w, http.StatusOK, map[string]any{"job_id": jobID, "status": job.Status})
		return
	}
	_, err := s.pool.Exec(r.Context(), `UPDATE import_jobs SET status='cancelling', cancel_requested_at=COALESCE(cancel_requested_at,now()), updated_at=now() WHERE id=$1`, jobID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to cancel import")
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"job_id": jobID, "status": "cancelling"})
}

func (s *Server) getEpubImportReport(w http.ResponseWriter, r *http.Request) {
	jobID, ok := parseEPUBImportJobID(w, r)
	if !ok {
		return
	}
	job, found := s.loadEPUBImportJob(r.Context(), jobID)
	if !found {
		writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "import job not found")
		return
	}
	if _, _, _, allowed := s.authBook(w, r, job.BookID, GrantView); !allowed {
		return
	}
	report, err := s.buildEPUBImportReport(r.Context(), jobID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to load import report")
		return
	}
	writeJSON(w, http.StatusOK, report)
}

// buildEPUBImportReport derives the visible report from durable item and asset
// state. report_json only carries immutable finalization details; it is never
// the authority for progress, failures, or a later rollback.
func (s *Server) buildEPUBImportReport(ctx context.Context, jobID uuid.UUID) (map[string]any, error) {
	var (
		sourceID           uuid.UUID
		status             string
		createdAt          time.Time
		completedAt        *time.Time
		stored             []byte
		navigationSource   *string
		chaptersDetected   int
		chaptersSelected   int
		chaptersCreated    int
		chaptersActive     int
		chaptersSkipped    int
		chaptersFailed     int
		chaptersRolledBack int
	)
	err := s.pool.QueryRow(ctx, `
SELECT j.source_id,j.status,j.created_at,j.completed_at,COALESCE(j.report_json,'{}'::jsonb),
       s.inspection_json->>'navigation_source'
FROM import_jobs j JOIN import_sources s ON s.id=j.source_id
WHERE j.id=$1 AND j.pipeline_version=$2
`, jobID, epubImportPipelineVersion).Scan(&sourceID, &status, &createdAt, &completedAt, &stored, &navigationSource)
	if err != nil {
		return nil, err
	}
	err = s.pool.QueryRow(ctx, `
SELECT count(*),
       count(*) FILTER (WHERE selected),
       count(*) FILTER (WHERE selected AND status IN ('active','rolled_back')),
       count(*) FILTER (WHERE selected AND status='active'),
       count(*) FILTER (WHERE NOT selected OR status='skipped'),
       count(*) FILTER (WHERE selected AND status='failed'),
       count(*) FILTER (WHERE status='rolled_back')
FROM import_job_items WHERE job_id=$1
`, jobID).Scan(&chaptersDetected, &chaptersSelected, &chaptersCreated, &chaptersActive, &chaptersSkipped, &chaptersFailed, &chaptersRolledBack)
	if err != nil {
		return nil, err
	}

	warnings := make([]any, 0)
	errors := make([]any, 0)
	rows, err := s.pool.Query(ctx, `
SELECT source_key, COALESCE(title,''), status, error_code, error_message, warnings_json
FROM import_job_items
WHERE job_id=$1 AND selected
  AND (status='failed' OR (jsonb_typeof(warnings_json) = 'array' AND jsonb_array_length(warnings_json) > 0))
ORDER BY ordinal
`, jobID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var sourceKey, title, itemStatus string
		var errorCode, errorMessage *string
		var rawWarnings []byte
		if err := rows.Scan(&sourceKey, &title, &itemStatus, &errorCode, &errorMessage, &rawWarnings); err != nil {
			return nil, err
		}
		var itemWarnings []any
		if len(rawWarnings) > 0 && json.Unmarshal(rawWarnings, &itemWarnings) == nil {
			for _, warning := range itemWarnings {
				warnings = append(warnings, normalizeEPUBReportWarning(warning, sourceKey, ""))
			}
		}
		if itemStatus == "failed" {
			code := "epub_content_unavailable"
			if errorCode != nil && *errorCode != "" {
				code = *errorCode
			}
			message := "import item failed"
			if errorMessage != nil && *errorMessage != "" {
				message = *errorMessage
			}
			errors = append(errors, map[string]any{"source_key": sourceKey, "title": nullableString(title), "code": code, "message": message})
		}
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	rollbackRows, err := s.pool.Query(ctx, `
SELECT after_json
FROM import_job_effects
WHERE job_id=$1 AND effect_type='rollback_conflict'
ORDER BY applied_at
`, jobID)
	if err != nil {
		return nil, err
	}
	defer rollbackRows.Close()
	for rollbackRows.Next() {
		var rawConflict []byte
		if err := rollbackRows.Scan(&rawConflict); err != nil {
			return nil, err
		}
		var conflict any
		if json.Unmarshal(rawConflict, &conflict) == nil {
			warnings = append(warnings, normalizeEPUBReportWarning(conflict, "", ""))
		}
	}
	if err := rollbackRows.Err(); err != nil {
		return nil, err
	}
	warningRows, err := s.pool.Query(ctx, `
SELECT after_json FROM import_job_effects
WHERE job_id=$1 AND effect_type='rollback_warning'
ORDER BY applied_at
`, jobID)
	if err != nil {
		return nil, err
	}
	for warningRows.Next() {
		var rawWarning []byte
		if err := warningRows.Scan(&rawWarning); err != nil {
			warningRows.Close()
			return nil, err
		}
		var warning any
		if json.Unmarshal(rawWarning, &warning) == nil {
			warnings = append(warnings, normalizeEPUBReportWarning(warning, "", ""))
		}
	}
	if err := warningRows.Err(); err != nil {
		warningRows.Close()
		return nil, err
	}
	warningRows.Close()
	jobWarningRows, err := s.pool.Query(ctx, `SELECT after_json FROM import_job_effects WHERE job_id=$1 AND effect_type='job_warning' ORDER BY applied_at`, jobID)
	if err != nil {
		return nil, err
	}
	for jobWarningRows.Next() {
		var rawWarning []byte
		if err := jobWarningRows.Scan(&rawWarning); err != nil {
			jobWarningRows.Close()
			return nil, err
		}
		var warning any
		if json.Unmarshal(rawWarning, &warning) == nil {
			warnings = append(warnings, normalizeEPUBReportWarning(warning, "", ""))
		}
	}
	if err := jobWarningRows.Err(); err != nil {
		jobWarningRows.Close()
		return nil, err
	}
	jobWarningRows.Close()

	var assetsDetected, assetsImported int
	assetRows, err := s.pool.Query(ctx, `
SELECT source_path,status,warnings_json
FROM import_assets WHERE source_id=$1
`, sourceID)
	if err != nil {
		return nil, err
	}
	defer assetRows.Close()
	for assetRows.Next() {
		var sourcePath, assetStatus string
		var rawWarnings []byte
		if err := assetRows.Scan(&sourcePath, &assetStatus, &rawWarnings); err != nil {
			return nil, err
		}
		assetsDetected++
		if assetStatus == "imported" || assetStatus == "active" {
			assetsImported++
		}
		var assetWarnings []any
		if len(rawWarnings) > 0 && json.Unmarshal(rawWarnings, &assetWarnings) == nil {
			for _, warning := range assetWarnings {
				warnings = append(warnings, normalizeEPUBReportWarning(warning, "", sourcePath))
			}
		}
	}
	if err := assetRows.Err(); err != nil {
		return nil, err
	}
	var persisted map[string]any
	_ = json.Unmarshal(stored, &persisted)
	if persisted == nil {
		persisted = make(map[string]any)
	}
	finishedAt := time.Now()
	if completedAt != nil {
		finishedAt = *completedAt
	}
	persisted["job_id"] = jobID
	persisted["source_id"] = sourceID
	persisted["status"] = status
	persisted["chapters_detected"] = chaptersDetected
	persisted["chapters_selected"] = chaptersSelected
	persisted["chapters_created"] = chaptersCreated
	persisted["chapters_active"] = chaptersActive
	persisted["chapters_skipped"] = chaptersSkipped
	persisted["chapters_failed"] = chaptersFailed
	persisted["chapters_rolled_back"] = chaptersRolledBack
	persisted["assets_detected"] = assetsDetected
	persisted["assets_imported"] = assetsImported
	persisted["warnings"] = warnings
	persisted["errors"] = errors
	if navigationSource == nil || *navigationSource == "" {
		persisted["navigation_source"] = "spine"
	} else {
		persisted["navigation_source"] = *navigationSource
	}
	if _, ok := persisted["metadata_applied"]; !ok {
		persisted["metadata_applied"] = []string{}
	}
	persisted["duration_ms"] = finishedAt.Sub(createdAt).Milliseconds()
	return persisted, nil
}

func normalizeEPUBReportWarning(raw any, sourceKey, sourcePath string) map[string]any {
	warning := map[string]any{
		"code":       "unsupported_resource",
		"message":    "EPUB import emitted a warning.",
		"source_key": nullableString(sourceKey),
	}
	if sourcePath != "" {
		warning["source_path"] = sourcePath
	}
	if decoded, ok := raw.(map[string]any); ok {
		if code, ok := decoded["code"].(string); ok && code != "" {
			warning["code"] = code
		}
		if message, ok := decoded["message"].(string); ok && message != "" {
			warning["message"] = message
		}
		if itemSourceKey, ok := decoded["source_key"].(string); ok && itemSourceKey != "" {
			warning["source_key"] = itemSourceKey
		}
	}
	if warning["code"] == "rollback_conflict_user_modified" {
		warning["message"] = "Rollback retained a chapter changed after import finalization."
	}
	return warning
}

func (s *Server) resumeEpubImportJob(w http.ResponseWriter, r *http.Request) {
	jobID, ok := parseEPUBImportJobID(w, r)
	if !ok {
		return
	}
	job, found := s.loadEPUBImportJob(r.Context(), jobID)
	if !found {
		writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "import job not found")
		return
	}
	if _, _, _, allowed := s.authBook(w, r, job.BookID, GrantEdit); !allowed {
		return
	}
	s.resumeEpubImportJobPersisted(w, r, jobID, job)
}

// resumeEpubImportJobInternal is the unified Jobs control-plane seam. The
// internal token authenticates jobs-service; the owner field is then matched to
// the durable import row so a stale or forged projection cannot resume another
// user's import.
func (s *Server) resumeEpubImportJobInternal(w http.ResponseWriter, r *http.Request) {
	jobID, ok := parseEPUBImportJobID(w, r)
	if !ok {
		return
	}
	var input struct {
		OwnerUserID string `json:"owner_user_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		writeError(w, http.StatusBadRequest, "IMPORT_BAD_REQUEST", "invalid resume request")
		return
	}
	ownerID, err := uuid.Parse(strings.TrimSpace(input.OwnerUserID))
	if err != nil {
		writeError(w, http.StatusBadRequest, "IMPORT_BAD_REQUEST", "owner_user_id is required")
		return
	}
	var jobOwner uuid.UUID
	err = s.pool.QueryRow(r.Context(), `SELECT user_id FROM import_jobs WHERE id=$1 AND pipeline_version=$2`, jobID, epubImportPipelineVersion).Scan(&jobOwner)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "import job not found")
		} else {
			writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to load import job")
		}
		return
	}
	if jobOwner != ownerID {
		writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "import job not found")
		return
	}
	job, found := s.loadEPUBImportJob(r.Context(), jobID)
	if !found {
		writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "import job not found")
		return
	}
	if s.resumeEpubImportJobPersisted(w, r, jobID, job) {
		slog.InfoContext(r.Context(), "[FIX] epub import resumed through unified jobs control", "job_id", jobID, "book_id", job.BookID)
	}
}

func (s *Server) resumeEpubImportJobPersisted(w http.ResponseWriter, r *http.Request, jobID uuid.UUID, job epubImportJobResponse) bool {
	if !job.Resumable {
		writeError(w, http.StatusConflict, "IMPORT_NOT_RESUMABLE", "import job is not resumable")
		return false
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to resume import")
		return false
	}
	defer tx.Rollback(r.Context())
	var userID uuid.UUID
	var objectKey, language string
	err = tx.QueryRow(r.Context(), `SELECT j.user_id,s.object_key,COALESCE(s.metadata_json->>'language','und') FROM import_jobs j JOIN import_sources s ON s.id=j.source_id WHERE j.id=$1 FOR UPDATE`, jobID).Scan(&userID, &objectKey, &language)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to resume import")
		return false
	}
	if _, err := tx.Exec(r.Context(), `UPDATE import_job_items SET status='pending',error_code=NULL,error_message=NULL,started_at=NULL,completed_at=NULL,updated_at=now() WHERE job_id=$1 AND selected AND status IN ('failed','processing')`, jobID); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to resume import")
		return false
	}
	if _, err := tx.Exec(r.Context(), `UPDATE import_jobs SET status='queued',cancel_requested_at=NULL,progress_failed=0,updated_at=now(),completed_at=NULL WHERE id=$1`, jobID); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to resume import")
		return false
	}
	payload := map[string]any{"job_id": jobID, "book_id": job.BookID, "user_id": userID, "file_format": "epub", "file_storage_key": objectKey, "original_language": importedLanguage(language), "source_id": job.SourceID, "pipeline_version": epubImportPipelineVersion}
	if err := insertOutboxEvent(r.Context(), tx, "import.requested", jobID, payload); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to queue import")
		return false
	}
	if err := emitJobEvent(r.Context(), tx, jobID, userID, "book_import", "queued", map[string]any{"progress": map[string]any{"done": job.ProgressCompleted, "total": job.ProgressTotal}}); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to queue import")
		return false
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to resume import")
		return false
	}
	slog.InfoContext(r.Context(), "epub import resumed", "job_id", jobID, "book_id", job.BookID)
	writeJSON(w, http.StatusAccepted, map[string]any{"job_id": jobID, "status": "queued"})
	return true
}

func parseEPUBImportJobID(w http.ResponseWriter, r *http.Request) (uuid.UUID, bool) {
	jobID, err := uuid.Parse(chi.URLParam(r, "job_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_ID", "invalid job_id")
		return uuid.Nil, false
	}
	return jobID, true
}

// claimNextEPUBImportItem is the worker's only scheduling command. The row
// lock makes redelivery safe: a second worker never receives an in-flight item.
func (s *Server) claimNextEPUBImportItem(w http.ResponseWriter, r *http.Request) {
	jobID, ok := parseEPUBImportJobID(w, r)
	if !ok {
		return
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to claim import item")
		return
	}
	defer tx.Rollback(r.Context())
	var cancelled bool
	err = tx.QueryRow(r.Context(), `SELECT cancel_requested_at IS NOT NULL FROM import_jobs WHERE id=$1 AND pipeline_version=$2 FOR UPDATE`, jobID, epubImportPipelineVersion).Scan(&cancelled)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "import job not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to claim import item")
		return
	}
	if cancelled {
		_, _ = tx.Exec(r.Context(), `UPDATE import_jobs SET status='cancelled', updated_at=now(), completed_at=now() WHERE id=$1`, jobID)
		if err := tx.Commit(r.Context()); err != nil {
			writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to cancel import")
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"done": true, "cancelled": true})
		return
	}
	var item struct {
		ID                                           uuid.UUID
		SourceKey, SourceHref, SourceFragment, Title string
		Ordinal                                      int
	}
	err = tx.QueryRow(r.Context(), `
SELECT id, source_key, COALESCE(source_href,''), COALESCE(source_fragment,''), COALESCE(title,''), ordinal
FROM import_job_items WHERE job_id=$1 AND selected=true AND status='pending'
ORDER BY ordinal FOR UPDATE SKIP LOCKED LIMIT 1`, jobID).Scan(&item.ID, &item.SourceKey, &item.SourceHref, &item.SourceFragment, &item.Title, &item.Ordinal)
	if err == pgx.ErrNoRows {
		if err := tx.Commit(r.Context()); err != nil {
			writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to complete claim")
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"done": true})
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to claim import item")
		return
	}
	_, err = tx.Exec(r.Context(), `UPDATE import_job_items SET status='processing', started_at=COALESCE(started_at,now()), updated_at=now() WHERE id=$1`, item.ID)
	if err == nil {
		_, err = tx.Exec(r.Context(), `UPDATE import_jobs SET status='import_staging', updated_at=now() WHERE id=$1`, jobID)
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to claim import item")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to claim import item")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"done": false, "item_id": item.ID, "source_key": item.SourceKey, "source_href": item.SourceHref, "source_fragment": item.SourceFragment, "title": item.Title, "ordinal": item.Ordinal})
}

func (s *Server) stageEPUBImportItem(w http.ResponseWriter, r *http.Request) {
	jobID, ok := parseEPUBImportJobID(w, r)
	if !ok {
		return
	}
	itemID, err := uuid.Parse(chi.URLParam(r, "item_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_ID", "invalid item_id")
		return
	}
	var body struct {
		StagingPayload json.RawMessage `json:"staging_payload"`
		Warnings       json.RawMessage `json:"warnings"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || !json.Valid(body.StagingPayload) {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "staging_payload must be valid JSON")
		return
	}
	if len(body.Warnings) == 0 {
		body.Warnings = json.RawMessage("[]")
	}
	if !json.Valid(body.Warnings) {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "warnings must be valid JSON")
		return
	}
	result, err := s.pool.Exec(r.Context(), `UPDATE import_job_items SET status='import_ready', staging_payload=$3, warnings_json=$4, completed_at=now(), updated_at=now() WHERE id=$1 AND job_id=$2 AND status='processing'`, itemID, jobID, body.StagingPayload, body.Warnings)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to stage import item")
		return
	}
	if result.RowsAffected() == 0 {
		EPUBImportItemsTotal.WithLabelValues("failure").Inc()
		writeError(w, http.StatusConflict, "IMPORT_ITEM_NOT_CLAIMED", "import item is not claimed")
		return
	}
	_, err = s.pool.Exec(r.Context(), `UPDATE import_jobs SET progress_completed=(SELECT count(*) FROM import_job_items WHERE job_id=$1 AND status='import_ready'), updated_at=now() WHERE id=$1`, jobID)
	if err != nil {
		EPUBImportItemsTotal.WithLabelValues("failure").Inc()
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to update import progress")
		return
	}
	w.WriteHeader(http.StatusNoContent)
	EPUBImportItemsTotal.WithLabelValues("success").Inc()
}

func (s *Server) failEPUBImportItem(w http.ResponseWriter, r *http.Request) {
	jobID, ok := parseEPUBImportJobID(w, r)
	if !ok {
		return
	}
	itemID, err := uuid.Parse(chi.URLParam(r, "item_id"))
	if err != nil {
		EPUBImportItemsTotal.WithLabelValues("failure").Inc()
		writeError(w, http.StatusBadRequest, "INVALID_ID", "invalid item_id")
		return
	}
	var body struct {
		Code    string `json:"code"`
		Message string `json:"message"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || strings.TrimSpace(body.Code) == "" || strings.TrimSpace(body.Message) == "" {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "code and message are required")
		return
	}
	_, err = s.pool.Exec(r.Context(), `UPDATE import_job_items SET status='failed', error_code=$3, error_message=$4, completed_at=now(), updated_at=now() WHERE id=$1 AND job_id=$2 AND status='processing'`, itemID, jobID, body.Code, body.Message)
	if err != nil {
		EPUBImportItemsTotal.WithLabelValues("failure").Inc()
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to record import item failure")
		return
	}
	_, err = s.pool.Exec(r.Context(), `UPDATE import_jobs SET status='failed', progress_failed=(SELECT count(*) FROM import_job_items WHERE job_id=$1 AND status='failed'), updated_at=now() WHERE id=$1`, jobID)
	if err != nil {
		EPUBImportItemsTotal.WithLabelValues("failure").Inc()
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to update import progress")
		return
	}
	w.WriteHeader(http.StatusNoContent)
	EPUBImportItemsTotal.WithLabelValues("failure").Inc()
}
