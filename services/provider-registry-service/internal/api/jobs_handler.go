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
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/loreweave/provider-registry-service/internal/jobs"
)

func nowRFC3339Nano() string { return time.Now().UTC().Format(time.RFC3339Nano) }

// validJobOperations mirrors the openapi JobOperation enum.
var validJobOperations = map[string]struct{}{
	"chat": {}, "completion": {}, "embedding": {},
	"stt": {}, "tts": {}, "image_gen": {},
	"entity_extraction": {}, "relation_extraction": {},
	"event_extraction": {}, "translation": {},
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
	if s.jobsRepo == nil || s.jobsWorker == nil {
		writeError(w, http.StatusServiceUnavailable, "LLM_INTERNAL_ERROR", "jobs subsystem not initialized")
		return
	}
	var in jobSubmitRequest
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "invalid JSON body")
		return
	}
	if _, ok := validJobOperations[in.Operation]; !ok {
		writeError(w, http.StatusBadRequest, "LLM_INVALID_REQUEST", "invalid or missing operation")
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

	// Spawn the worker goroutine. Use a fresh context detached from the
	// inbound HTTP request so the goroutine survives the response.
	go func() {
		bgCtx := context.Background()
		s.jobsWorker.Process(bgCtx, jobID, userID, in.Operation, in.ModelSource, modelRef, in.Input)
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
