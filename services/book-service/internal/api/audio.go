package api

import (
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/minio/minio-go/v7"
)

const maxAudioSize = 20 << 20 // 20 MB

var allowedAudioTypes = map[string]string{
	"audio/mpeg": ".mp3",
	"audio/wav":  ".wav",
	"audio/ogg":  ".ogg",
	"audio/webm": ".webm",
	"audio/mp4":  ".m4a",
}

// ── Response types ─────────────────────────────────────────────────────────────

type audioSegmentSummary struct {
	SegmentID      uuid.UUID `json:"segment_id"`
	BlockIndex     int       `json:"block_index"`
	SourceTextHash string    `json:"source_text_hash"`
	Voice          string    `json:"voice"`
	Provider       string    `json:"provider"`
	Language       string    `json:"language"`
	MediaKey       string    `json:"media_key"`
	DurationMs     int       `json:"duration_ms"`
	CreatedAt      time.Time `json:"created_at"`
}

type audioSegmentDetail struct {
	audioSegmentSummary
	SourceText string `json:"source_text"`
}

// ── List segments ──────────────────────────────────────────────────────────────

func (s *Server) listAudioSegments(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chapterID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	if _, okBook, st := s.ensureOwnerBook(r.Context(), bookID, ownerID); !okBook {
		writeError(w, st, "BOOK_NOT_FOUND", "book not found")
		return
	}

	language := r.URL.Query().Get("language")
	voice := r.URL.Query().Get("voice")
	if language == "" || voice == "" {
		writeError(w, http.StatusBadRequest, "AUDIO_VALIDATION_ERROR", "language and voice query params required")
		return
	}

	rows, err := s.pool.Query(r.Context(), `
		SELECT segment_id, block_index, source_text_hash, voice, provider, language, media_key, duration_ms, created_at
		FROM chapter_audio_segments
		WHERE chapter_id = $1 AND language = $2 AND voice = $3
		ORDER BY block_index ASC
	`, chapterID, language, voice)
	if err != nil {
		slog.Error("listAudioSegments query", "error", err)
		writeError(w, http.StatusInternalServerError, "AUDIO_QUERY_ERROR", "failed to query audio segments")
		return
	}
	defer rows.Close()

	segments := make([]audioSegmentSummary, 0)
	for rows.Next() {
		var seg audioSegmentSummary
		if err := rows.Scan(&seg.SegmentID, &seg.BlockIndex, &seg.SourceTextHash, &seg.Voice, &seg.Provider, &seg.Language, &seg.MediaKey, &seg.DurationMs, &seg.CreatedAt); err != nil {
			slog.Error("listAudioSegments scan", "error", err)
			continue
		}
		segments = append(segments, seg)
	}

	writeJSON(w, http.StatusOK, map[string]any{"segments": segments})
}

// ── Get single segment ─────────────────────────────────────────────────────────

func (s *Server) getAudioSegment(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chapterID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	segmentID, ok := parseUUIDParam(w, r, "segment_id")
	if !ok {
		return
	}
	if _, okBook, st := s.ensureOwnerBook(r.Context(), bookID, ownerID); !okBook {
		writeError(w, st, "BOOK_NOT_FOUND", "book not found")
		return
	}

	var seg audioSegmentDetail
	err := s.pool.QueryRow(r.Context(), `
		SELECT segment_id, block_index, source_text, source_text_hash, voice, provider, language, media_key, duration_ms, created_at
		FROM chapter_audio_segments
		WHERE segment_id = $1 AND chapter_id = $2
	`, segmentID, chapterID).Scan(
		&seg.SegmentID, &seg.BlockIndex, &seg.SourceText, &seg.SourceTextHash,
		&seg.Voice, &seg.Provider, &seg.Language, &seg.MediaKey, &seg.DurationMs, &seg.CreatedAt,
	)
	if err != nil {
		writeError(w, http.StatusNotFound, "AUDIO_NOT_FOUND", "audio segment not found")
		return
	}

	writeJSON(w, http.StatusOK, seg)
}

// ── Delete segments ────────────────────────────────────────────────────────────

