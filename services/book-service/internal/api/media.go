package api

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/minio/minio-go/v7"

	"github.com/loreweave/llmgw"
	"github.com/loreweave/observability"
)

const (
	maxImageSize = 10 << 20  // 10 MB
	maxVideoSize = 100 << 20 // 100 MB
	mediaBucket  = "loreweave-media"
)

var allowedMediaTypes = map[string]string{
	"image/png":  ".png",
	"image/jpeg": ".jpg",
	"image/gif":  ".gif",
	"image/webp": ".webp",
	"video/mp4":  ".mp4",
	"video/webm": ".webm",
}

// ── Upload ──────────────────────────────────────────────────────────────────

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

	lifecycle, okBook, status := s.ensureOwnerBook(r.Context(), bookID, ownerID)
	if !okBook {
		writeError(w, status, "BOOK_NOT_FOUND", "book not found")
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

	if err := r.ParseMultipartForm(maxVideoSize); err != nil {
		writeError(w, http.StatusBadRequest, "MEDIA_TOO_LARGE", "file exceeds size limit")
		return
	}
	f, fh, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "file is required")
		return
	}
	defer f.Close()

	contentType := fh.Header.Get("Content-Type")
	ext, ok := allowedMediaTypes[contentType]
	if !ok {
		writeError(w, http.StatusUnsupportedMediaType, "UNSUPPORTED_MEDIA_TYPE",
			fmt.Sprintf("unsupported type %s; allowed: png, jpg, gif, webp, mp4, webm", contentType))
		return
	}

	isVideo := contentType == "video/mp4" || contentType == "video/webm"
	sizeLimit := int64(maxImageSize)
	if isVideo {
		sizeLimit = maxVideoSize
	}
	if fh.Size > sizeLimit {
		writeError(w, http.StatusRequestEntityTooLarge, "MEDIA_TOO_LARGE",
			fmt.Sprintf("file exceeds %d MB limit", sizeLimit/(1<<20)))
		return
	}

	ctx := r.Context()
	if err := s.ensureMediaBucket(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "MEDIA_UPLOAD_FAILED", "storage init failed")
		return
	}

	// Optional block_id for versioned path
	blockID := r.FormValue("block_id")

	// Determine object key and version
	var objectKey string
	var versionNum int
	if blockID != "" {
		// Versioned path: get next version number
		_ = s.pool.QueryRow(ctx,
			`SELECT COALESCE(MAX(version), 0) FROM block_media_versions WHERE chapter_id=$1 AND block_id=$2`,
			chapterID, blockID).Scan(&versionNum)
		versionNum++
		objectKey = fmt.Sprintf("books/%s/chapters/%s/%s/v%d%s", bookID, chapterID, blockID, versionNum, ext)
	} else {
		// Legacy unversioned path
		objectKey = fmt.Sprintf("books/%s/chapters/%s/%s%s", bookID, chapterID, uuid.New().String(), ext)
		versionNum = 1
	}

	uploadInfo, err := s.minio.PutObject(ctx, mediaBucket, objectKey, io.LimitReader(f, sizeLimit), fh.Size,
		minio.PutObjectOptions{ContentType: contentType})
	if err != nil {
		writeError(w, http.StatusInternalServerError, "MEDIA_UPLOAD_FAILED", "upload failed")
		return
	}

	mediaURL := s.mediaURL(objectKey)

	// Auto-create version record if block_id provided
	var versionID *string
	if blockID != "" {
		var vid string
		err = s.pool.QueryRow(ctx, `
			INSERT INTO block_media_versions(chapter_id, block_id, version, action, changes, media_ref, content_type, size_bytes)
			VALUES($1, $2, $3, 'upload', ARRAY['media'], $4, $5, $6)
			RETURNING id`,
			chapterID, blockID, versionNum, objectKey, contentType, uploadInfo.Size,
		).Scan(&vid)
		if err == nil {
			versionID = &vid
		}
	}

	originalName := fh.Filename
	if originalName == "" {
		originalName = filepath.Base(objectKey)
	}

	resp := map[string]any{
		"url":          mediaURL,
		"object_key":   objectKey,
		"filename":     originalName,
		"size":         uploadInfo.Size,
		"content_type": contentType,
		"version":      versionNum,
	}
	if versionID != nil {
		resp["version_id"] = *versionID
	}
	writeJSON(w, http.StatusCreated, resp)
}

