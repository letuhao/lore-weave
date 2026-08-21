package api

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"path/filepath"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/loreweave/epubimport"
)

const epubImportPipelineVersion = "epub-v2"

type startEPUBImportRequest struct {
	SourceID uuid.UUID `json:"source_id"`
	Target   struct {
		Mode   string     `json:"mode"`
		BookID *uuid.UUID `json:"book_id,omitempty"`
	} `json:"target"`
	Strategy                string            `json:"strategy"`
	MetadataPolicy          map[string]string `json:"metadata_policy"`
	SelectedSourceKeys      []string          `json:"selected_source_keys"`
	TitleOverrides          map[string]string `json:"title_overrides"`
	Options                 map[string]any    `json:"options"`
	DestructiveConfirmation bool              `json:"destructive_confirmation"`
}

type epubImportSourceRecord struct {
	ID             uuid.UUID
	Filename       string
	ObjectKey      string
	SHA256         string
	CompressedSize int64
	MetadataJSON   []byte
	InspectionJSON []byte
	Inspection     epubimport.Inspection
}

// startEpubImport creates a source-retained, item-level import job. The
// inspector is the sole authority for the chapter boundary tree; this handler
// never parses headings or source XHTML.
func (s *Server) startEpubImport(w http.ResponseWriter, r *http.Request) {
	if s.cfg.EPUBImportV2Mode == "off" || s.cfg.EPUBImportV2Mode == "shadow" {
		writeError(w, http.StatusConflict, "EPUB_IMPORT_V2_DISABLED", "the EPUB import v2 pipeline is not enabled")
		return
	}
	caller, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}

	var in startEPUBImportRequest
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "invalid JSON")
		return
	}
	if in.SourceID == uuid.Nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "source_id is required")
		return
	}
	if in.Strategy == "" {
		in.Strategy = "append"
	}
	if !validEPUBImportStrategy(in.Strategy) {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "strategy must be append, replace_all, or merge_by_source_key")
		return
	}
	if in.Strategy == "replace_all" && !in.DestructiveConfirmation {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "replace_all requires destructive_confirmation")
		return
	}

	var existingBookID uuid.UUID
	switch in.Target.Mode {
	case "existing_book":
		if in.Target.BookID == nil || *in.Target.BookID == uuid.Nil {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "target.book_id is required for existing_book")
			return
		}
		resolvedCaller, _, lifecycle, allowed := s.authBook(w, r, *in.Target.BookID, GrantEdit)
		if !allowed {
			return
		}
		if lifecycle != "active" {
			writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "book not active")
			return
		}
		caller = resolvedCaller
		existingBookID = *in.Target.BookID
	case "new_book":
		if err := s.ensureQuotaRow(r.Context(), caller); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to initialize quota")
			return
		}
		count, err := s.countActiveBooks(r.Context(), caller)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to check book quota")
			return
		}
		if count >= maxBooksPerUser {
			writeError(w, http.StatusConflict, "BOOK_LIMIT_REACHED", fmt.Sprintf("book limit reached (%d) — delete or purge a book first", maxBooksPerUser))
			return
		}
	default:
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "target.mode must be existing_book or new_book")
		return
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to start import")
		return
	}
	defer tx.Rollback(r.Context())

	source, err := loadEPUBImportSource(r.Context(), tx, caller, in.SourceID)
	if err != nil {
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusNotFound, "IMPORT_SOURCE_NOT_FOUND", "EPUB source not found")
			return
		}
		slog.ErrorContext(r.Context(), "epub import source load failed", "error", err, "source_id", in.SourceID)
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to load EPUB source")
		return
	}

	selected, err := selectEPUBImportItems(source.Inspection.Structure, in.SelectedSourceKeys)
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", err.Error())
		return
	}
	if len(selected) == 0 {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "at least one content chapter must be selected")
		return
	}

	bookID := existingBookID
	if in.Target.Mode == "new_book" {
		bookID, err = createEPUBImportBook(r.Context(), tx, caller, source.Inspection.Metadata, source.Filename)
		if err != nil {
			slog.ErrorContext(r.Context(), "epub import book creation failed", "error", err, "source_id", source.ID)
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to create book")
			return
		}
	}

	optionsJSON, err := json.Marshal(map[string]any{
		"strategy":        in.Strategy,
		"metadata_policy": in.MetadataPolicy,
		"options":         in.Options,
	})
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid import options")
		return
	}
	jobID := uuid.New()
	_, err = tx.Exec(r.Context(), `
INSERT INTO import_jobs (
  id, book_id, user_id, status, filename, file_format, file_size, file_storage_key,
  source_id, target_mode, options_json, progress_total, pipeline_version
) VALUES ($1, $2, $3, 'queued', $4, 'epub', $5, $6, $7, $8, $9, $10, $11)
`, jobID, bookID, caller, source.Filename, source.CompressedSize, source.ObjectKey,
		source.ID, in.Target.Mode, optionsJSON, len(selected), epubImportPipelineVersion)
	if err != nil {
		slog.ErrorContext(r.Context(), "epub import job creation failed", "error", err, "source_id", source.ID, "book_id", bookID)
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to create import job")
		return
	}

	if err := insertEPUBImportItems(r.Context(), tx, jobID, source.SHA256, source.Inspection.Structure, selected, in.TitleOverrides); err != nil {
		slog.ErrorContext(r.Context(), "epub import item creation failed", "error", err, "job_id", jobID)
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to create import items")
		return
	}

	payload := map[string]any{
		"job_id":            jobID,
		"book_id":           bookID,
		"user_id":           caller,
		"file_format":       "epub",
		"file_storage_key":  source.ObjectKey,
		"original_language": importedLanguage(source.Inspection.Metadata.Language),
		"source_id":         source.ID,
		"pipeline_version":  epubImportPipelineVersion,
		"target_mode":       in.Target.Mode,
		"lore_genres":       source.Inspection.Metadata.Subjects,
	}
	if err := insertOutboxEvent(r.Context(), tx, "import.requested", jobID, payload); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to queue import")
		return
	}
	if err := emitJobEvent(r.Context(), tx, jobID, caller, "book_import", "queued", map[string]any{
		"title":    source.Filename,
		"params":   map[string]any{"file_format": "epub", "pipeline_version": epubImportPipelineVersion},
		"progress": map[string]any{"done": 0, "total": len(selected)},
	}); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to queue import")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to commit import")
		return
	}

	slog.InfoContext(r.Context(), "epub import job created", "job_id", jobID, "source_id", source.ID, "book_id", bookID, "item_count", len(selected))
	writeJSON(w, http.StatusAccepted, map[string]any{"job_id": jobID, "book_id": bookID, "status": "queued"})
}