func (s *Server) deleteAudioSegments(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chapterID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	if _, okBook, st := s.ensureOwnerBook(r.Context(), bookID, ownerID); !okBook {
		writeError(w, st, "BOOK_NOT_FOUND", "book not found")
		return
	}

	language := r.URL.Query().Get("language")
	voice := r.URL.Query().Get("voice")
	if language == "" || voice == "" {
		writeError(w, http.StatusBadRequest, "AUDIO_VALIDATION_ERROR", "language and voice query params required")
		return
	}

	// 1. Fetch media_keys for MinIO cleanup
	rows, err := s.pool.Query(r.Context(), `
		SELECT media_key FROM chapter_audio_segments
		WHERE chapter_id = $1 AND language = $2 AND voice = $3
	`, chapterID, language, voice)
	if err != nil {
		slog.Error("deleteAudioSegments fetch keys", "error", err)
		writeError(w, http.StatusInternalServerError, "AUDIO_QUERY_ERROR", "failed to query audio segments")
		return
	}
	var mediaKeys []string
	for rows.Next() {
		var key string
		if err := rows.Scan(&key); err == nil {
			mediaKeys = append(mediaKeys, key)
		}
	}
	rows.Close()

	// 2. Delete DB rows first
	tag, err := s.pool.Exec(r.Context(), `
		DELETE FROM chapter_audio_segments
		WHERE chapter_id = $1 AND language = $2 AND voice = $3
	`, chapterID, language, voice)
	if err != nil {
		slog.Error("deleteAudioSegments delete", "error", err)
		writeError(w, http.StatusInternalServerError, "AUDIO_DELETE_ERROR", "failed to delete audio segments")
		return
	}

	// 3. Best-effort MinIO cleanup
	if s.minio != nil {
		for _, key := range mediaKeys {
			if err := s.minio.RemoveObject(r.Context(), mediaBucket, key, minio.RemoveObjectOptions{}); err != nil {
				slog.Warn("deleteAudioSegments minio cleanup", "key", key, "error", err)
			}
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{"deleted": tag.RowsAffected()})
}

// ── Upload block audio ─────────────────────────────────────────────────────────

func (s *Server) uploadBlockAudio(w http.ResponseWriter, r *http.Request) {
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

	lifecycle, okBook, st := s.ensureOwnerBook(r.Context(), bookID, ownerID)
	if !okBook {
		writeError(w, st, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if lifecycle != "active" {
		writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "book not active")
		return
	}

	var exists bool
	_ = s.pool.QueryRow(r.Context(),
		`SELECT EXISTS(SELECT 1 FROM chapters WHERE id=$1 AND book_id=$2 AND lifecycle_state='active')`,
		chapterID, bookID).Scan(&exists)
	if !exists {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}

	if err := r.ParseMultipartForm(maxAudioSize); err != nil {
		writeError(w, http.StatusBadRequest, "AUDIO_TOO_LARGE", "file exceeds 20 MB limit")
		return
	}

	// block_index is required
	biStr := r.FormValue("block_index")
	if biStr == "" {
		writeError(w, http.StatusBadRequest, "AUDIO_VALIDATION_ERROR", "block_index is required")
		return
	}
	blockIndex, err := strconv.Atoi(biStr)
	if err != nil || blockIndex < 0 {
		writeError(w, http.StatusBadRequest, "AUDIO_VALIDATION_ERROR", "block_index must be a non-negative integer")
		return
	}

	f, fh, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "AUDIO_VALIDATION_ERROR", "file is required")
		return
	}
	defer f.Close()

	contentType := fh.Header.Get("Content-Type")
	ext, ok := allowedAudioTypes[contentType]
	if !ok {
		writeError(w, http.StatusUnsupportedMediaType, "UNSUPPORTED_MEDIA_TYPE",
			fmt.Sprintf("unsupported audio type %s; allowed: mp3, wav, ogg, webm, m4a", contentType))
		return
	}

	if fh.Size > maxAudioSize {
		writeError(w, http.StatusRequestEntityTooLarge, "AUDIO_TOO_LARGE", "file exceeds 20 MB limit")
		return
	}

	ctx := r.Context()
	if err := s.ensureMediaBucket(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "MEDIA_UPLOAD_FAILED", "storage init failed")
		return
	}

	objectKey := fmt.Sprintf("audio/%s/attached/%d_%s%s", chapterID, blockIndex, uuid.New().String(), ext)

	_, err = s.minio.PutObject(ctx, mediaBucket, objectKey, io.LimitReader(f, maxAudioSize), fh.Size,
		minio.PutObjectOptions{ContentType: contentType})
	if err != nil {
		slog.Error("uploadBlockAudio minio put", "error", err)
		writeError(w, http.StatusInternalServerError, "MEDIA_UPLOAD_FAILED", "upload failed")
		return
	}

	subtitle := r.FormValue("subtitle")

	writeJSON(w, http.StatusCreated, map[string]any{
		"audio_url":    s.mediaURL(objectKey),
		"media_key":    objectKey,
		"duration_ms":  0,
		"size_bytes":   fh.Size,
		"content_type": contentType,
		"subtitle":     subtitle,
	})
}
