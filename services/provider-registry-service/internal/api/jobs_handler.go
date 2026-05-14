package api

// jobs_handler.go — Phase 2b (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN)
// Async LLM job lifecycle handlers per
// contracts/api/llm-gateway/v1/openapi.yaml.
//
// - POST /v1/llm/jobs           (JWT)         + /internal/llm/jobs (svc)
// - GET  /v1/llm/jobs/{job_id}  (JWT)         + /internal/llm/jobs/{job_id} (svc)
// - DELETE /v1/llm/jobs/{job_id}              (cancellation)
//
// Worker is fired inline via goroutine; Phase 2c will swap to a
// RabbitMQ consumer. Caller polls GET to track progress / collect
// the result.

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/loreweave/provider-registry-service/internal/jobs"
	"github.com/loreweave/provider-registry-service/internal/provider"
)

// Phase 5b — bytes-mode STT submit constants. SttMaxAudioBytes mirrors
// provider.MaxAudioBytes (25MB OpenAI Whisper cap); sttMultipartOverhead
// is a small allowance for multipart envelope (boundary, headers, form
// fields) so the cap doesn't fire on a 25MB audio surrounded by ~1KB of
// metadata. Total request body cap = SttMaxAudioBytes + overhead.
const (
	SttMaxAudioBytes     = 25 * 1024 * 1024
	sttMultipartOverhead = 64 * 1024
)

func nowRFC3339Nano() string { return time.Now().UTC().Format(time.RFC3339Nano) }

// validJobOperations mirrors the openapi JobOperation enum.
var validJobOperations = map[string]struct{}{
	"chat": {}, "completion": {}, "embedding": {},
	"stt": {}, "tts": {}, "image_gen": {},
	"video_gen":         {}, // Phase 5d
	"audio_gen":         {}, // Phase 5e-β.2 — batch TTS
	"entity_extraction": {}, "relation_extraction": {},
	"event_extraction": {}, "fact_extraction": {}, // Phase 4a-β
	"translation": {},
}

// jobSubmitRequest mirrors openapi SubmitJobRequest.
type jobSubmitRequest struct {
	Operation   string          `json:"operation"`
	ModelSource string          `json:"model_source"`
	ModelRef    string          `json:"model_ref"`
	Input       json.RawMessage `json:"input"`
	Chunking    json.RawMessage `json:"chunking,omitempty"`
	Callback    json.RawMessage `json:"callback,omitempty"`
	JobMeta     json.RawMessage `json:"job_meta,omitempty"`
	TraceID     string          `json:"trace_id,omitempty"`
}

// submitLlmJob — POST /v1/llm/jobs (JWT auth).
func (s *Server) submitLlmJob(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "LLM_AUTH_FAILED", "unauthorized")
		return
	}
	s.doSubmitJob(w, r, userID)
}

// internalSubmitLlmJob — POST /internal/llm/jobs (X-Internal-Token + user_id query).
func (s *Server) internalSubmitLlmJob(w http.ResponseWriter, r *http.Request) {
	userID, ok := parseUserIDQuery(w, r)
	if !ok {
		return
	}
	s.doSubmitJob(w, r, userID)
}

