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
	"log/slog"
	"mime"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/loreweave/provider-registry-service/internal/billing"
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

	// Phase 3c — decode the optional chunking config up front. Moved ahead
	// of the guardrail pre-flight (Phase 6a): a malformed chunking config is
	// a 400 BEFORE any reservation is placed, so a bad request never leaks a
	// held reservation.
	chunkCfg, decodeErr := jobs.DecodeChunkConfig(in.Chunking)
	if decodeErr != nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST",
			"invalid chunking config: "+decodeErr.Error())
		return
	}

	// Phase 6a — spend-guardrail pre-flight: model lookup (404 if missing),
	// worst-case cost estimate (402 if unpriced), max_tokens cap, and the
	// usage-billing reservation. The job_id is generated up front so the
	// reservation can reference it before the row exists (design §3.5).
	jobID, err := uuid.NewV7()
	if err != nil {
		writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "failed to allocate job id")
		return
	}
	pf, ok := s.runGuardrailPreflight(w, r, jobID, userID, modelRef, in.Operation, in.ModelSource, in.Input, chunkCfg)
	if !ok {
		return // runGuardrailPreflight already wrote the error response
	}

	if _, err := s.jobsRepo.Insert(r.Context(), jobs.InsertParams{
		JobID:         jobID,
		OwnerUserID:   userID,
		Operation:     in.Operation,
		ModelSource:   in.ModelSource,
		ModelRef:      modelRef,
		Input:         pf.input,
		Chunking:      rawOrNil(in.Chunking),
		Callback:      rawOrNil(in.Callback),
		JobMeta:       mergeJobMeta(in.JobMeta, pf.capApplied),
		TraceID:       in.TraceID,
		ReservationID: &pf.reservationID,
	}); err != nil {
		// The reservation is now orphaned (held, no job to settle it). Per
		// design §3.5 LOW#13 this is accepted — the usage-billing sweeper
		// releases it after RESERVATION_TTL.
		writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "failed to create job")
		return
	}

	// Spawn the worker goroutine. Use a fresh context detached from the
	// inbound HTTP request so the goroutine survives the response. The
	// worker gets pf.input — the possibly max_tokens-capped input.
	go func() {
		bgCtx := context.Background()
		s.jobsWorker.Process(bgCtx, jobID, userID, in.Operation, in.ModelSource, modelRef, pf.input, chunkCfg)
	}()

	writeJSON(w, http.StatusAccepted, map[string]any{
		"job_id":       jobID.String(),
		"status":       "pending",
		"submitted_at": nowRFC3339Nano(),
	})
}

// maxTokensCap records a budget-driven max_tokens reduction. It is folded into
// the job's job_meta so the caller sees the cap was applied — the result is
// not silently truncated (design §3.5 MED#6).
type maxTokensCap struct {
	Requested int    `json:"requested"`
	Applied   int    `json:"applied"`
	Reason    string `json:"reason"`
}

// preflightResult carries the guardrail pre-flight outcome into doSubmitJob.
type preflightResult struct {
	reservationID uuid.UUID
	input         json.RawMessage // original, or with max_tokens capped
	capApplied    *maxTokensCap   // non-nil → a cap was applied
}

