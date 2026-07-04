package api

// stream_handler.go — Phase 1a (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN)
//
// Implements POST /v1/llm/stream + POST /internal/llm/stream per the
// llm-gateway OpenAPI contract. Opens an SSE response, resolves provider
// credentials, calls adapter.Stream(), and re-emits canonical
// StreamChunk events to the wire.
//
// Properties:
//   - **No wall-clock timeout** anywhere in this handler. The stream
//     lives until the upstream completes, the upstream errors, or the
//     caller's HTTP connection closes (r.Context() cancels).
//   - SSE wire format: `event: <name>\ndata: <JSON>\n\n` per the SSE
//     spec; see contracts/api/llm-gateway/v1/openapi.yaml StreamEventEnvelope.
//   - Disconnect propagation: r.Context() cancellation flows into
//     adapter.Stream() which aborts the upstream HTTP call.

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/loreweave/observability"
	"github.com/loreweave/provider-registry-service/internal/billing"
	"github.com/loreweave/provider-registry-service/internal/jobs"
	"github.com/loreweave/provider-registry-service/internal/provider"
)

// base64StdEncode is a thin alias around base64.StdEncoding.EncodeToString,
// kept as a function so the call sites read clearly at the SSE-emit boundary.
func base64StdEncode(p []byte) string {
	return base64.StdEncoding.EncodeToString(p)
}

// hasToolDefinitions reports whether the request carries at least one tool
// definition. The JSON `tools` field decodes into `any`: an absent field is
// nil, but `tools: []` decodes to a non-nil EMPTY `[]any` — which asks for
// nothing and must NOT trip the D8 tools-unsupported guard.
func hasToolDefinitions(tools any) bool {
	s, ok := tools.([]any)
	return ok && len(s) > 0
}

// streamRequest mirrors the StreamRequest schema in the OpenAPI contract.
//
// Phase 5a: `operation` discriminates between chat (default, omitted ⇒
// "chat" for backward-compat) and tts. Chat path uses Messages; tts path
// uses Input. Existing callers don't include `operation` — gateway
// treats absent and "chat" identically.
type streamRequest struct {
	Operation    string         `json:"operation,omitempty"` // Phase 5a; defaults to "chat" when empty
	ModelSource  string         `json:"model_source"`
	ModelRef     string         `json:"model_ref"`
	Messages     any            `json:"messages,omitempty"` // chat only
	Tools        any            `json:"tools,omitempty"`
	ToolChoice   any            `json:"tool_choice,omitempty"` // OpenAI-shaped; chat only
	Temperature  *float64       `json:"temperature,omitempty"`
	MaxTokens    *int           `json:"max_tokens,omitempty"`
	// Reasoning controls — forwarded to the provider unchanged (the adapter's
	// forwardOptionalChatFields allowlist). `reasoning_effort:"none"` turns OFF
	// hidden thinking so reasoning_tokens don't burn the output budget.
	ReasoningEffort    *string        `json:"reasoning_effort,omitempty"`
	ChatTemplateKwargs map[string]any `json:"chat_template_kwargs,omitempty"`
	// Structured-output enforcement — forwarded to the provider unchanged via the
	// adapter's forwardOptionalChatFields allowlist. OpenAI/LM Studio/vLLM shape:
	// {"type":"json_object"} or {"type":"json_schema","json_schema":{…}}. Lets the
	// JSON pipelines (extraction, glossary/chapter translation) force valid JSON so
	// a clean-finish-but-malformed array (the residual completed_with_errors cause)
	// can't happen. `any` (not a typed struct) keeps the gateway shape-agnostic —
	// the provider validates the concrete shape.
	ResponseFormat any `json:"response_format,omitempty"`
	StreamFormat string         `json:"stream_format,omitempty"`
	Input        map[string]any `json:"input,omitempty"` // Phase 5a; tts only
	TraceID      string         `json:"trace_id,omitempty"`
	// M3 (chat disconnect-cancel) — OPTIONAL caller-minted job id. When set on a
	// chat stream, doLlmStream persists a BILLING-NEUTRAL observability llm_jobs
	// row + registers a cancellable context under this id, so a caller (chat-
	// service) can abort the in-flight stream via DELETE /internal/llm/jobs/{id}
	// on a client disconnect. Empty (every legacy caller) → today's behavior
	// verbatim (no row, no registry entry).
	StreamJobID string `json:"stream_job_id,omitempty"`
	// Generic extras passed to adapter (forward-compat for tools, response_format).
	Extra map[string]any `json:"-"`
}