func (s *Server) doSubmitJob(w http.ResponseWriter, r *http.Request, userID uuid.UUID) {
	// Phase 5b /review-impl MED#4 — Content-Type dispatch via mime.ParseMediaType
	// (RFC-conformant; handles MULTIPART/FORM-DATA case-insensitivity + param
	// ordering variation that naive strings.HasPrefix would miss).
	mediaType, _, mtErr := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if mtErr != nil {
		// Empty / malformed Content-Type — default to JSON to preserve
		// the Phase 5a behavior where clients omitting Content-Type
		// (or sending a garbage value) still got their JSON parsed.
		mediaType = "application/json"
	}
	switch mediaType {
	case "multipart/form-data":
		s.doSubmitSttMultipart(w, r, userID)
		return
	case "application/json", "":
		// Falls through to legacy JSON path below.
	default:
		writeError(w, http.StatusUnsupportedMediaType, "LLM_INVALID_REQUEST",
			"unsupported Content-Type: "+mediaType)
		return
	}

	// Caller-input validation first — these rejections are independent of
	// service health, so a malformed request returns 400 even when
	// jobsRepo is nil. The 503 check below catches the case where the
	// request is well-formed but the subsystem is down.
	var in jobSubmitRequest
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "invalid JSON body")
		return
	}
	if _, ok := validJobOperations[in.Operation]; !ok {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "invalid or missing operation")
		return
	}
	// Phase 5a: tts is supported only via /v1/llm/stream. Submitting tts
	// here returns 400 with a hint pointing at the streaming endpoint.
	// This rejection lives at the handler boundary (not the worker) so
	// callers learn their mistake immediately, before a job row is
	// inserted. The worker has a defensive fallback (worker.go) for the
	// theoretical case where this gate is bypassed.
	if in.Operation == "tts" {
		writeError(w, http.StatusBadRequest, "LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS",
			"tts is supported only via POST /v1/llm/stream — submit there with operation=tts")
		return
	}
	if in.ModelSource != "user_model" && in.ModelSource != "platform_model" {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "invalid model_source")
		return
	}
	modelRef, err := uuid.Parse(in.ModelRef)
	if err != nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "invalid model_ref")
		return
	}
	if len(in.Input) == 0 {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "input required")
		return
	}

	// Phase 5c-α + 5d — operation-specific input validation for media ops.
	if in.Operation == "image_gen" {
		if err := validateImageGenInput(in.Input, in.Chunking); err != nil {
			writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", err.Error())
			return
		}
	}
	if in.Operation == "video_gen" {
		if err := validateVideoGenInput(in.Input, in.Chunking); err != nil {
			writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", err.Error())
			return
		}
	}
	if in.Operation == "audio_gen" {
		if err := validateAudioGenInput(in.Input, in.Chunking); err != nil {
			writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", err.Error())
			return
		}
	}

	if s.jobsRepo == nil || s.jobsWorker == nil {
		writeError(w, http.StatusServiceUnavailable, "LLM_INTERNAL_ERROR", "jobs subsystem not initialized")
		return
	}

	jobID, err := s.jobsRepo.Insert(r.Context(), jobs.InsertParams{
		OwnerUserID: userID,
		Operation:   in.Operation,
		ModelSource: in.ModelSource,
		ModelRef:    modelRef,
		Input:       json.RawMessage(in.Input),
		Chunking:    rawOrNil(in.Chunking),
		Callback:    rawOrNil(in.Callback),
		JobMeta:     rawOrNil(in.JobMeta),
		TraceID:     in.TraceID,
	})
	if err != nil {
		writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "failed to create job")
		return
	}

	// Phase 3c — decode the optional chunking config now so the worker
	// goroutine doesn't need to re-parse the JSONB. Decode failure here
	// is non-fatal: we fall back to single-call mode (caller's
	// chunking field is malformed but the job itself can still run).
	chunkCfg, decodeErr := jobs.DecodeChunkConfig(in.Chunking)
	if decodeErr != nil {
		// Treat as caller error rather than silent fallback so the
		// caller learns their config was malformed. Job already
		// inserted — finalize as failed.
		_, _ = s.jobsRepo.Cancel(r.Context(), jobID, userID)
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST",
			"invalid chunking config: "+decodeErr.Error())
		return
	}

	// Spawn the worker goroutine. Use a fresh context detached from the
	// inbound HTTP request so the goroutine survives the response.
	go func() {
		bgCtx := context.Background()
		s.jobsWorker.Process(bgCtx, jobID, userID, in.Operation, in.ModelSource, modelRef, in.Input, chunkCfg)
	}()

	writeJSON(w, http.StatusAccepted, map[string]any{
		"job_id":       jobID.String(),
		"status":       "pending",
		"submitted_at": nowRFC3339Nano(),
	})
}