// ── List versions ───────────────────────────────────────────────────────────

func (s *Server) listMediaVersions(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	if _, okBook, st := s.ensureOwnerBook(r.Context(), bookID, ownerID); !okBook {
		writeError(w, st, "BOOK_NOT_FOUND", "book not found")
		return
	}
	chapterID := chi.URLParam(r, "chapter_id")
	blockID := r.URL.Query().Get("block_id")
	if blockID == "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "block_id query param required")
		return
	}

	rows, err := s.pool.Query(r.Context(), `
		SELECT id, block_id, version, action, changes, media_ref, prompt_snapshot, caption_snapshot,
		       ai_model, content_type, size_bytes, created_at
		FROM block_media_versions
		WHERE chapter_id=$1 AND block_id=$2
		ORDER BY version DESC`, chapterID, blockID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "query failed")
		return
	}
	defer rows.Close()

	items := []map[string]any{}
	for rows.Next() {
		var id, bid, action string
		var version int
		var changes []string
		var mediaRef, promptSnap, captionSnap, aiModel, ct *string
		var sizeBytes *int64
		var createdAt time.Time
		if err := rows.Scan(&id, &bid, &version, &action, &changes, &mediaRef, &promptSnap, &captionSnap,
			&aiModel, &ct, &sizeBytes, &createdAt); err != nil {
			continue
		}
		item := map[string]any{
			"id":               id,
			"block_id":         bid,
			"version":          version,
			"action":           action,
			"changes":          changes,
			"media_ref":        mediaRef,
			"prompt_snapshot":  promptSnap,
			"caption_snapshot": captionSnap,
			"ai_model":         aiModel,
			"content_type":     ct,
			"size_bytes":       sizeBytes,
			"created_at":       createdAt,
		}
		if mediaRef != nil && *mediaRef != "" {
			item["media_url"] = s.mediaURL(*mediaRef)
		}
		items = append(items, item)
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

// ── Create version (manual — prompt/caption changes) ────────────────────────

func (s *Server) createMediaVersion(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	if _, okBook, st := s.ensureOwnerBook(r.Context(), bookID, ownerID); !okBook {
		writeError(w, st, "BOOK_NOT_FOUND", "book not found")
		return
	}
	chapterID := chi.URLParam(r, "chapter_id")

	var body struct {
		BlockID         string   `json:"block_id"`
		Action          string   `json:"action"`
		Changes         []string `json:"changes"`
		PromptSnapshot  string   `json:"prompt_snapshot"`
		CaptionSnapshot string   `json:"caption_snapshot"`
		MediaRef        string   `json:"media_ref"`
		AIModel         string   `json:"ai_model"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid JSON")
		return
	}
	if body.BlockID == "" || body.Action == "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "block_id and action required")
		return
	}

	ctx := r.Context()
	var nextVersion int
	_ = s.pool.QueryRow(ctx,
		`SELECT COALESCE(MAX(version), 0) + 1 FROM block_media_versions WHERE chapter_id=$1 AND block_id=$2`,
		chapterID, body.BlockID).Scan(&nextVersion)

	var id string
	var createdAt time.Time
	err := s.pool.QueryRow(ctx, `
		INSERT INTO block_media_versions(chapter_id, block_id, version, action, changes, media_ref, prompt_snapshot, caption_snapshot, ai_model)
		VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9)
		RETURNING id, created_at`,
		chapterID, body.BlockID, nextVersion, body.Action, body.Changes,
		nilIfEmpty(body.MediaRef), body.PromptSnapshot, body.CaptionSnapshot, nilIfEmpty(body.AIModel),
	).Scan(&id, &createdAt)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "insert failed")
		return
	}

	writeJSON(w, http.StatusCreated, map[string]any{
		"id":         id,
		"version":    nextVersion,
		"action":     body.Action,
		"changes":    body.Changes,
		"created_at": createdAt,
	})
}

// ── Delete version ──────────────────────────────────────────────────────────

func (s *Server) deleteMediaVersion(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	if _, okBook, st := s.ensureOwnerBook(r.Context(), bookID, ownerID); !okBook {
		writeError(w, st, "BOOK_NOT_FOUND", "book not found")
		return
	}
	versionID := chi.URLParam(r, "version_id")
	chapterID := chi.URLParam(r, "chapter_id")

	// Get media_ref before deleting (to clean up MinIO)
	var mediaRef *string
	_ = s.pool.QueryRow(r.Context(),
		`SELECT media_ref FROM block_media_versions WHERE id=$1 AND chapter_id=$2`, versionID, chapterID,
	).Scan(&mediaRef)

	tag, err := s.pool.Exec(r.Context(),
		`DELETE FROM block_media_versions WHERE id=$1 AND chapter_id=$2`, versionID, chapterID)
	if err != nil || tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "VERSION_NOT_FOUND", "version not found")
		return
	}

	// Best-effort cleanup of MinIO object
	if mediaRef != nil && *mediaRef != "" && s.minio != nil {
		_ = s.minio.RemoveObject(r.Context(), mediaBucket, *mediaRef, minio.RemoveObjectOptions{})
	}

	w.WriteHeader(http.StatusNoContent)
}

// writeImageGenError maps a typed *llmgw.Error (potentially wrapped) to
// the HTTP response. Extracted from generateChapterMedia so it can be
// unit-tested without the surrounding DB/MinIO/JWT fixtures.
//
// Per /review-impl(DESIGN) MED#2 — ErrImageGenerationFailed and
// ErrUpstream are kept SEPARATE cases (same HTTP status today but may
// diverge). Per MED#3 — uses errors.As so a future fmt.Errorf wrap
// doesn't panic. Per MED#4 — surfaces Retry-After response header
// when the gateway reported retry_after_s for rate-limit cases.
func writeImageGenError(w http.ResponseWriter, err error) {
	var llmErr *llmgw.Error
	_ = errors.As(err, &llmErr)

	switch {
	case errors.Is(err, llmgw.ErrImageContentPolicy):
		msg := "Content policy violation"
		if llmErr != nil && llmErr.Message != "" {
			msg = "Content policy: " + llmErr.Message
		}
		writeError(w, http.StatusBadRequest, "CONTENT_POLICY", msg)
	case errors.Is(err, llmgw.ErrQuotaExceeded):
		writeError(w, http.StatusPaymentRequired, "NO_PROVIDER", "AI provider quota exceeded")
	case errors.Is(err, llmgw.ErrModelNotFound):
		writeError(w, http.StatusPaymentRequired, "NO_PROVIDER", "no active AI provider configured")
	case errors.Is(err, llmgw.ErrInvalidRequest):
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", err.Error())
	case errors.Is(err, llmgw.ErrRateLimited):
		if llmErr != nil && llmErr.RetryAfterS > 0 {
			w.Header().Set("Retry-After", strconv.Itoa(int(llmErr.RetryAfterS)))
		}
		writeError(w, http.StatusTooManyRequests, "RATE_LIMITED", "AI provider rate-limit")
	case errors.Is(err, llmgw.ErrImageGenerationFailed):
		writeError(w, http.StatusBadGateway, "GENERATION_FAILED", "AI image generation failed (retryable)")
	case errors.Is(err, llmgw.ErrUpstream):
		writeError(w, http.StatusBadGateway, "GENERATION_FAILED", "AI provider upstream error")
	case errors.Is(err, llmgw.ErrJobTerminal):
		writeError(w, http.StatusGatewayTimeout, "GENERATION_CANCELLED", "AI generation cancelled")
	case errors.Is(err, llmgw.ErrAuthFailed):
		// Upstream BYOK key revoked / wrong API key surfaces as
		// LLM_AUTH_FAILED from the gateway's worker (worker_image.go
		// classifies 401/403 from OpenAI/upstream as terminal auth-failed).
		// Treat as "user needs to configure a working provider" — same
		// surface as ErrModelNotFound. (/review-impl(BUILD) MED#2.)
		writeError(w, http.StatusPaymentRequired, "NO_PROVIDER", "AI provider authentication failed (check API key)")
	default:
		writeError(w, http.StatusBadGateway, "GENERATION_FAILED", "AI image generation failed")
	}
}

// ── AI Image Generation ─────────────────────────────────────────────────────

func (s *Server) generateChapterMedia(w http.ResponseWriter, r *http.Request) {
	if s.minio == nil {
		writeError(w, http.StatusServiceUnavailable, "MEDIA_UNAVAILABLE", "media storage not configured")
		return
	}
	// Phase 5e-β.1 — unified gateway SDK replaces direct provider-registry
	// credential resolve + direct image-generation POST. s.llmgw is
	// constructed in NewServer; nil only when LLM_GATEWAY_INTERNAL_URL or
	// INTERNAL_SERVICE_TOKEN was missing at startup (config.Load enforces).
	if s.llmgw == nil {
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
	chapterID := chi.URLParam(r, "chapter_id")

	lifecycle, okBook, status := s.ensureOwnerBook(r.Context(), bookID, ownerID)
	if !okBook {
		writeError(w, status, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if lifecycle != "active" {
		writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "book not active")
		return
	}

	var body struct {
		BlockID     string `json:"block_id"`
		Prompt      string `json:"prompt"`
		ModelSource string `json:"model_source"` // "user_model" or "platform_model"
		ModelRef    string `json:"model_ref"`    // model UUID
		Size        string `json:"size"`         // "1024x1024" default (caller-side)
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid JSON")
		return
	}
	if body.BlockID == "" || body.Prompt == "" || body.ModelRef == "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "block_id, prompt, and model_ref required")
		return
	}
	if body.ModelSource == "" {
		body.ModelSource = "user_model"
	}
	if body.Size == "" {
		body.Size = "1024x1024"
	}

	ctx := r.Context()

	// 1+2. SDK call — replaces credential resolve + direct POST.
	size := body.Size
	result, err := s.llmgw.GenerateImage(ctx, llmgw.GenerateImageRequest{
		Prompt:      body.Prompt,
		ModelSource: llmgw.ModelSource(body.ModelSource),
		ModelRef:    body.ModelRef,
		Size:        &size,
		UserID:      ownerID.String(),
	})
	if err != nil {
		writeImageGenError(w, err)
		return
	}
	// SDK's decodeImageGenResult already rejects empty Data with
	// ErrUpstream (caught by writeImageGenError above), so only the
	// URL-mode-specific case is reachable here. This caller always
	// uses URL mode (no ResponseFormat override); if a future caller
	// switches to b64_json, this check needs the B64JSON path added.
	// (/review-impl(BUILD) MED#3.)
	if result.Data[0].URL == "" {
		writeError(w, http.StatusBadGateway, "GENERATION_FAILED", "AI provider returned image without URL")
		return
	}

	// 3. Download the generated image. Use a dedicated http.Client with a
	// 120s wall-clock cap for the download (unrelated to the SDK polling
	// loop which has no Timeout).
	dlReq, _ := http.NewRequestWithContext(ctx, "GET", result.Data[0].URL, nil)
	// Phase 6c — traced transport so the outbound download carries a W3C
	// traceparent + emits a CLIENT span.
	dlClient := &http.Client{Timeout: 120 * time.Second, Transport: observability.HTTPTransport(nil)}
	imgResp, err := dlClient.Do(dlReq)
	if err != nil || imgResp.StatusCode != http.StatusOK {
		writeError(w, http.StatusBadGateway, "GENERATION_FAILED", "failed to download generated image")
		return
	}
	defer imgResp.Body.Close()

	contentType := imgResp.Header.Get("Content-Type")
	ext := ".png"
	if e, ok := allowedMediaTypes[contentType]; ok {
		ext = e
	}

	// 4. Ensure bucket + upload to MinIO
	if err := s.ensureMediaBucket(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "MEDIA_UPLOAD_FAILED", "storage init failed")
		return
	}

	var nextVersion int
	_ = s.pool.QueryRow(ctx,
		`SELECT COALESCE(MAX(version), 0) + 1 FROM block_media_versions WHERE chapter_id=$1 AND block_id=$2`,
		chapterID, body.BlockID).Scan(&nextVersion)

	objectKey := fmt.Sprintf("books/%s/chapters/%s/%s/v%d%s", bookID, chapterID, body.BlockID, nextVersion, ext)
	uploadInfo, err := s.minio.PutObject(ctx, mediaBucket, objectKey, imgResp.Body, -1,
		minio.PutObjectOptions{ContentType: contentType})
	if err != nil {
		writeError(w, http.StatusInternalServerError, "MEDIA_UPLOAD_FAILED", "failed to store generated image")
		return
	}

	// 5. Create version record. Phase 5e-β.1 — `ai_model` is now stored
	// as the empty string for new rows because the SDK does not surface
	// the human-readable upstream model name (it lives gateway-side).
	// Legacy rows retain their human names (e.g. "dall-e-3").
	// Frontend's `{v.ai_model && ...}` conditional render naturally
	// hides the model-name line for empty values, so new rows display
	// without the model annotation rather than showing a raw UUID.
	// Tracked as deferred D-PHASE5E-BETA1-IMAGE-PROVIDER-MODEL-NAME-IN-RESULT
	// for a future cycle that extends the SDK's ImageGenResult to expose
	// provider_model_name from the gateway.
	var versionID string
	_ = s.pool.QueryRow(ctx, `
		INSERT INTO block_media_versions(chapter_id, block_id, version, action, changes, media_ref, prompt_snapshot, ai_model, content_type, size_bytes)
		VALUES($1, $2, $3, 'regenerate', ARRAY['prompt','media'], $4, $5, $6, $7, $8)
		RETURNING id`,
		chapterID, body.BlockID, nextVersion, objectKey, body.Prompt, "", contentType, uploadInfo.Size,
	).Scan(&versionID)

	mediaURL := s.mediaURL(objectKey)

	// 6. Best-effort usage billing. provider_kind is empty string —
	// gateway records its own model-level usage; this call records
	// APPLICATION-LEVEL purpose. Per Phase 5e-α QC MED#1 precedent.
	if s.cfg.UsageBillingServiceURL != "" {
		modelRefUUID, _ := uuid.Parse(body.ModelRef)
		usagePayload, _ := json.Marshal(map[string]any{
			"request_id":     uuid.New(),
			"owner_user_id":  ownerID,
			"provider_kind":  "", // tracked as D-PHASE5E-BILLING-PROVIDER-KIND-ANALYTICS
			"model_source":   body.ModelSource,
			"model_ref":      modelRefUUID,
			"input_tokens":   len(body.Prompt),
			"output_tokens":  0,
			"request_status": "success",
			"purpose":        "image_generation",
		})
		billingURL := fmt.Sprintf("%s/internal/model-billing/record",
			strings.TrimRight(s.cfg.UsageBillingServiceURL, "/"))
		billingReq, _ := http.NewRequestWithContext(ctx, "POST", billingURL, bytes.NewReader(usagePayload))
		billingReq.Header.Set("Content-Type", "application/json")
		billingReq.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
		if resp, err := internalClient.Do(billingReq); err != nil {
			slog.Warn("generateChapterMedia billing failed", "error", err)
		} else {
			resp.Body.Close()
		}
	}

	writeJSON(w, http.StatusCreated, map[string]any{
		"url":          mediaURL,
		"object_key":   objectKey,
		"version":      nextVersion,
		"version_id":   versionID,
		"ai_model":     "", // Phase 5e-β.1 — empty until SDK exposes provider_model_name; FE hides line on falsy
		"size":         uploadInfo.Size,
		"content_type": contentType,
	})
}

// ── Bucket management ───────────────────────────────────────────────────────

var mediaBucketReady bool

func (s *Server) ensureMediaBucket(ctx context.Context) error {
	if mediaBucketReady {
		return nil
	}
	exists, err := s.minio.BucketExists(ctx, mediaBucket)
	if err != nil {
		return err
	}
	if !exists {
		err = s.minio.MakeBucket(ctx, mediaBucket, minio.MakeBucketOptions{})
		if err != nil {
			if exists2, _ := s.minio.BucketExists(ctx, mediaBucket); exists2 {
				mediaBucketReady = true
				return s.setBucketPublicRead(ctx)
			}
			return err
		}
	}
	mediaBucketReady = true
	return s.setBucketPublicRead(ctx)
}

func (s *Server) setBucketPublicRead(ctx context.Context) error {
	// Set bucket policy to allow public read (anonymous GET)
	p := `{
		"Version": "2012-10-17",
		"Statement": [{
			"Effect": "Allow",
			"Principal": {"AWS": ["*"]},
			"Action": ["s3:GetObject"],
			"Resource": ["arn:aws:s3:::` + mediaBucket + `/*"]
		}]
	}`
	return s.minio.SetBucketPolicy(ctx, mediaBucket, p)
}

// ── Helpers ─────────────────────────────────────────────────────────────────

// mediaURL returns the browser-accessible URL for a MinIO/S3 object.
func (s *Server) mediaURL(objectKey string) string {
	return fmt.Sprintf("%s/%s/%s", s.cfg.MinioExternalURL, mediaBucket, objectKey)
}

func nilIfEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}