// llmStream — public POST /v1/llm/stream (JWT auth).
func (s *Server) llmStream(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "LLM_AUTH_FAILED", "unauthorized")
		return
	}
	s.doLlmStream(w, r, userID)
}

// internalLlmStream — service-to-service POST /internal/llm/stream
// (X-Internal-Token middleware applied at route level + user_id query).
func (s *Server) internalLlmStream(w http.ResponseWriter, r *http.Request) {
	userIDStr := r.URL.Query().Get("user_id")
	if userIDStr == "" {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "user_id query param required")
		return
	}
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "invalid user_id")
		return
	}
	s.doLlmStream(w, r, userID)
}

// doLlmStream — shared streaming handler used by both auth flavors.
//
// At this point r.Body has not been consumed. We decode it into a
// streamRequest, resolve the provider credentials from the DB, set SSE
// response headers, then call adapter.Stream() with an emit closure that
// serializes each canonical StreamChunk to the wire and flushes.
//
// Phase 5a: branches on Operation. Default path (Operation == "" or
// "chat") preserves the existing chat-streaming behavior verbatim. New
// path Operation == "tts" routes through adapter.Speak emitting
// audio-chunk SSE frames. Other operations return 400 LLM_INVALID_REQUEST
// before any HTTP commit, so callers learn early.
func (s *Server) doLlmStream(w http.ResponseWriter, r *http.Request, userID uuid.UUID) {
	var in streamRequest
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "invalid JSON body")
		return
	}
	if in.ModelRef == "" || in.ModelSource == "" {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "model_source and model_ref required")
		return
	}

	// Phase 5a — operation defaults to "chat" when absent (preserves all
	// existing callers; regression-locked by
	// TestDoLlmStream_OperationDefaultIsChat). Validate operation here
	// so unknown ops fail at 400 before any DB or upstream call.
	op := in.Operation
	if op == "" {
		op = "chat"
	}
	switch op {
	case "chat":
		if in.Messages == nil {
			writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "messages required")
			return
		}
	case "tts":
		if in.Input == nil {
			writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "input required for tts")
			return
		}
		text, _ := in.Input["text"].(string)
		if text == "" {
			writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "input.text required for tts")
			return
		}
	default:
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST",
			"unsupported stream operation: "+op+" (allowed: chat, tts)")
		return
	}

	modelRef, err := uuid.Parse(in.ModelRef)
	if err != nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "invalid model_ref")
		return
	}

	// PUB-12 (BYOK-only) — a public MCP key (X-Mcp-Key-Id header) may not draw a
	// platform_model on the streaming path either; reject 402 before any spend.
	// Synchronous path → header is the carrier (no job_meta here).
	if rejectPlatformDrawForPublicKey(w, in.ModelSource, isPublicMcpKeyCall(r, nil)) {
		return
	}

	// Resolve credentials. Mirrors doProxy's pattern but inlined here
	// to keep the diff focused; the duplication will be eliminated in a
	// later cleanup cycle if it bothers us. (Originally referenced
	// invokeModel, retired in Phase 4d.)
	var providerKind, providerModelName, endpointBaseURL, secret string
	var pricingRaw []byte // Phase 6a-δ — per-model pricing JSONB for the guardrail
	if in.ModelSource == "user_model" {
		var secretCipher string
		err = s.pool.QueryRow(r.Context(), `
SELECT um.provider_kind, um.provider_model_name,
       COALESCE(pc.endpoint_base_url,''), COALESCE(pc.secret_ciphertext,''), um.pricing
FROM user_models um
JOIN provider_credentials pc ON pc.provider_credential_id = um.provider_credential_id
WHERE um.user_model_id=$1 AND um.owner_user_id=$2 AND um.is_active=true AND pc.status='active'
`, modelRef, userID).Scan(&providerKind, &providerModelName, &endpointBaseURL, &secretCipher, &pricingRaw)
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusNotFound, "LLM_MODEL_NOT_FOUND", "user model not found or inactive")
			return
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "failed to resolve model")
			return
		}
		if secretCipher != "" {
			secret, err = s.decryptSecret(secretCipher)
			if err != nil {
				writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "failed to decrypt secret")
				return
			}
		}
	} else if in.ModelSource == "platform_model" {
		err = s.pool.QueryRow(r.Context(), `
SELECT provider_kind, provider_model_name, pricing
FROM platform_models
WHERE platform_model_id=$1 AND status='active'
`, modelRef).Scan(&providerKind, &providerModelName, &pricingRaw)
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusNotFound, "LLM_MODEL_NOT_FOUND", "platform model not found or inactive")
			return
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "failed to resolve model")
			return
		}
	} else {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "invalid model_source")
		return
	}

	adapter, err := provider.ResolveAdapter(providerKind, s.invokeClient)
	if err != nil {
		writeError(w, http.StatusConflict, "LLM_PROVIDER_ROUTE_VIOLATION", "provider route violation")
		return
	}

	// Fail loud if the request carries tool DEFINITIONS but the resolved
	// provider's adapter does not support them — a 400 BEFORE the SSE
	// prelude, so the caller learns early instead of getting a 200 stream
	// that silently dropped the tool definitions. The trigger is a
	// non-empty `tools` array: `tools: []` asks for nothing (and decodes to
	// a non-nil empty slice), and `tool_choice` without tools is inert — so
	// neither trips the guard. (tts requests carry no tools either.)
	if hasToolDefinitions(in.Tools) && !adapter.SupportsTools() {
		writeError(w, http.StatusBadRequest, "LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER",
			"provider '"+providerKind+"' does not support tools/tool_choice")
		return
	}

	// SSE prelude (shared chat + tts). We commit to a 200 here because
	// we have no way to signal HTTP-level errors after the first byte
	// ships; streaming errors are emitted as `event: error` SSE frames
	// instead.
	flusher, ok := w.(http.Flusher)
	if !ok {
		// In production this can't happen (chi + net/http always supply
		// a Flusher) but defensive: if the writer can't flush we cannot
		// stream and must fail loud.
		writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "response writer does not support flushing")
		return
	}

	// Phase 6a-δ — spend-guardrail pre-flight. MUST run before the SSE
	// prelude below: once WriteHeader(200) ships, a 402/404 is impossible.
	// It is also the LAST thing that can fail before streaming, so a
	// successful reserve is always followed by stream + settle.
	estimateInput := in.Input // tts — the input map directly
	if op == "chat" {
		// Mirror exactly what streamChat sends upstream: messages AND tools
		// both consume input tokens. Omitting tools would under-size the
		// reservation and the running tally (/review-impl 6a-δ MED#1).
		estimateInput = map[string]any{"messages": in.Messages}
		if in.Tools != nil {
			estimateInput["tools"] = in.Tools
		}
		if in.MaxTokens != nil && *in.MaxTokens > 0 {
			estimateInput["max_tokens"] = float64(*in.MaxTokens)
		}
	}
	var pricing billing.Pricing
	if len(pricingRaw) > 0 {
		if uErr := json.Unmarshal(pricingRaw, &pricing); uErr != nil {
			writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "invalid model pricing")
			return
		}
	}
	guard, ok := s.preflightStream(w, r, userID, op, in.ModelSource, modelRef, pricing, estimateInput)
	if !ok {
		return // preflightStream wrote the rejection
	}
	// settle runs on every exit — completion, abort, upstream error, or
	// client disconnect. observability.DetachedContext carries the stream's
	// trace context but not r.Context()'s cancellation, so a disconnect
	// cannot cancel the reconcile HTTP call (Phase 6c §5c streaming bridge).
	defer guard.settle(observability.DetachedContext(r.Context()))

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache, no-transform")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no") // disable nginx buffering if proxied
	if in.TraceID != "" {
		w.Header().Set("X-LLM-Trace-Id", in.TraceID)
	}
	w.WriteHeader(http.StatusOK)
	flusher.Flush()

	// M3 (chat disconnect-cancel) — when a chat stream carries a caller-minted
	// stream_job_id, persist a BILLING-NEUTRAL observability row + register a
	// cancellable context so DELETE /internal/llm/jobs/{id} can abort the
	// in-flight stream. reservation_id stays NULL (the `guard` above owns the
	// real spend hold) so finalizing here cannot double-bill. Best-effort: an
	// insert failure logs + degrades to today's uncancellable behavior, never
	// fails the stream. Replacing r's context with the cancellable child means
	// every downstream r.Context() (emit + adapter.Stream) honors BOTH the
	// explicit cancel AND the original client-disconnect.
	var finalizeStream func(streamErr error)
	if op == "chat" && s.jobsRepo != nil && in.StreamJobID != "" {
		if sjid, perr := uuid.Parse(in.StreamJobID); perr != nil {
			slog.Warn("invalid stream_job_id; cancel/observability disabled", "stream_job_id", in.StreamJobID)
		} else if _, ierr := s.jobsRepo.Insert(r.Context(), jobs.InsertParams{
			JobID:       sjid,
			OwnerUserID: userID,
			Operation:   "chat",
			ModelSource: in.ModelSource,
			ModelRef:    modelRef,
			Input:       map[string]any{"stream": true},
			TraceID:     in.TraceID,
			// ReservationID nil — guard.settle is the sole billing authority.
		}); ierr != nil {
			slog.Warn("stream job-row insert failed; cancel/observability disabled",
				"stream_job_id", sjid.String(), "err", ierr)
		} else {
			_, _ = s.jobsRepo.MarkRunning(r.Context(), sjid)
			streamCtx, cancel := context.WithCancel(r.Context())
			s.jobCancels.register(sjid, cancel)
			r = r.WithContext(streamCtx)
			finalizeStream = func(streamErr error) {
				s.jobCancels.remove(sjid)
				cancel()
				status, reason := "completed", "stop"
				switch {
				case streamCtx.Err() != nil:
					// client disconnect OR an explicit DELETE cancel. The
					// FinalizeStreamStatus 'running' guard makes this a no-op
					// when DELETE's Cancel already wrote 'cancelled'.
					status, reason = "cancelled", "client_cancelled"
				case guard.didAbort():
					status, reason = "failed", "budget_exceeded"
				case streamErr != nil:
					status, reason = "failed", "upstream_error"
				}
				// DetachedContext: the stream ctx is cancelled on disconnect, but
				// the terminal write MUST still land (mirrors guard.settle, §5c).
				_, _ = s.jobsRepo.FinalizeStreamStatus(
					observability.DetachedContext(r.Context()), sjid, status, reason)
			}
		}
	}

	// Branch on operation — chat uses adapter.Stream, tts uses adapter.Speak.
	switch op {
	case "tts":
		s.streamTts(r, w, flusher, adapter, endpointBaseURL, secret, providerModelName, in.Input)
	default: // "chat"
		streamErr := s.streamChat(r, w, flusher, adapter, endpointBaseURL, secret, providerModelName, in, guard)
		if finalizeStream != nil {
			finalizeStream(streamErr)
		}
	}
}

