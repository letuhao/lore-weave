package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"path"
	"strings"

	"github.com/google/uuid"
)

type upsertEPUBImportAssetRequest struct {
	SourcePath      string `json:"source_path"`
	SourceMediaType string `json:"source_media_type"`
	SHA256          string `json:"sha256"`
	SizeBytes       int64  `json:"size_bytes"`
	ObjectKey       string `json:"object_key"`
}

// upsertEPUBImportAsset records an object that worker-infra already uploaded
// under a deterministic Book-owned key. The worker never writes Book tables;
// retries converge on the source/path unique constraint.
func (s *Server) upsertEPUBImportAsset(w http.ResponseWriter, r *http.Request) {
	jobID, ok := parseEPUBImportJobID(w, r)
	if !ok {
		return
	}
	var body upsertEPUBImportAssetRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || !validEPUBImportAssetRequest(body) {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "invalid EPUB asset metadata")
		return
	}
	var sourceID uuid.UUID
	var sourceSHA string
	err := s.pool.QueryRow(r.Context(), `
SELECT j.source_id,s.sha256
FROM import_jobs j JOIN import_sources s ON s.id=j.source_id
WHERE j.id=$1 AND j.pipeline_version=$2
`, jobID, epubImportPipelineVersion).Scan(&sourceID, &sourceSHA)
	if err != nil {
		EPUBImportAssetsTotal.WithLabelValues("failure").Inc()
		writeError(w, http.StatusNotFound, "IMPORT_NOT_FOUND", "import job not found")
		return
	}
	if !validEPUBImportAssetObjectKey(sourceSHA, body) {
		writeError(w, http.StatusBadRequest, "INVALID_BODY", "asset object key is outside the import source namespace")
		return
	}
	publicURL := fmt.Sprintf("/media/%s/%s", s.cfg.BooksStorageBucket, body.ObjectKey)
	_, err = s.pool.Exec(r.Context(), `
INSERT INTO import_assets(source_id,source_path,source_media_type,sha256,size_bytes,object_key,public_url,status)
VALUES($1,$2,$3,$4,$5,$6,$7,'imported')
ON CONFLICT (source_id,source_path) DO UPDATE
SET source_media_type=EXCLUDED.source_media_type,sha256=EXCLUDED.sha256,size_bytes=EXCLUDED.size_bytes,
    object_key=EXCLUDED.object_key,public_url=EXCLUDED.public_url,status='imported'
`, sourceID, body.SourcePath, body.SourceMediaType, body.SHA256, body.SizeBytes, body.ObjectKey, publicURL)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "failed to persist EPUB asset")
		return
	}
	EPUBImportAssetsTotal.WithLabelValues("success").Inc()
	writeJSON(w, http.StatusOK, map[string]any{"url": publicURL})
}

func validEPUBImportAssetObjectKey(sourceSHA string, body upsertEPUBImportAssetRequest) bool {
	prefix := fmt.Sprintf("imports/assets/%s/", sourceSHA)
	if !strings.HasPrefix(body.ObjectKey, prefix) || strings.Contains(body.ObjectKey, "\\") || strings.Contains(body.ObjectKey, "..") {
		return false
	}
	filename := strings.TrimPrefix(body.ObjectKey, prefix)
	if filename != path.Base(filename) {
		return false
	}
	return filename == body.SHA256+epubImportAssetExtension(body.SourceMediaType)
}

func epubImportAssetExtension(mediaType string) string {
	switch strings.ToLower(strings.TrimSpace(mediaType)) {
	case "image/jpeg":
		return ".jpg"
	case "image/png":
		return ".png"
	case "image/gif":
		return ".gif"
	case "image/webp":
		return ".webp"
	case "image/svg+xml":
		return ".svg"
	default:
		return ""
	}
}

func validEPUBImportAssetRequest(body upsertEPUBImportAssetRequest) bool {
	if body.SizeBytes <= 0 || epubImportAssetExtension(body.SourceMediaType) == "" {
		return false
	}
	if len(body.SHA256) != 64 || strings.TrimSpace(body.SourcePath) == "" || strings.TrimSpace(body.ObjectKey) == "" {
		return false
	}
	for _, character := range body.SHA256 {
		if !((character >= '0' && character <= '9') || (character >= 'a' && character <= 'f')) {
			return false
		}
	}
	return true
}
