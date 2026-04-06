package api

import (
	"log/slog"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/minio/minio-go/v7"
)

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