// buildChatStreamInput maps a streamRequest onto the adapter input map the
// adapter's Stream() reads (same shape as Invoke() input). Pure + unit-testable.
// Optional fields stay ABSENT when unset; reasoning_effort / chat_template_kwargs
// are threaded so forwardOptionalChatFields forwards them to the provider (e.g.
// reasoning_effort:"none" to disable hidden thinking on reasoning models).
func buildChatStreamInput(in streamRequest) map[string]any {
	input := map[string]any{
		"messages": in.Messages,
	}
	if in.Temperature != nil {
		input["temperature"] = *in.Temperature
	}
	// Policy: max_tokens=0 means "let the model decide" — same as omitting.
	// Prevents the footgun of sending `max_tokens: 0` to upstream providers that
	// interpret it as "cap output at 0".
	if in.MaxTokens != nil && *in.MaxTokens > 0 {
		input["max_tokens"] = *in.MaxTokens
	}
	if in.Tools != nil {
		input["tools"] = in.Tools
	}
	if in.ToolChoice != nil {
		input["tool_choice"] = in.ToolChoice
	}
	if in.ReasoningEffort != nil {
		input["reasoning_effort"] = *in.ReasoningEffort
	}
	if in.ChatTemplateKwargs != nil {
		input["chat_template_kwargs"] = in.ChatTemplateKwargs
	}
	if in.ResponseFormat != nil {
		input["response_format"] = in.ResponseFormat
	}
	return input
}