// rawOrNil treats an empty json.RawMessage as a true SQL NULL rather
// than the JSON literal `null`. Repo.Insert further marshals nil → NULL.
func rawOrNil(raw json.RawMessage) any {
	if len(raw) == 0 {
		return nil
	}
	return json.RawMessage(raw)
}

// doSubmitSttMultipart handles Phase 5b bytes-mode STT submission.
//
// Wire: multipart/form-data with metadata fields (operation, model_source,
// model_ref, language, trace_id) + a "audio" file part holding the raw
// audio bytes. ONLY operation=stt is accepted via multipart; other
// operations return 400.
//
// Audio bytes flow:
//  1. http.MaxBytesReader caps the request body at SttMaxAudioBytes
//     plus a small multipart envelope overhead (Fix #1).
//  2. ParseMultipartForm extracts metadata + the file part. maxMemory
//     is set to SttMaxAudioBytes so the entire 25MB stays in RAM
//     rather than spilling to TempDir (we want bytes in goroutine
//     closure for ProcessAudioInline).
//  3. Read the file into memory ONCE via the FileHeader.Open() handle
//     (also capped at SttMaxAudioBytes).
//  4. Insert llm_jobs row with synthetic JSON input (NO bytes in DB).
//  5. Spawn goroutine → worker.ProcessAudioInline(... audioBytes ...).
//
// http.MaxBytesError → 413 LLM_AUDIO_TOO_LARGE; other parse errors → 400.
func (s *Server) doSubmitSttMultipart(w http.ResponseWriter, r *http.Request, userID uuid.UUID) {
	// Phase 5b /review-impl HIGH#1 — explicit cap mechanism. Wrap the
	// body BEFORE ParseMultipartForm so a 50MB POST gets rejected at
	// the network read step (not after multipart parsing allocates).
	r.Body = http.MaxBytesReader(w, r.Body, SttMaxAudioBytes+sttMultipartOverhead)

	if err := r.ParseMultipartForm(SttMaxAudioBytes); err != nil {
		var maxBytesErr *http.MaxBytesError
		if errors.As(err, &maxBytesErr) {
			writeError(w, http.StatusRequestEntityTooLarge, "LLM_AUDIO_TOO_LARGE",
				fmt.Sprintf("audio exceeds %d-byte cap", SttMaxAudioBytes))
			return
		}
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST",
			"multipart parse failed: "+err.Error())
		return
	}

	// Metadata field extraction (mirrors the JSON jobSubmitRequest fields).
	operation := r.FormValue("operation")
	if operation == "" {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "operation field required")
		return
	}
	if operation != "stt" {
		// Phase 5b /review-impl design §2.1 — only stt is supported on
		// multipart. tts is /v1/llm/stream; image_gen has no caller.
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST",
			"operation "+operation+" not supported via multipart; use application/json")
		return
	}

	modelSource := r.FormValue("model_source")
	if modelSource != "user_model" && modelSource != "platform_model" {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "invalid model_source")
		return
	}
	modelRefStr := r.FormValue("model_ref")
	modelRef, err := uuid.Parse(modelRefStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "invalid model_ref")
		return
	}
	language := r.FormValue("language")
	if language == "" {
		language = "auto"
	}
	traceID := r.FormValue("trace_id")

	// Phase 5b /review-impl LOW#12 — chunking not accepted on multipart.
	if r.FormValue("chunking") != "" {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST",
			"chunking not accepted on stt multipart submits")
		return
	}

	// Phase 5b /review-impl LOW#13 — explicit field-name diagnostic.
	if r.MultipartForm == nil || r.MultipartForm.File == nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST",
			"no file fields in multipart request; expected 'audio'")
		return
	}
	audioHeaders, ok := r.MultipartForm.File["audio"]
	if !ok || len(audioHeaders) == 0 {
		// Build hint listing whichever file fields were present.
		var got []string
		for name := range r.MultipartForm.File {
			got = append(got, name)
		}
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST",
			fmt.Sprintf("expected file field 'audio'; got %s", formatFieldList(got)))
		return
	}

	// Single audio file — read into memory.
	audioFile, err := audioHeaders[0].Open()
	if err != nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST",
			"open audio file: "+err.Error())
		return
	}
	defer audioFile.Close()
	// LimitReader belt-and-suspenders — the MaxBytesReader above already
	// caps total body size, but this guards against a degenerate
	// multipart form with one huge field that the form parser somehow
	// undercounted.
	audioBytes, err := io.ReadAll(io.LimitReader(audioFile, SttMaxAudioBytes+1))
	if err != nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST",
			"read audio bytes: "+err.Error())
		return
	}
	if len(audioBytes) > SttMaxAudioBytes {
		writeError(w, http.StatusRequestEntityTooLarge, "LLM_AUDIO_TOO_LARGE",
			fmt.Sprintf("audio exceeds %d-byte cap", SttMaxAudioBytes))
		return
	}
	// Phase 5b /review-impl(QC) MED#1 — 0-byte audio. Without this
	// check, a non-nil empty slice would slip past the adapter's
	// `hasBytes := input.AudioBytes != nil` (nil-vs-empty is a Go
	// trap), reach OpenAI Whisper as a 0-byte multipart file, and
	// surface as a confusing LLM_UPSTREAM_ERROR rather than a clear
	// "you sent no audio" message.
	if len(audioBytes) == 0 {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST",
			"audio field is empty (0 bytes)")
		return
	}
	contentType := audioHeaders[0].Header.Get("Content-Type")
	// Phase 5b /review-impl(QC) MED#2 — empty per-part Content-Type
	// would cascade through audioFilenameFromContentType → "audio.wav"
	// default, misleading OpenAI Whisper if the actual bytes aren't
	// WAV. Reject explicitly so caller surfaces the bug at submit time.
	if contentType == "" {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST",
			"audio file part missing Content-Type header (e.g. \"audio/webm\")")
		return
	}

	// Subsystem availability — after validation so the response code
	// distinguishes "you sent bad data" (400/413) from "server isn't ready"
	// (503).
	if s.jobsRepo == nil || s.jobsWorker == nil {
		writeError(w, http.StatusServiceUnavailable, "LLM_INTERNAL_ERROR", "jobs subsystem not initialized")
		return
	}

	// Synthetic input: metadata only. NO audio bytes in DB — they live
	// in this handler's stack memory and get captured into the worker
	// goroutine's closure below (design §3.2).
	synthInput, _ := json.Marshal(map[string]any{
		"audio_inline": true,
		"content_type": contentType,
		"language":     language,
	})
	jobID, ierr := s.jobsRepo.Insert(r.Context(), jobs.InsertParams{
		OwnerUserID: userID,
		Operation:   "stt",
		ModelSource: modelSource,
		ModelRef:    modelRef,
		Input:       synthInput,
		Chunking:    nil,
		Callback:    nil,
		JobMeta:     nil,
		TraceID:     traceID,
	})
	if ierr != nil {
		writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "failed to create job")
		return
	}

	// Spawn the worker goroutine. audioBytes is captured by closure;
	// bgCtx detaches from the HTTP request so the goroutine survives
	// the 202 response.
	go func() {
		bgCtx := context.Background()
		s.jobsWorker.ProcessAudioInline(
			bgCtx, jobID, userID, modelSource, modelRef,
			language, audioBytes, contentType,
		)
	}()

	writeJSON(w, http.StatusAccepted, map[string]any{
		"job_id":       jobID.String(),
		"status":       "pending",
		"submitted_at": nowRFC3339Nano(),
	})
}

