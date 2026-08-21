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

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/minio/minio-go/v7"

	"github.com/loreweave/epubimport"
)

// inspectEpubImport retains and validates an EPUB before a user creates an
// import job. It never creates a chapter or runs a worker.
func (s *Server) inspectEpubImport(w http.ResponseWriter, r *http.Request) {
	caller, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, maxImportSize)
	if err := r.ParseMultipartForm(maxImportSize); err != nil {
		writeError(w, http.StatusRequestEntityTooLarge, "FILE_TOO_LARGE", "file exceeds 200 MB limit")
		return
	}
	file, header, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "file is required")
		return
	}
	defer file.Close()
	if strings.ToLower(filepath.Ext(header.Filename)) != ".epub" {
		writeError(w, http.StatusUnsupportedMediaType, "UNSUPPORTED_FORMAT", "file must use the .epub extension")
		return
	}
	if targetBookID := r.FormValue("target_book_id"); targetBookID != "" {
		bookID, err := uuid.Parse(targetBookID)
		if err != nil {
			writeError(w, http.StatusBadRequest, "INVALID_ID", "invalid target_book_id")
			return
		}
		resolvedCaller, _, _, allowed := s.authBook(w, r, bookID, GrantEdit)
		if !allowed {
			return
		}
		caller = resolvedCaller
	}

	data, err := io.ReadAll(file)
	if err != nil {
		writeError(w, http.StatusRequestEntityTooLarge, "FILE_TOO_LARGE", "failed to read EPUB source")
		return
	}
	inspection, err := epubimport.Inspect(data, s.cfg.EPUBImportLimits)
	if err != nil {
		writeEPUBInspectionError(w, err)
		return
	}
	EPUBImportUncompressedBytes.Observe(float64(inspection.UncompressedSize))
	if s.minio == nil {
		writeError(w, http.StatusServiceUnavailable, "IMPORT_STORAGE_UNAVAILABLE", "source storage is unavailable")
		return
	}

	var sourceID uuid.UUID
	err = s.pool.QueryRow(r.Context(), `
SELECT id
FROM import_sources
WHERE owner_user_id=$1 AND sha256=$2 AND deleted_at IS NULL
`, caller, inspection.SHA256).Scan(&sourceID)
	duplicate := err == nil
	if err != nil && err != pgx.ErrNoRows {
		slog.ErrorContext(r.Context(), "epub import inspection lookup failed", "error", err, "source_sha256", inspection.SHA256)
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to inspect source")
		return
	}

	objectKey := fmt.Sprintf("imports/sources/%s/%s.epub", caller, inspection.SHA256)
	if !duplicate {
		exists, err := s.minio.BucketExists(r.Context(), s.cfg.BooksStorageBucket)
		if err != nil {
			slog.ErrorContext(r.Context(), "epub import source bucket check failed", "error", err, "source_sha256", inspection.SHA256)
			writeError(w, http.StatusInternalServerError, "IMPORT_UPLOAD_FAILED", "failed to access source storage")
			return
		}
		if !exists {
			if err := s.minio.MakeBucket(r.Context(), s.cfg.BooksStorageBucket, minio.MakeBucketOptions{}); err != nil {
				slog.ErrorContext(r.Context(), "epub import source bucket creation failed", "error", err, "source_sha256", inspection.SHA256)
				writeError(w, http.StatusInternalServerError, "IMPORT_UPLOAD_FAILED", "failed to prepare source storage")
				return
			}
		}
		if _, err := s.minio.PutObject(r.Context(), s.cfg.BooksStorageBucket, objectKey, bytes.NewReader(data), int64(len(data)), minio.PutObjectOptions{ContentType: "application/epub+zip"}); err != nil {
			slog.ErrorContext(r.Context(), "epub import source upload failed", "error", err, "source_sha256", inspection.SHA256)
			writeError(w, http.StatusInternalServerError, "IMPORT_UPLOAD_FAILED", "failed to store source")
			return
		}
	}

	metadataJSON, err := json.Marshal(inspection.Metadata)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to encode source metadata")
		return
	}
	inspectionJSON, err := json.Marshal(inspection)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to encode source inspection")
		return
	}
	if !duplicate {
		err = s.pool.QueryRow(r.Context(), `
INSERT INTO import_sources (
  owner_user_id, source_type, original_filename, object_key, sha256,
  compressed_size, uncompressed_size, epub_version, metadata_json, inspection_json
) VALUES ($1, 'epub', $2, $3, $4, $5, $6, $7, $8, $9)
ON CONFLICT (owner_user_id, sha256) DO UPDATE
SET deleted_at=NULL, original_filename=EXCLUDED.original_filename, metadata_json=EXCLUDED.metadata_json,
    inspection_json=EXCLUDED.inspection_json
RETURNING id
`, caller, header.Filename, objectKey, inspection.SHA256, inspection.CompressedSize,
			inspection.UncompressedSize, inspection.Metadata.EPUBVersion, metadataJSON, inspectionJSON).Scan(&sourceID)
		if err != nil {
			slog.ErrorContext(r.Context(), "epub import source persistence failed", "error", err, "source_sha256", inspection.SHA256)
			writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to persist source inspection")
			return
		}
	}
	if s.cfg.EPUBImportV2Mode == "shadow" {
		if err := s.persistEPUBShadowComparison(r.Context(), sourceID, *inspection); err != nil {
			slog.ErrorContext(r.Context(), "epub shadow comparison persistence failed", "error", err, "source_id", sourceID)
			writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to persist shadow comparison")
			return
		}
	}

	slog.InfoContext(r.Context(), "epub import source inspected",
		"source_id", sourceID,
		"source_sha256", inspection.SHA256,
		"navigation_source", inspection.NavigationSource,
		"navigation_roots", len(inspection.Structure),
		"asset_count", len(inspection.Assets),
		"duplicate_source", duplicate,
	)
	writeJSON(w, http.StatusOK, map[string]any{
		"source_id":         sourceID,
		"sha256":            inspection.SHA256,
		"duplicate_source":  duplicate,
		"metadata":          inspection.Metadata,
		"cover":             inspection.Cover,
		"navigation_source": inspection.NavigationSource,
		"structure":         inspection.Structure,
		"warnings":          inspection.Warnings,
		"limits":            epubLimitResponse(s.cfg.EPUBImportLimits),
	})
}