// streamChat — Phase 1a chat streaming, factored out so doLlmStream can
// branch on operation. Identical to the pre-Phase-5a inline body.
func (s *Server) streamChat(
	r *http.Request,
	w http.ResponseWriter,
	flusher http.Flusher,
	adapter provider.Adapter,
	endpointBaseURL, secret, providerModelName string,
	in streamRequest,
	guard *streamGuard,
) error {
	input := buildChatStreamInput(in)
	// P0-2 (B1) — capture the assembled provider request (post-injection: messages
	// already carry the system + context prompt the caller built) as the audit input
	// payload, bounded so a huge context is logged by reference.
	guard.captureRequest(boundedPayload(input))

	emit := func(chunk provider.StreamChunk) error {
		select {
		case <-r.Context().Done():
			return r.Context().Err()
		default:
		}
		// Phase 6a-δ — account the chunk against the spend tally; a budget
		// runaway hard-aborts. The aborting chunk's content is dropped (we
		// emit the error frame instead) — an acceptable trim of the last
		// delta.
		if guard.observe(chunk) {
			abortFrame := provider.StreamChunk{
				Kind:    provider.StreamChunkError,
				Code:    "LLM_QUOTA_EXCEEDED",
				Message: "stream aborted — budget exceeded",
			}
			raw, _ := json.Marshal(abortFrame)
			_, _ = fmt.Fprintf(w, "event: %s\ndata: %s\n\n", abortFrame.Kind, raw)
			flusher.Flush()
			return errStreamBudgetExceeded
		}
		raw, err := json.Marshal(chunk)
		if err != nil {
			return err
		}
		if _, err := fmt.Fprintf(w, "event: %s\ndata: %s\n\n", chunk.Kind, raw); err != nil {
			return err
		}
		flusher.Flush()
		return nil
	}

	err := adapter.Stream(r.Context(), endpointBaseURL, secret, providerModelName, input, emit)
	if err != nil {
		// A budget abort already emitted its own error frame; a client
		// disconnect means nobody is listening. In both cases, do not
		// emit a second (misleading) error frame. The error is still
		// RETURNED so doLlmStream's M3 finalize can classify the outcome.
		if guard.didAbort() || errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
			return err
		}
		code := "LLM_UPSTREAM_ERROR"
		message := err.Error()
		if errors.Is(err, provider.ErrStreamNotSupported) {
			code = "LLM_STREAM_NOT_SUPPORTED"
		}
		_ = emit(provider.StreamChunk{
			Kind:    provider.StreamChunkError,
			Code:    code,
			Message: message,
		})
	}
	// P0-2 (B2) — classify the terminal outcome so the deferred guard.settle records
	// the real request_status (settle runs after streamChat returns).
	guard.finalizeOutcome(err)
	return err
}