func validEPUBImportStrategy(strategy string) bool {
	switch strategy {
	case "append", "replace_all", "merge_by_source_key":
		return true
	default:
		return false
	}
}

func loadEPUBImportSource(ctx context.Context, tx pgx.Tx, ownerID, sourceID uuid.UUID) (epubImportSourceRecord, error) {
	var source epubImportSourceRecord
	err := tx.QueryRow(ctx, `
SELECT id, original_filename, object_key, sha256, compressed_size, metadata_json, inspection_json
FROM import_sources
WHERE id=$1 AND owner_user_id=$2 AND source_type='epub' AND deleted_at IS NULL
`, sourceID, ownerID).Scan(&source.ID, &source.Filename, &source.ObjectKey, &source.SHA256,
		&source.CompressedSize, &source.MetadataJSON, &source.InspectionJSON)
	if err != nil {
		return epubImportSourceRecord{}, err
	}
	if err := json.Unmarshal(source.InspectionJSON, &source.Inspection); err != nil {
		return epubImportSourceRecord{}, fmt.Errorf("decode persisted EPUB inspection: %w", err)
	}
	if source.Inspection.SHA256 != source.SHA256 {
		return epubImportSourceRecord{}, fmt.Errorf("persisted EPUB source fingerprint mismatch")
	}
	return source, nil
}

