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
	"encoding/json"
	"errors"
	"fmt"
	"net/http"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// streamRequest mirrors the StreamRequest schema in the OpenAPI contract.
type streamRequest struct {
	ModelSource  string         `json:"model_source"`
	ModelRef     string         `json:"model_ref"`
	Messages     any            `json:"messages"`
	Tools        any            `json:"tools,omitempty"`
	Temperature  *float64       `json:"temperature,omitempty"`
	MaxTokens    *int           `json:"max_tokens,omitempty"`
	StreamFormat string         `json:"stream_format,omitempty"`
	TraceID      string         `json:"trace_id,omitempty"`
	// Generic extras passed to adapter (forward-compat for tools, response_format).
	Extra map[string]any `json:"-"`
}

// llmStream — public POST /v1/llm/stream (JWT auth).
func (s *Server) llmStream(w http.ResponseWriter, r *http.Request) {
	userID, _, ok := s.auth(r)
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
	if in.Messages == nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "messages required")
		return
	}
	modelRef, err := uuid.Parse(in.ModelRef)
	if err != nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "invalid model_ref")
		return
	}

	// Resolve credentials. Mirrors invokeModel's pattern but inlined here
	// to keep the diff focused; the duplication will be eliminated in a
	// later cleanup cycle if it bothers us.
	var providerKind, providerModelName, endpointBaseURL, secret string
	if in.ModelSource == "user_model" {
		var secretCipher string
		err = s.pool.QueryRow(r.Context(), `
SELECT um.provider_kind, um.provider_model_name,
       COALESCE(pc.endpoint_base_url,''), COALESCE(pc.secret_ciphertext,'')
FROM user_models um
JOIN provider_credentials pc ON pc.provider_credential_id = um.provider_credential_id
WHERE um.user_model_id=$1 AND um.owner_user_id=$2 AND um.is_active=true AND pc.status='active'
`, modelRef, userID).Scan(&providerKind, &providerModelName, &endpointBaseURL, &secretCipher)
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
SELECT provider_kind, provider_model_name
FROM platform_models
WHERE platform_model_id=$1 AND status='active'
`, modelRef).Scan(&providerKind, &providerModelName)
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

	// Build adapter input map. The adapter's Stream() reads messages,
	// temperature, max_tokens, tools — same shape as Invoke() input.
	input := map[string]any{
		"messages": in.Messages,
	}
	if in.Temperature != nil {
		input["temperature"] = *in.Temperature
	}
	// Policy: max_tokens=0 means "let the model decide" — same as
	// omitting. Prevents the footgun of sending `max_tokens: 0` to
	// upstream providers that interpret it as "cap output at 0".
	if in.MaxTokens != nil && *in.MaxTokens > 0 {
		input["max_tokens"] = *in.MaxTokens
	}
	if in.Tools != nil {
		input["tools"] = in.Tools
	}

	// SSE prelude. We commit to a 200 here because we have no way to
	// signal HTTP-level errors after the first byte ships; streaming
	// errors are emitted as `event: error` SSE frames instead.
	flusher, ok := w.(http.Flusher)
	if !ok {
		// In production this can't happen (chi + net/http always supply
		// a Flusher) but defensive: if the writer can't flush we cannot
		// stream and must fail loud.
		writeError(w, http.StatusInternalServerError, "LLM_INTERNAL_ERROR", "response writer does not support flushing")
		return
	}
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache, no-transform")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no") // disable nginx buffering if proxied
	if in.TraceID != "" {
		w.Header().Set("X-LLM-Trace-Id", in.TraceID)
	}
	w.WriteHeader(http.StatusOK)
	flusher.Flush()

	emit := func(chunk provider.StreamChunk) error {
		// Detect client disconnect early — writing on a dead connection
		// returns an error but we want adapter.Stream() to short-circuit.
		select {
		case <-r.Context().Done():
			return r.Context().Err()
		default:
		}
		raw, err := json.Marshal(chunk)
		if err != nil {
			return err
		}
		// SSE wire format: `event: <name>\ndata: <JSON>\n\n`
		if _, err := fmt.Fprintf(w, "event: %s\ndata: %s\n\n", chunk.Kind, raw); err != nil {
			return err
		}
		flusher.Flush()
		return nil
	}

	err = adapter.Stream(r.Context(), endpointBaseURL, secret, providerModelName, input, emit)
	if err != nil {
		// If we get here AFTER the headers have been written, we cannot
		// change the status code. Best we can do is push an `error` SSE
		// frame so the client can surface a useful message.
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
}