// streamTts — Phase 5a TTS streaming. Calls adapter.Speak emitting one
// SSE `audio-chunk` frame per AudioChunk + a final `done` frame.
//
// Disconnect handling: the emit closure checks r.Context() before each
// write; client disconnect propagates back through Speak, which closes
// the upstream connection.
//
// Adapter errors after SSE prelude are emitted as `event: error` frames
// (we can't change HTTP status post-prelude). Pre-prelude validation
// already happened in doLlmStream; this path assumes a valid request.
func (s *Server) streamTts(
	r *http.Request,
	w http.ResponseWriter,
	flusher http.Flusher,
	adapter provider.Adapter,
	endpointBaseURL, secret, providerModelName string,
	input map[string]any,
) {
	// Decode input. text is required (already validated by doLlmStream);
	// voice/speed/format have adapter-side defaults but we surface them
	// so the wire payload is reproducible.
	text, _ := input["text"].(string)
	voice, _ := input["voice"].(string)
	format, _ := input["format"].(string)
	speed := 1.0
	if v, ok := input["speed"].(float64); ok && v > 0 {
		speed = v
	}

	speakInput := provider.SpeakInput{
		Text:   text,
		Voice:  voice,
		Speed:  speed,
		Format: format,
	}

	emit := func(c provider.AudioChunk) error {
		select {
		case <-r.Context().Done():
			return r.Context().Err()
		default:
		}
		// AudioChunkEvent payload mirrors the openapi schema.
		// `data` is base64-encoded since SSE is text-only by spec.
		payload := map[string]any{
			"sequence_id": c.SequenceID,
			"data":        base64StdEncode(c.Data),
			"final":       c.Final,
		}
		raw, err := json.Marshal(payload)
		if err != nil {
			return err
		}
		if _, err := fmt.Fprintf(w, "event: audio-chunk\ndata: %s\n\n", raw); err != nil {
			return err
		}
		flusher.Flush()
		return nil
	}

	err := adapter.Speak(r.Context(), endpointBaseURL, secret, providerModelName, speakInput, emit)
	if err != nil {
		// /review-impl LOW#5 — when the error is caller-disconnect
		// (ctx cancelled/deadline), don't emit a misleading SSE error
		// frame. The client is gone; the write would fail silently and
		// log noise would mask the real cause in triage.
		if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
			return
		}
		// /review-impl MED#3 — map typed upstream errors to canonical
		// SSE codes so FE/SDK consumers can branch on code, not
		// error.Error() text.
		code := classifySpeakErrorCode(err)
		errPayload := map[string]any{
			"event":   "error",
			"code":    code,
			"message": err.Error(),
		}
		raw, _ := json.Marshal(errPayload)
		_, _ = fmt.Fprintf(w, "event: error\ndata: %s\n\n", raw)
		flusher.Flush()
		return
	}

	// Closing `done` frame so the consumer iterator terminates cleanly.
	donePayload := map[string]any{"event": "done"}
	doneRaw, _ := json.Marshal(donePayload)
	_, _ = fmt.Fprintf(w, "event: done\ndata: %s\n\n", doneRaw)
	flusher.Flush()
}

// classifySpeakErrorCode — Phase 5a /review-impl MED#3. Maps adapter.Speak
// errors to canonical LLM_* codes for the SSE error frame. Mirrors
// classifyAudioError in worker_audio.go (jobs pkg) — kept here as a
// separate function to avoid an api → jobs import cycle.
func classifySpeakErrorCode(err error) string {
	if errors.Is(err, provider.ErrOperationNotSupported) {
		return "LLM_OPERATION_NOT_SUPPORTED"
	}
	var rl *provider.ErrUpstreamRateLimited
	if errors.As(err, &rl) {
		return "LLM_RATE_LIMITED"
	}
	var perm *provider.ErrUpstreamPermanent
	if errors.As(err, &perm) {
		if perm.StatusCode == 401 || perm.StatusCode == 403 {
			return "LLM_AUTH_FAILED"
		}
	}
	return "LLM_UPSTREAM_ERROR"
}