func createEPUBImportBook(ctx context.Context, tx pgx.Tx, ownerID uuid.UUID, metadata epubimport.Metadata, filename string) (uuid.UUID, error) {
	title := strings.TrimSpace(metadata.Title)
	if title == "" {
		title = strings.TrimSuffix(filepath.Base(filename), filepath.Ext(filename))
	}
	if title == "" {
		title = "Imported EPUB"
	}
	// books.genre_tags is NOT NULL. EPUB metadata is allowed to omit dc:subject,
	// so preserve that absence as an empty tag list instead of a SQL NULL.
	genreTags := metadata.Subjects
	if genreTags == nil {
		genreTags = []string{}
	}
	var bookID uuid.UUID
	err := tx.QueryRow(ctx, `
INSERT INTO books(owner_user_id, title, description, original_language, genre_tags, kind)
VALUES($1, $2, $3, $4, $5, 'novel')
RETURNING id
	`, ownerID, title, strings.TrimSpace(metadata.Description), importedLanguage(metadata.Language), genreTags).Scan(&bookID)
	return bookID, err
}

func importedLanguage(language string) string {
	language = strings.TrimSpace(language)
	if language == "" || strings.EqualFold(language, "auto") {
		return "und"
	}
	return language
}

func selectEPUBImportItems(roots []*epubimport.NavigationNode, requested []string) (map[string]bool, error) {
	requestedSet := make(map[string]struct{}, len(requested))
	for _, sourceKey := range requested {
		if sourceKey = strings.TrimSpace(sourceKey); sourceKey != "" {
			requestedSet[sourceKey] = struct{}{}
		}
	}
	found := make(map[string]bool, len(requestedSet))
	selected := make(map[string]bool)
	var visit func(nodes []*epubimport.NavigationNode, selectedByAncestor bool)
	visit = func(nodes []*epubimport.NavigationNode, selectedByAncestor bool) {
		for _, node := range nodes {
			_, explicitlySelected := requestedSet[node.SourceKey]
			if explicitlySelected {
				found[node.SourceKey] = true
			}
			include := selectedByAncestor || explicitlySelected
			if len(requestedSet) == 0 {
				include = node.Selected
			}
			if len(node.Children) == 0 && node.SourceHref != "" && include {
				selected[node.SourceKey] = true
			}
			visit(node.Children, include)
		}
	}
	visit(roots, false)
	for sourceKey := range requestedSet {
		if !found[sourceKey] {
			return nil, fmt.Errorf("selected_source_keys contains an unknown source key")
		}
	}
	return selected, nil
}

func insertEPUBImportItems(ctx context.Context, tx pgx.Tx, jobID uuid.UUID, sourceSHA string, roots []*epubimport.NavigationNode, selected map[string]bool, titleOverrides map[string]string) error {
	var visit func(nodes []*epubimport.NavigationNode) error
	visit = func(nodes []*epubimport.NavigationNode) error {
		for _, node := range nodes {
			warnings, err := json.Marshal(node.Warnings)
			if err != nil {
				return err
			}
			title := strings.TrimSpace(titleOverrides[node.SourceKey])
			if title == "" {
				title = node.Title
			}
			status := "skipped"
			if selected[node.SourceKey] {
				status = "pending"
			}
			_, err = tx.Exec(ctx, `
INSERT INTO import_job_items (
  job_id, source_key, source_href, source_fragment, source_hash, parent_source_key,
  depth, role, ordinal, title, selected, status, warnings_json
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
`, jobID, node.SourceKey, nullableString(node.SourceHref), nullableString(node.SourceFragment), sourceSHA,
				nullableString(node.ParentSourceKey), node.Depth, string(node.Role), node.Ordinal, title,
				selected[node.SourceKey], status, warnings)
			if err != nil {
				return err
			}
			if err := visit(node.Children); err != nil {
				return err
			}
		}
		return nil
	}
	return visit(roots)
}
