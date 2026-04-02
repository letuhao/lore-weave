package api

import (
	"bytes"
	"context"
	"fmt"
	"net/http"
	"path/filepath"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/minio/minio-go/v7"
)

const (
	maxMediaSize = 10 << 20 // 10 MB
	mediaBucket  = "loreweave-media"
)

var allowedImageTypes = map[string]string{
	"image/png":  ".png",
	"image/jpeg": ".jpg",
	"image/gif":  ".gif",
	"image/webp": ".webp",
}

func (s *Server) uploadChapterMedia(w http.ResponseWriter, r *http.Request) {
	if s.minio == nil {
		writeError(w, http.StatusServiceUnavailable, "MEDIA_UNAVAILABLE", "media storage not configured")
		return
	}

	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chapterID := chi.URLParam(r, "chapter_id")
	if chapterID == "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "chapter_id required")
		return
	}

	// Validate book ownership + active lifecycle
	lifecycle, okBook, status := s.ensureOwnerBook(r.Context(), bookID, ownerID)
	if !okBook {
		writeError(w, status, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if lifecycle != "active" {
		writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "book not active")
		return
	}

	// Verify chapter belongs to this book
	var exists bool
	_ = s.pool.QueryRow(r.Context(),
		`SELECT EXISTS(SELECT 1 FROM chapters WHERE id=$1 AND book_id=$2 AND lifecycle_state='active')`,
		chapterID, bookID).Scan(&exists)
	if !exists {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}

	// Parse multipart
	if err := r.ParseMultipartForm(maxMediaSize); err != nil {
		writeError(w, http.StatusBadRequest, "MEDIA_TOO_LARGE", "file exceeds 10 MB limit")
		return
	}
	f, fh, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "file is required")
		return
	}
	defer f.Close()

	if fh.Size > maxMediaSize {
		writeError(w, http.StatusRequestEntityTooLarge, "MEDIA_TOO_LARGE", "file exceeds 10 MB limit")
		return
	}

	contentType := fh.Header.Get("Content-Type")
	ext, ok := allowedImageTypes[contentType]
	if !ok {
		writeError(w, http.StatusUnsupportedMediaType, "UNSUPPORTED_MEDIA_TYPE",
			fmt.Sprintf("unsupported type %s; allowed: png, jpg, gif, webp", contentType))
		return
	}

	// Read file
	buf := new(bytes.Buffer)
	if _, err := buf.ReadFrom(f); err != nil {
		writeError(w, http.StatusInternalServerError, "MEDIA_UPLOAD_FAILED", "failed to read file")
		return
	}

	// Generate object key
	mediaID := uuid.New().String()
	objectKey := fmt.Sprintf("books/%s/chapters/%s/%s%s", bookID, chapterID, mediaID, ext)

	// Ensure bucket exists
	ctx := r.Context()
	if err := s.ensureMediaBucket(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "MEDIA_UPLOAD_FAILED", "storage init failed")
		return
	}

	// Upload to MinIO
	_, err = s.minio.PutObject(ctx, mediaBucket, objectKey, bytes.NewReader(buf.Bytes()), int64(buf.Len()),
		minio.PutObjectOptions{ContentType: contentType})
	if err != nil {
		writeError(w, http.StatusInternalServerError, "MEDIA_UPLOAD_FAILED", "upload failed")
		return
	}

	// Build the URL — for local dev, use the MinIO endpoint directly
	mediaURL := fmt.Sprintf("http://%s/%s/%s", s.cfg.MinioEndpoint, mediaBucket, objectKey)

	originalName := fh.Filename
	if originalName == "" {
		originalName = filepath.Base(objectKey)
	}

	writeJSON(w, http.StatusCreated, map[string]any{
		"url":          mediaURL,
		"object_key":   objectKey,
		"filename":     originalName,
		"size":         buf.Len(),
		"content_type": contentType,
	})
}

func (s *Server) ensureMediaBucket(ctx context.Context) error {
	exists, err := s.minio.BucketExists(ctx, mediaBucket)
	if err != nil {
		return err
	}
	if !exists {
		return s.minio.MakeBucket(ctx, mediaBucket, minio.MakeBucketOptions{})
	}
	return nil
}