// runGuardrailPreflight performs the Phase 6a pre-flight for a job submission:
// model lookup, cost estimate, optional max_tokens cap, and reservation. On
// any rejection it writes the HTTP error itself and returns ok=false.
func (s *Server) runGuardrailPreflight(
	w http.ResponseWriter, r *http.Request,
	jobID, userID, modelRef uuid.UUID,
	operation, modelSource string,
	rawInput json.RawMessage,
	chunkCfg *jobs.ChunkConfig,
) (preflightResult, bool) {
	ctx := r.Context()

	var inputMap map[string]any
	if err := json.Unmarshal(rawInput, &inputMap); err != nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "input must be a JSON object")
		return preflightResult{}, false
	}

	// 1. Model lookup. A model that does not exist is a 404 — distinct from
	//    a model that exists but is unpriced (a 402 below). (design MED#7)
	pricing, found, err := s.jobsRepo.ModelPricing(ctx, modelSource, userID, modelRef)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "model lookup failed")
		return preflightResult{}, false
	}
	if !found {
		writeError(w, http.StatusNotFound, "LLM_MODEL_NOT_FOUND", "model not found")
		return preflightResult{}, false
	}

	// 2. Estimate. nchunks is derived from the chunk config + the raw input
	//    token count (no overhead) so the per-chunk overhead lands once.
	strategy, size := "", 0
	if chunkCfg != nil {
		strategy, size = chunkCfg.Strategy, chunkCfg.Size
	}
	nchunks := billing.EstimateNChunks(strategy, size, s.estimator.InputTokens(inputMap, 1))

	estimate, err := s.estimator.EstimateUSD(operation, inputMap, pricing, nchunks)
	if errors.Is(err, billing.ErrUnpriced) {
		writeError(w, http.StatusPaymentRequired, "LLM_QUOTA_EXCEEDED", "model pricing not configured")
		return preflightResult{}, false
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "cost estimate failed")
		return preflightResult{}, false
	}

	// 3 + 4. Reserve. A success carries the reservation onto the job row.
	res, err := s.guardrail.Reserve(ctx, userID, jobID, estimate, modelSource)
	if err != nil {
		// Fail CLOSED — no job runs on an unconfirmed reservation. This is
		// a deliberate availability coupling (/review-impl MED#4): while
		// usage-billing is unreachable, job submission is blocked rather
		// than letting unbounded spend through. Fail-open would defeat the
		// guardrail. The 503 lets callers retry once billing recovers.
		writeError(w, http.StatusServiceUnavailable, "LLM_INTERNAL_ERROR", "billing service unavailable")
		return preflightResult{}, false
	}
	if !res.Insufficient {
		return preflightResult{reservationID: res.ReservationID, input: rawInput}, true
	}

	// A Subsystem-B rejection (platform free tier + credits) is not a
	// max_tokens-cap situation — capping shrinks the estimate but the
	// platform pool, not the user's daily/monthly budget, is the binding
	// constraint. Propagate it directly (Phase 6a-γ).
	if res.Code == "PLATFORM_BALANCE_EXHAUSTED" {
		writeBudget402(w, res)
		return preflightResult{}, false
	}
	// Over budget. Only chat/completion may be salvaged by capping
	// max_tokens — truncating a translation/extraction/media artifact is
	// corruption, not degradation, so those propagate the 402 (design §3.5).
	if operation != "chat" && operation != "completion" {
		writeBudget402(w, res)
		return preflightResult{}, false
	}
	capped, reqMax, capOK := s.affordableMaxTokens(inputMap, pricing, nchunks, res)
	if !capOK {
		writeBudget402(w, res)
		return preflightResult{}, false
	}
	inputMap["max_tokens"] = capped
	cappedInput, err := json.Marshal(inputMap)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "failed to apply max_tokens cap")
		return preflightResult{}, false
	}
	estimate2, err := s.estimator.EstimateUSD(operation, inputMap, pricing, nchunks)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "re-estimate failed")
		return preflightResult{}, false
	}
	res2, err := s.guardrail.Reserve(ctx, userID, jobID, estimate2, modelSource)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "LLM_INTERNAL_ERROR", "billing service unavailable")
		return preflightResult{}, false
	}
	if res2.Insufficient {
		writeBudget402(w, res2)
		return preflightResult{}, false
	}
	return preflightResult{
		reservationID: res2.ReservationID,
		input:         cappedInput,
		capApplied:    &maxTokensCap{Requested: reqMax, Applied: capped, Reason: "budget"},
	}, true
}

