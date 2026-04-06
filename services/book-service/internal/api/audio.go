package api

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
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

// ── Generate TTS audio ─────────────────────────────────────────────────────────

var ttsClient = &http.Client{Timeout: 120 * time.Second}

func textHash(s string) string {
	h := sha256.Sum256([]byte(s))
	return hex.EncodeToString(h[:])
}

func (s *Server) generateAudio(w http.ResponseWriter, r *http.Request) {
	if s.minio == nil {
		writeError(w, http.StatusServiceUnavailable, "MEDIA_UNAVAILABLE", "media storage not configured")
		return
	}
	if s.cfg.ProviderRegistryURL == "" || s.cfg.InternalServiceToken == "" {
		writeError(w, http.StatusServiceUnavailable, "GENERATION_UNAVAILABLE", "AI generation not configured")
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
	chapterID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
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

	var body struct {
		Language    string `json:"language"`
		Voice       string `json:"voice"`
		Provider    string `json:"provider"`
		ModelSource string `json:"model_source"`
		ModelRef    string `json:"model_ref"`
		Blocks      []struct {
			Index int    `json:"index"`
			Text  string `json:"text"`
		} `json:"blocks"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "AUDIO_VALIDATION_ERROR", "invalid JSON")
		return
	}
	if body.Language == "" || body.Voice == "" || body.ModelRef == "" || len(body.Blocks) == 0 {
		writeError(w, http.StatusBadRequest, "AUDIO_VALIDATION_ERROR", "language, voice, model_ref, and blocks are required")
		return
	}
	if body.ModelSource == "" {
		body.ModelSource = "user_model"
	}
	if body.Provider == "" {
		body.Provider = "openai"
	}

	ctx := r.Context()

	// 1. Resolve provider credentials
	credURL := fmt.Sprintf("%s/internal/credentials/%s/%s?user_id=%s",
		s.cfg.ProviderRegistryURL, body.ModelSource, body.ModelRef, ownerID)
	credReq, _ := http.NewRequestWithContext(ctx, "GET", credURL, nil)
	credReq.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	credResp, err := internalClient.Do(credReq)
	if err != nil {
		writeError(w, http.StatusBadGateway, "PROVIDER_ERROR", "failed to reach provider registry")
		return
	}
	defer credResp.Body.Close()
	if credResp.StatusCode == http.StatusNotFound {
		writeError(w, http.StatusPaymentRequired, "NO_PROVIDER", "no active AI provider configured")
		return
	}
	if credResp.StatusCode != http.StatusOK {
		writeError(w, http.StatusBadGateway, "PROVIDER_ERROR", "provider registry error")
		return
	}

	var creds struct {
		ProviderKind      string `json:"provider_kind"`
		ProviderModelName string `json:"provider_model_name"`
		BaseURL           string `json:"base_url"`
		APIKey            string `json:"api_key"`
	}
	if err := json.NewDecoder(credResp.Body).Decode(&creds); err != nil {
		writeError(w, http.StatusBadGateway, "PROVIDER_ERROR", "invalid provider response")
		return
	}

	baseURL := strings.TrimRight(creds.BaseURL, "/")
	if baseURL == "" {
		baseURL = "https://api.openai.com"
	}

	// 2. Ensure MinIO bucket
	if err := s.ensureMediaBucket(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "MEDIA_UPLOAD_FAILED", "storage init failed")
		return
	}

	// 3. Delete existing segments for this (chapter, language, voice)
	var oldKeys []string
	rows, err := s.pool.Query(ctx,
		`SELECT media_key FROM chapter_audio_segments WHERE chapter_id=$1 AND language=$2 AND voice=$3`,
		chapterID, body.Language, body.Voice)
	if err == nil {
		for rows.Next() {
			var k string
			if rows.Scan(&k) == nil {
				oldKeys = append(oldKeys, k)
			}
		}
		rows.Close()
	}
	_, _ = s.pool.Exec(ctx,
		`DELETE FROM chapter_audio_segments WHERE chapter_id=$1 AND language=$2 AND voice=$3`,
		chapterID, body.Language, body.Voice)
	for _, k := range oldKeys {
		_ = s.minio.RemoveObject(ctx, mediaBucket, k, minio.RemoveObjectOptions{})
	}

	// 4. Generate TTS for each block
	type segResult struct {
		BlockIndex int    `json:"block_index"`
		MediaURL   string `json:"media_url"`
		MediaKey   string `json:"media_key"`
		DurationMs int    `json:"duration_ms"`
	}
	type segError struct {
		BlockIndex int    `json:"block_index"`
		Error      string `json:"error"`
	}

	var segments []segResult
	var genErrors []segError
	totalChars := 0

	for _, block := range body.Blocks {
		if strings.TrimSpace(block.Text) == "" {
			continue
		}

		// Call OpenAI-compatible TTS API
		ttsPayload, _ := json.Marshal(map[string]any{
			"model":           creds.ProviderModelName,
			"voice":           body.Voice,
			"input":           block.Text,
			"response_format": "mp3",
		})
		ttsReq, _ := http.NewRequestWithContext(ctx, "POST", baseURL+"/v1/audio/speech",
			bytes.NewReader(ttsPayload))
		ttsReq.Header.Set("Authorization", "Bearer "+creds.APIKey)
		ttsReq.Header.Set("Content-Type", "application/json")

		ttsResp, err := ttsClient.Do(ttsReq)
		if err != nil {
			slog.Warn("generateAudio TTS call failed", "block_index", block.Index, "error", err)
			genErrors = append(genErrors, segError{BlockIndex: block.Index, Error: "TTS request failed"})
			continue
		}

		if ttsResp.StatusCode != http.StatusOK {
			respBody, _ := io.ReadAll(io.LimitReader(ttsResp.Body, 2048))
			ttsResp.Body.Close()
			slog.Warn("generateAudio TTS error", "block_index", block.Index, "status", ttsResp.StatusCode, "body", string(respBody))
			genErrors = append(genErrors, segError{
				BlockIndex: block.Index,
				Error:      fmt.Sprintf("TTS API returned %d", ttsResp.StatusCode),
			})
			continue
		}

		// Upload to MinIO
		objectKey := fmt.Sprintf("audio/%s/tts/%s_%s_%d_%s.mp3",
			chapterID, body.Language, body.Voice, block.Index, uuid.New().String())

		uploadInfo, err := s.minio.PutObject(ctx, mediaBucket, objectKey, ttsResp.Body, -1,
			minio.PutObjectOptions{ContentType: "audio/mpeg"})
		ttsResp.Body.Close()
		if err != nil {
			slog.Error("generateAudio minio upload", "block_index", block.Index, "error", err)
			genErrors = append(genErrors, segError{BlockIndex: block.Index, Error: "failed to store audio"})
			continue
		}

		// Insert DB row
		hash := textHash(block.Text)
		_, err = s.pool.Exec(ctx, `
			INSERT INTO chapter_audio_segments(chapter_id, block_index, source_text, source_text_hash, voice, provider, language, media_key, duration_ms)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		`, chapterID, block.Index, block.Text, hash, body.Voice, body.Provider, body.Language, objectKey, 0)
		if err != nil {
			slog.Error("generateAudio db insert", "block_index", block.Index, "error", err)
			// Clean up the uploaded object
			_ = s.minio.RemoveObject(ctx, mediaBucket, objectKey, minio.RemoveObjectOptions{})
			genErrors = append(genErrors, segError{BlockIndex: block.Index, Error: "failed to save segment record"})
			continue
		}

		totalChars += len(block.Text)
		segments = append(segments, segResult{
			BlockIndex: block.Index,
			MediaURL:   s.mediaURL(objectKey),
			MediaKey:   objectKey,
			DurationMs: 0,
		})

		_ = uploadInfo // used by PutObject
	}

	// 5. Best-effort usage billing
	if s.cfg.UsageBillingServiceURL != "" && len(segments) > 0 {
		modelRefUUID, _ := uuid.Parse(body.ModelRef)
		usagePayload, _ := json.Marshal(map[string]any{
			"request_id":    uuid.New(),
			"owner_user_id": ownerID,
			"provider_kind": creds.ProviderKind,
			"model_source":  body.ModelSource,
			"model_ref":     modelRefUUID,
			"input_tokens":  totalChars, // TTS bills by characters, map to "tokens" field
			"output_tokens": 0,
			"request_status": "success",
			"purpose":       "tts_generation",
		})
		billingURL := fmt.Sprintf("%s/internal/model-billing/record",
			strings.TrimRight(s.cfg.UsageBillingServiceURL, "/"))
		billingReq, _ := http.NewRequestWithContext(ctx, "POST", billingURL, bytes.NewReader(usagePayload))
		billingReq.Header.Set("Content-Type", "application/json")
		billingReq.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
		if resp, err := internalClient.Do(billingReq); err != nil {
			slog.Warn("generateAudio billing failed", "error", err)
		} else {
			resp.Body.Close()
		}
	}

	if segments == nil {
		segments = make([]segResult, 0)
	}
	if genErrors == nil {
		genErrors = make([]segError, 0)
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"segments": segments,
		"errors":   genErrors,
	})
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
