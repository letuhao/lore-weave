package api

import (
	"bytes"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
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

	"github.com/loreweave/llmgw"
	"github.com/loreweave/observability"
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

// Phase 6c — traced transport so the outbound TTS call carries a W3C
// traceparent + emits a CLIENT span.
var ttsClient = &http.Client{Timeout: 120 * time.Second, Transport: observability.HTTPTransport(nil)}

func textHash(s string) string {
	h := sha256.Sum256([]byte(s))
	return hex.EncodeToString(h[:])
}

// writeAudioGenError maps a typed *llmgw.Error (potentially wrapped) to
// HTTP response. Mirrors writeImageGenError from Phase 5e-β.1.
//
// /review-impl(DESIGN) MED#4 — ErrAuthFailed → 402 NO_PROVIDER (BYOK
// key revoked is the dominant case); ErrRateLimited surfaces Retry-After
// header per (DESIGN) MED#4 + (BUILD) MED#4 from 5e-β.1.
func writeAudioGenError(w http.ResponseWriter, err error) {
	var llmErr *llmgw.Error
	_ = errors.As(err, &llmErr)

	switch {
	case errors.Is(err, llmgw.ErrQuotaExceeded):
		writeError(w, http.StatusPaymentRequired, "NO_PROVIDER", "AI provider quota exceeded")
	case errors.Is(err, llmgw.ErrModelNotFound):
		writeError(w, http.StatusPaymentRequired, "NO_PROVIDER", "no active AI provider configured")
	case errors.Is(err, llmgw.ErrInvalidRequest):
		writeError(w, http.StatusBadRequest, "AUDIO_VALIDATION_ERROR", err.Error())
	case errors.Is(err, llmgw.ErrRateLimited):
		if llmErr != nil && llmErr.RetryAfterS > 0 {
			w.Header().Set("Retry-After", strconv.Itoa(int(llmErr.RetryAfterS)))
		}
		writeError(w, http.StatusTooManyRequests, "RATE_LIMITED", "AI provider rate-limit")
	case errors.Is(err, llmgw.ErrAudioGenerationFailed):
		writeError(w, http.StatusBadGateway, "GENERATION_FAILED", "AI audio generation failed (retryable)")
	case errors.Is(err, llmgw.ErrGatewayStorage):
		// /review-impl(BUILD round 3) C#1 — distinct surface. TTS
		// succeeded; gateway storage failed. DO NOT auto-retry (would
		// double-bill BYOK). User should refresh + check if any segments
		// were preserved before manually re-submitting.
		writeError(w, http.StatusBadGateway, "GENERATION_STORAGE_FAILED",
			"TTS succeeded but gateway storage failed; check status before retrying to avoid double-bill")
	case errors.Is(err, llmgw.ErrUpstream):
		writeError(w, http.StatusBadGateway, "GENERATION_FAILED", "AI provider upstream error")
	case errors.Is(err, llmgw.ErrJobTerminal):
		writeError(w, http.StatusGatewayTimeout, "GENERATION_CANCELLED", "AI generation cancelled")
	case errors.Is(err, llmgw.ErrAuthFailed):
		writeError(w, http.StatusPaymentRequired, "NO_PROVIDER", "AI provider authentication failed (check API key)")
	default:
		writeError(w, http.StatusBadGateway, "GENERATION_FAILED", "AI audio generation failed")
	}
}

func (s *Server) generateAudio(w http.ResponseWriter, r *http.Request) {
	if s.minio == nil {
		writeError(w, http.StatusServiceUnavailable, "MEDIA_UNAVAILABLE", "media storage not configured")
		return
	}
	// Phase 5e-β.2 — unified gateway audio_gen replaces direct credential
	// resolve + per-block TTS POST. s.audioGenClient is nil only when
	// LLM_GATEWAY_INTERNAL_URL or INTERNAL_SERVICE_TOKEN missing at startup.
	if s.audioGenClient == nil {
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

	// Result + error envelope types (same shape as before).
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

	// Filter non-empty blocks BEFORE submit; track original indices so
	// result.Data[i] can be mapped back via inputs[i].idx
	// (/review-impl(DESIGN) MED#5 — adapter preserves input order).
	type indexedText struct {
		idx  int
		text string
	}
	var inputs []indexedText
	for _, b := range body.Blocks {
		if strings.TrimSpace(b.Text) != "" {
			inputs = append(inputs, indexedText{idx: b.Index, text: b.Text})
		}
	}
	if len(inputs) == 0 {
		writeJSON(w, http.StatusOK, map[string]any{
			"segments": []segResult{},
			"errors":   []segError{},
		})
		return
	}

	// Ensure MinIO bucket.
	if err := s.ensureMediaBucket(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "MEDIA_UPLOAD_FAILED", "storage init failed")
		return
	}

	// /review-impl(BUILD) H#2 — defer the prior-segment delete until
	// AFTER the SDK call returns successfully. If the gateway returns a
	// contract violation (len(result.Data) != len(inputs)) or a transient
	// upstream error, we DON'T want to have already nuked the user's
	// prior audio.

	// Single batch SDK call. Caller-side b64_json mode — gateway returns
	// inline base64; we decode + upload to our loreweave-media bucket
	// (uniform with non-TTS audio upload path).
	texts := make([]string, len(inputs))
	for i, it := range inputs {
		texts[i] = it.text
	}
	voice := body.Voice
	format := "mp3"
	responseFormat := "b64_json"
	result, err := s.audioGenClient.GenerateAudio(ctx, llmgw.GenerateAudioRequest{
		Texts:          texts,
		ModelSource:    llmgw.ModelSource(body.ModelSource),
		ModelRef:       body.ModelRef,
		Voice:          &voice,
		Format:         &format,
		ResponseFormat: &responseFormat,
		UserID:         ownerID.String(),
	})
	if err != nil {
		writeAudioGenError(w, err)
		return
	}
	if len(result.Data) != len(inputs) {
		// /review-impl(BUILD) H#2 — log contract violation explicitly;
		// 502 GENERATION_FAILED is the closest user-facing surface but
		// the underlying issue is an adapter-or-worker bug, not AI failure.
		slog.Error("generateAudio: gateway contract violation",
			"got_results", len(result.Data), "want_results", len(inputs))
		writeError(w, http.StatusBadGateway, "GENERATION_FAILED",
			fmt.Sprintf("audio_gen returned %d results for %d inputs", len(result.Data), len(inputs)))
		return
	}

	// /review-impl(BUILD round 3) H#1 — DO NOT delete old segments yet.
	// Stage all new audio to MinIO first; only after ALL successful
	// inserts do we delete the prior set. If a per-item op fails,
	// user keeps their prior audio AND sees error details for the
	// failing blocks. Previously: SDK-success → DELETE old → per-item
	// loop → some fail → user has prior set GONE + new partial set.
	// Now: per-item loop → all succeed → DELETE old. Per-item failures
	// leave new partial set + old set both visible; FE can present a
	// "regenerate failed blocks" UX.
	//
	// Trade-off: brief window with BOTH old + new segments in DB.
	// chapter_audio_segments may have duplicates per block_index (no
	// unique constraint blocks this). Acceptable since the DELETE
	// runs immediately after per-item loop on success path.

	// Decode base64 + upload + insert DB row per block, preserving order.
	// Use timestamp-suffixed keys so new uploads don't collide with old.
	var segments []segResult
	var genErrors []segError
	for i, item := range result.Data {
		if item.B64JSON == "" {
			genErrors = append(genErrors, segError{BlockIndex: inputs[i].idx, Error: "empty audio payload"})
			continue
		}
		audioBytes, err := base64.StdEncoding.DecodeString(item.B64JSON)
		if err != nil {
			slog.Error("generateAudio b64 decode", "block_index", inputs[i].idx, "error", err)
			genErrors = append(genErrors, segError{BlockIndex: inputs[i].idx, Error: "audio decode failed"})
			continue
		}
		objectKey := fmt.Sprintf("audio/%s/tts/%s_%s_%d_%s.mp3",
			chapterID, body.Language, body.Voice, inputs[i].idx, uuid.New().String())
		_, err = s.minio.PutObject(ctx, mediaBucket, objectKey,
			bytes.NewReader(audioBytes), int64(len(audioBytes)),
			minio.PutObjectOptions{ContentType: "audio/mpeg"})
		if err != nil {
			slog.Error("generateAudio minio upload", "block_index", inputs[i].idx, "error", err)
			genErrors = append(genErrors, segError{BlockIndex: inputs[i].idx, Error: "failed to store audio"})
			continue
		}
		hash := textHash(inputs[i].text)
		_, err = s.pool.Exec(ctx, `
			INSERT INTO chapter_audio_segments(chapter_id, block_index, source_text, source_text_hash, voice, provider, language, media_key, duration_ms)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		`, chapterID, inputs[i].idx, inputs[i].text, hash, body.Voice, body.Provider, body.Language, objectKey, item.DurationMs)
		if err != nil {
			slog.Error("generateAudio db insert", "block_index", inputs[i].idx, "error", err)
			_ = s.minio.RemoveObject(ctx, mediaBucket, objectKey, minio.RemoveObjectOptions{})
			genErrors = append(genErrors, segError{BlockIndex: inputs[i].idx, Error: "failed to save segment record"})
			continue
		}
		// Inserted successfully; tracking for response below. Old-segment
		// cleanup runs AFTER this loop only if no failures occurred.
		segments = append(segments, segResult{
			BlockIndex: inputs[i].idx,
			MediaURL:   s.mediaURL(objectKey),
			MediaKey:   objectKey,
			DurationMs: item.DurationMs,
		})
	}

	// /review-impl(BUILD round 3) H#1 — Only delete old segments if ALL
	// new items succeeded. On partial failure, leave old set intact so
	// user has fallback content; FE can offer "retry failed blocks" UX.
	if len(genErrors) == 0 && len(segments) > 0 {
		newKeys := make([]string, len(segments))
		for i, s := range segments {
			newKeys[i] = s.MediaKey
		}
		var oldKeys []string
		rows, err := s.pool.Query(ctx,
			`SELECT media_key FROM chapter_audio_segments WHERE chapter_id=$1 AND language=$2 AND voice=$3 AND media_key != ALL($4::text[])`,
			chapterID, body.Language, body.Voice, newKeys)
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
			`DELETE FROM chapter_audio_segments WHERE chapter_id=$1 AND language=$2 AND voice=$3 AND media_key != ALL($4::text[])`,
			chapterID, body.Language, body.Voice, newKeys)
		for _, k := range oldKeys {
			_ = s.minio.RemoveObject(ctx, mediaBucket, k, minio.RemoveObjectOptions{})
		}
	}

	// Best-effort usage billing — provider_kind="" per 5e-α QC MED#1.
	if s.cfg.UsageBillingServiceURL != "" && len(segments) > 0 {
		totalChars := 0
		for _, it := range inputs {
			totalChars += len(it.text)
		}
		modelRefUUID, _ := uuid.Parse(body.ModelRef)
		usagePayload, _ := json.Marshal(map[string]any{
			"request_id":     uuid.New(),
			"owner_user_id":  ownerID,
			"provider_kind":  "",
			"model_source":   body.ModelSource,
			"model_ref":      modelRefUUID,
			"input_tokens":   totalChars,
			"output_tokens":  0,
			"request_status": "success",
			"purpose":        "tts_generation",
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