func writeEPUBInspectionError(w http.ResponseWriter, err error) {
	if typed, ok := err.(*epubimport.Error); ok {
		switch typed.Code {
		case epubimport.CodeInvalidArchive, epubimport.CodeInvalidMIME, epubimport.CodeContainerMissing, epubimport.CodeInvalidOPF, epubimport.CodeDRMUnsupported, epubimport.CodeInvalidArchivePath, epubimport.CodeArchiveLimit, epubimport.CodeInvalidNavigation:
			writeError(w, http.StatusUnprocessableEntity, string(typed.Code), typed.Message)
			return
		}
	}
	writeError(w, http.StatusUnprocessableEntity, "epub_invalid_archive", "EPUB inspection failed")
}

func epubLimitResponse(limits epubimport.Limits) map[string]int64 {
	limits = limits.Normalize()
	return map[string]int64{
		"max_compressed_size":   limits.MaxCompressedSize,
		"max_uncompressed_size": limits.MaxUncompressedSize,
		"max_zip_entries":       int64(limits.MaxZipEntries),
		"max_single_entry_size": limits.MaxSingleEntrySize,
		"max_content_documents": int64(limits.MaxContentDocuments),
		"max_navigation_nodes":  int64(limits.MaxNavigationNodes),
		"max_assets":            int64(limits.MaxAssets),
		"max_chapter_html_size": limits.MaxChapterHTMLSize,
	}
}