// affordableMaxTokens computes how many output tokens the remaining budget
// affords for a chat/completion job, AFTER subtracting the worst-case input
// cost (design §3.5 LOW#12). capOK is false when not even a usable output is
// affordable, or output is free (so capping cannot help) — the caller 402s.
func (s *Server) affordableMaxTokens(
	inputMap map[string]any, pricing billing.Pricing, nchunks int, res billing.ReserveResult,
) (capped, reqMax int, capOK bool) {
	reqMax = mapInt(inputMap, "max_tokens", s.cfg.MaxOutputTokensDefault)
	if pricing.InputPerMTok == nil || pricing.OutputPerMTok == nil {
		return 0, reqMax, false
	}
	budget := res.DailyAvailable
	if res.MonthlyAvailable < budget {
		budget = res.MonthlyAvailable
	}
	inputCost := float64(s.estimator.InputTokens(inputMap, nchunks)) / 1e6 * (*pricing.InputPerMTok)
	outPerTok := *pricing.OutputPerMTok / 1e6
	if outPerTok <= 0 {
		// Output is free → the 402 is driven by the input cost alone;
		// capping max_tokens cannot bring the job under budget.
		return 0, reqMax, false
	}
	affordable := int((budget - inputCost) / outPerTok)
	if affordable < 1 {
		return 0, reqMax, false
	}
	if affordable > reqMax {
		affordable = reqMax // never RAISE the caller's requested ceiling
	}
	return affordable, reqMax, true
}

// writeBudget402 emits the over-budget rejection. The message distinguishes
// the two gates: Subsystem A (the user's daily/monthly cap) vs Subsystem B
// (the platform free tier + credits) — /review-impl D-PHASE6A-BETA-402-MESSAGE.
func writeBudget402(w http.ResponseWriter, res billing.ReserveResult) {
	msg := fmt.Sprintf("insufficient budget: estimated $%.8f, available daily $%.8f / monthly $%.8f",
		res.Requested, res.DailyAvailable, res.MonthlyAvailable)
	if res.Code == "PLATFORM_BALANCE_EXHAUSTED" {
		msg = fmt.Sprintf("platform free tier + credits exhausted: estimated $%.8f, available $%.8f",
			res.Requested, res.PlatformAvailable)
	}
	writeError(w, http.StatusPaymentRequired, "LLM_QUOTA_EXCEEDED", msg)
}

// mergeJobMeta folds a max_tokens cap into the caller's job_meta. Returns a
// value suitable for jobs.InsertParams.JobMeta (nil → SQL NULL).
func mergeJobMeta(raw json.RawMessage, cap *maxTokensCap) any {
	if cap == nil {
		return rawOrNil(raw)
	}
	meta := map[string]any{}
	if len(raw) > 0 && string(raw) != "null" {
		// Best-effort: a non-object job_meta is replaced by the cap object.
		_ = json.Unmarshal(raw, &meta)
	}
	meta["max_tokens_capped"] = cap
	return meta
}

// mapInt reads a JSON-decoded numeric field (float64 in a decoded map) as an
// int, falling back to def.
func mapInt(m map[string]any, key string, def int) int {
	switch v := m[key].(type) {
	case float64:
		return int(v)
	case int:
		return v
	default:
		return def
	}
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
	// Phase 6a — release the spend reservation (cancelled job: no spend).
	// Both best-effort: the DB row is the source of truth; a notifier blip
	// just means FE polls, and a release blip is caught by the usage-billing
	// sweeper. Re-read the row once to fold operation/trace_id into the
	// envelope and to recover the reservation_id.
	if job, getErr := s.jobsRepo.Get(r.Context(), jobID, userID); getErr == nil {
		if s.jobsNotifier != nil {
			_ = s.jobsNotifier.PublishTerminal(r.Context(), jobs.TerminalEvent{
				JobID:       job.JobID,
				OwnerUserID: job.OwnerUserID,
				Operation:   job.Operation,
				Status:      "cancelled",
			})
		}
		if job.ReservationID != nil && s.guardrail != nil {
			if relErr := s.guardrail.Release(r.Context(), *job.ReservationID); relErr != nil {
				slog.Warn("guardrail release on cancel failed",
					"job_id", jobID.String(), "err", relErr)
			}
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