// validateImageGenInput — Phase 5c-α handler-level validation for
// operation=image_gen. Rejects malformed prompt, out-of-range n, bad
// response_format, and chunking-config (not supported for image gen).
//
// Belt-and-suspenders with adapter-level invariant pre-checks: handler
// returns LLM_INVALID_REQUEST fast (no DB insert, no goroutine spawn);
// adapter catches the same conditions for non-handler callers.
func validateImageGenInput(raw json.RawMessage, chunking json.RawMessage) error {
	// Phase 5c-α — chunking not supported for image_gen (single
	// upstream call, no logical chunking). Reject if non-empty / non-null.
	if len(chunking) > 0 && string(chunking) != "null" {
		return fmt.Errorf("chunking not supported for image_gen")
	}

	var v struct {
		Prompt         string `json:"prompt"`
		N              int    `json:"n"`
		ResponseFormat string `json:"response_format"`
	}
	if err := json.Unmarshal(raw, &v); err != nil {
		return fmt.Errorf("image_gen input parse: %w", err)
	}
	if strings.TrimSpace(v.Prompt) == "" {
		return fmt.Errorf("image_gen requires non-empty prompt")
	}
	if len(v.Prompt) > 32000 {
		return fmt.Errorf("image_gen prompt exceeds 32000-char cap (got %d)", len(v.Prompt))
	}
	// n=0 means "use upstream default"; explicit values must be 1..4.
	if v.N != 0 && (v.N < 1 || v.N > 4) {
		return fmt.Errorf("image_gen n must be 1..4 (got %d)", v.N)
	}
	if v.ResponseFormat != "" && v.ResponseFormat != "url" && v.ResponseFormat != "b64_json" {
		return fmt.Errorf("image_gen response_format must be url or b64_json (got %q)", v.ResponseFormat)
	}
	return nil
}

// validateVideoGenInput — Phase 5d handler-level validation for
// operation=video_gen. Rejects malformed prompt, out-of-range duration,
// n != 1, b64_json response_format (impractical for video per
// /review-impl(DESIGN) MED#3), oversize init_image (/review-impl
// MED#2), and chunking config (not supported for video gen).
//
// /review-impl(BUILD) LOW#6 cross-reference: adapter-side validation
// in provider/openai_video.go::GenerateVideo mirrors these checks.
// Belt-and-suspenders: handler catches caller-side validation early
// (no DB insert, no goroutine spawn); adapter catches non-handler
// callers (cron, future RabbitMQ submit path, background re-runs).
// If the two layers ever drift, the test pyramid catches it
// (jobs_router_test.go covers this function; adapters_video_test.go
// covers the adapter's GenerateVideo).
func validateVideoGenInput(raw json.RawMessage, chunking json.RawMessage) error {
	// chunking not supported for video_gen (single upstream call).
	if len(chunking) > 0 && string(chunking) != "null" {
		return fmt.Errorf("chunking not supported for video_gen")
	}

	var v struct {
		Prompt         string `json:"prompt"`
		Duration       int    `json:"duration"`
		N              int    `json:"n"`
		ResponseFormat string `json:"response_format"`
		InitImage      string `json:"init_image"`
	}
	if err := json.Unmarshal(raw, &v); err != nil {
		return fmt.Errorf("video_gen input parse: %w", err)
	}
	if strings.TrimSpace(v.Prompt) == "" {
		return fmt.Errorf("video_gen requires non-empty prompt")
	}
	if len(v.Prompt) > 32000 {
		return fmt.Errorf("video_gen prompt exceeds 32000-char cap (got %d)", len(v.Prompt))
	}
	if v.Duration != 0 && (v.Duration < 1 || v.Duration > 60) {
		return fmt.Errorf("video_gen duration must be 1..60s (got %d)", v.Duration)
	}
	// Phase 5d locks to n=1. 0 (omit) treated as 1.
	if v.N != 0 && v.N != 1 {
		return fmt.Errorf("video_gen n must be 1 (got %d)", v.N)
	}
	// /review-impl(DESIGN) MED#3 — reject b64_json at handler with clear
	// hint. Asymmetric with image_gen (which accepts both); video b64
	// exceeds the 8MB MaxImageResponseBytes cap in practice.
	if v.ResponseFormat != "" && v.ResponseFormat != "url" {
		return fmt.Errorf("video_gen response_format must be \"url\" (b64_json impractical for video; got %q)", v.ResponseFormat)
	}
	// /review-impl(DESIGN) MED#2 — init_image size cap (measured as
	// received — the bytes that will hit the llm_jobs.input JSONB row).
	// Note: belt-and-suspenders with adapter-side check (openai_video.go);
	// either layer firing early gives the caller a clear 400. If the
	// validation layers diverge in a future refactor, the integration
	// test pyramid should catch it (handler tests + adapter tests both
	// cover this case independently).
	if len(v.InitImage) > provider.MaxImg2VidInputBytes {
		return fmt.Errorf("video_gen init_image exceeds %d-byte cap (got %d)", provider.MaxImg2VidInputBytes, len(v.InitImage))
	}
	return nil
}

// validateAudioGenInput — Phase 5e-β.2 handler-level validation for
// operation=audio_gen. Rejects empty texts, batch over MaxAudioGenInputs,
// per-text empty/oversize, bad response_format/format, and chunking.
//
// /review-impl(DESIGN) COSMETIC#3 — chunking checked on top-level
// SubmitJobRequest.Chunking param (json.RawMessage), NOT input["chunking"].
// Mirrors validateImageGenInput / validateVideoGenInput pattern.
func validateAudioGenInput(raw json.RawMessage, chunking json.RawMessage) error {
	if len(chunking) > 0 && string(chunking) != "null" {
		return fmt.Errorf("chunking not supported for audio_gen")
	}
	var v struct {
		Texts          []string `json:"texts"`
		Voice          string   `json:"voice"`
		Speed          float64  `json:"speed"`
		Format         string   `json:"format"`
		ResponseFormat string   `json:"response_format"`
	}
	if err := json.Unmarshal(raw, &v); err != nil {
		return fmt.Errorf("audio_gen input parse: %w", err)
	}
	if len(v.Texts) == 0 {
		return fmt.Errorf("audio_gen requires non-empty texts array")
	}
	if len(v.Texts) > provider.MaxAudioGenInputs {
		return fmt.Errorf("audio_gen texts exceeds %d (got %d)", provider.MaxAudioGenInputs, len(v.Texts))
	}
	for i, t := range v.Texts {
		if strings.TrimSpace(t) == "" {
			return fmt.Errorf("audio_gen texts[%d] must not be empty/whitespace", i)
		}
		if len(t) > provider.MaxAudioGenInputCharsLen {
			return fmt.Errorf("audio_gen texts[%d] exceeds %d-char cap (got %d)", i, provider.MaxAudioGenInputCharsLen, len(t))
		}
	}
	if v.ResponseFormat != "" && v.ResponseFormat != "b64_json" && v.ResponseFormat != "url" {
		return fmt.Errorf("audio_gen response_format must be \"b64_json\" or \"url\" (got %q)", v.ResponseFormat)
	}
	if v.Format != "" {
		valid := map[string]bool{"mp3": true, "opus": true, "aac": true, "flac": true, "wav": true, "pcm": true}
		if !valid[v.Format] {
			return fmt.Errorf("audio_gen format must be one of mp3/opus/aac/flac/wav/pcm (got %q)", v.Format)
		}
	}
	if v.Speed != 0 && (v.Speed < 0.25 || v.Speed > 4.0) {
		return fmt.Errorf("audio_gen speed must be 0.25..4.0 (got %g)", v.Speed)
	}
	return nil
}

// formatFieldList renders a slice of field names for the field-name
// diagnostic in 'expected file field "audio"; got [...]' errors.
func formatFieldList(names []string) string {
	if len(names) == 0 {
		return "[]"
	}
	return "[" + strings.Join(names, ", ") + "]"
}

// getLlmJob — GET /v1/llm/jobs/{job_id} (JWT auth).
func (s *Server) getLlmJob(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "LLM_AUTH_FAILED", "unauthorized")
		return
	}
	s.doGetJob(w, r, userID)
}

// internalGetLlmJob — GET /internal/llm/jobs/{job_id}.
func (s *Server) internalGetLlmJob(w http.ResponseWriter, r *http.Request) {
	userID, ok := parseUserIDQuery(w, r)
	if !ok {
		return
	}
	s.doGetJob(w, r, userID)
}

func (s *Server) doGetJob(w http.ResponseWriter, r *http.Request, userID uuid.UUID) {
	if s.jobsRepo == nil {
		writeError(w, http.StatusServiceUnavailable, "LLM_INTERNAL_ERROR", "jobs subsystem not initialized")
		return
	}
	jobIDStr := chi.URLParam(r, "job_id")
	jobID, err := uuid.Parse(jobIDStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "invalid job_id")
		return
	}
	job, err := s.jobsRepo.Get(r.Context(), jobID, userID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "LLM_JOB_NOT_FOUND", "job not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "failed to fetch job")
		return
	}
	writeJSON(w, http.StatusOK, jobs.MarshalJob(job))
}

// cancelLlmJob — DELETE /v1/llm/jobs/{job_id} (JWT auth). Best-effort
// cancel: ctx of an in-flight worker goroutine is independent (we used
// context.Background()), so cancellation today only flips DB state.
// Phase 6 hardens with worker-context cancellation.
func (s *Server) cancelLlmJob(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "LLM_AUTH_FAILED", "unauthorized")
		return
	}
	if s.jobsRepo == nil {
		writeError(w, http.StatusServiceUnavailable, "LLM_INTERNAL_ERROR", "jobs subsystem not initialized")
		return
	}
	jobIDStr := chi.URLParam(r, "job_id")
	jobID, err := uuid.Parse(jobIDStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "invalid job_id")
		return
	}
	rows, err := s.jobsRepo.Cancel(r.Context(), jobID, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "failed to cancel job")
		return
	}
	if rows == 0 {
		// Either not found OR already terminal. Disambiguate via Get.
		_, getErr := s.jobsRepo.Get(r.Context(), jobID, userID)
		if errors.Is(getErr, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "LLM_JOB_NOT_FOUND", "job not found")
			return
		}
		writeError(w, http.StatusConflict, "LLM_JOB_TERMINAL", "job already terminal")
		return
	}
	// Phase 2c — emit terminal event so notification-service can fan out.
	// Best-effort: DB row is the source of truth; failure here just means
	// FE has to poll. Re-read the row to fold operation/trace_id into
	// the envelope without trusting client-supplied fields.
	if s.jobsNotifier != nil {
		if job, getErr := s.jobsRepo.Get(r.Context(), jobID, userID); getErr == nil {
			_ = s.jobsNotifier.PublishTerminal(r.Context(), jobs.TerminalEvent{
				JobID:       job.JobID,
				OwnerUserID: job.OwnerUserID,
				Operation:   job.Operation,
				Status:      "cancelled",
			})
		}
	}
	w.WriteHeader(http.StatusNoContent)
}

// parseUserIDQuery — shared helper for the X-Internal-Token routes.
func parseUserIDQuery(w http.ResponseWriter, r *http.Request) (uuid.UUID, bool) {
	userIDStr := r.URL.Query().Get("user_id")
	if userIDStr == "" {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "user_id query param required")
		return uuid.Nil, false
	}
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "invalid user_id")
		return uuid.Nil, false
	}
	return userID, true
}
