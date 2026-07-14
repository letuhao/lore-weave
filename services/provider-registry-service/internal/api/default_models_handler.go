package api

import (
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// Per-user DEFAULT model per capability (D-RERANK-NOT-BYOK follow-up). Restores
// the default-reranker UX the removed RERANK_URL/_MODEL .env config provided, the
// BYOK way: the default is the user's own user_model, resolved through this
// service. Consumers (raw search in knowledge-service + glossary-service) read
// GET /internal/default-models/{capability}; users set it from Settings.

// defaultModelCapabilities is the whitelist of capabilities that support a
// user-level default. Keep in sync with the FE pickers' capability strings.
var defaultModelCapabilities = map[string]bool{
	"rerank":    true,
	"embedding": true,
	// "chat" — the user's default conversation model (W5 shared ModelPicker wave):
	// new chat sessions preselect it; settable from the Settings default-models card.
	"chat": true,
	// "planner" — the capable chat+tool model the glossary plan-and-execute planner
	// (glossary_plan) uses; a per-user default so planning isn't stuck on the chat
	// "Fast" model (D-1). Set from Settings; resolved via /internal/default-models.
	"planner": true,
	// "distill" (WS-3.0 / DBT-15 · Q8) — the model the headless journal DISTILLER uses. A per-user
	// default so a scheduled "end my day" resolves a NON-reasoning chat model (a reasoning model emits
	// only reasoning_content → an empty diary). A ROLE, not a model flag → validated against 'chat'
	// (like planner); the caller falls back to the 'chat' default when unset.
	"distill": true,
}

// defaultModelCapQuery is THE capability-validation rule for assigning a
// default model — shared by the HTTP route (putDefaultModel) and the MCP tool
// (toolModelSetDefault) so the two can never diverge (review-impl W5 #2: the
// MCP tool inherited the "chat" whitelist without the '{}' parity and the
// planner→chat mapping, rejecting models the picker offers).
//   - `planner` is a ROLE, not a model flag — validated against 'chat'
//     (D-PLAN-PLANNER-DEFAULT-FE).
//   - chat (incl. planner) admits undeclared '{}' flags, mirroring
//     listUserModels — the picker must never offer a model this rejects.
//   - non-chat capabilities stay strict (canonical flag or legacy _capability).
// Returns (query, capJSON, validateCap); query params: $1 model, $2 owner,
// $3 capJSON, $4 validateCap.
func defaultModelCapQuery(capability string) (query, capJSON, validateCap string) {
	validateCap = capability
	// planner + distill are ROLES that run as a chat call → validated against the 'chat' flag, so the
	// picker's chat models are all assignable (WS-3.0 adds distill; D-PLAN-PLANNER-DEFAULT-FE added planner).
	if capability == "planner" || capability == "distill" {
		validateCap = "chat"
	}
	capJSON = fmt.Sprintf(`{"%s":true}`, validateCap)
	query = `
SELECT 1 FROM user_models
WHERE user_model_id=$1 AND owner_user_id=$2 AND is_active=true
  AND (capability_flags @> $3::jsonb OR capability_flags->>'_capability' = $4)`
	if validateCap == "chat" {
		query = `
SELECT 1 FROM user_models
WHERE user_model_id=$1 AND owner_user_id=$2 AND is_active=true
  AND (capability_flags @> $3::jsonb OR capability_flags->>'_capability' = $4 OR capability_flags = '{}'::jsonb)`
	}
	return query, capJSON, validateCap
}

// getDefaultModels — GET /v1/model-registry/default-models (JWT). Returns the
// caller's still-valid defaults (a dangling default whose model was deleted is
// already cascaded away by the FK, so a JOIN here is belt-and-suspenders).
func (s *Server) getDefaultModels(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	rows, err := s.pool.Query(r.Context(), `
SELECT d.capability, d.user_model_id
FROM user_default_models d
JOIN user_models um ON um.user_model_id = d.user_model_id
WHERE d.owner_user_id = $1`, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DEFAULT_MODELS_QUERY_FAILED", "failed to load defaults")
		return
	}
	defer rows.Close()
	defaults := map[string]string{}
	for rows.Next() {
		var cap string
		var modelID uuid.UUID
		if err := rows.Scan(&cap, &modelID); err != nil {
			writeError(w, http.StatusInternalServerError, "DEFAULT_MODELS_SCAN_FAILED", "scan failed")
			return
		}
		defaults[cap] = modelID.String()
	}
	writeJSON(w, http.StatusOK, map[string]any{"defaults": defaults})
}

// putDefaultModel — PUT /v1/model-registry/default-models/{capability} (JWT).
// Body {"user_model_id": "<uuid>"} sets the default (validating the model is the
// caller's and carries the capability); {"user_model_id": null} clears it.
func (s *Server) putDefaultModel(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	capability := chi.URLParam(r, "capability")
	if !defaultModelCapabilities[capability] {
		writeError(w, http.StatusBadRequest, "DEFAULT_MODELS_BAD_CAPABILITY", "unsupported capability")
		return
	}
	var in struct {
		UserModelID *string `json:"user_model_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "DEFAULT_MODELS_VALIDATION", "invalid payload")
		return
	}

	// Clear when null/empty.
	if in.UserModelID == nil || *in.UserModelID == "" {
		if _, err := s.pool.Exec(r.Context(),
			`DELETE FROM user_default_models WHERE owner_user_id=$1 AND capability=$2`,
			userID, capability); err != nil {
			writeError(w, http.StatusInternalServerError, "DEFAULT_MODELS_CLEAR_FAILED", "failed to clear default")
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"capability": capability, "user_model_id": nil})
		return
	}

	modelID, err := uuid.Parse(*in.UserModelID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "DEFAULT_MODELS_VALIDATION", "invalid user_model_id")
		return
	}
	// The model must be the caller's, active, and carry the capability. `planner` is a
	// ROLE, not a model capability flag — no model is tagged {"planner":true}; any chat
	// (ideally tool-calling) model can plan. So validate the 'planner' default against the
	// 'chat' flag instead (D-PLAN-PLANNER-DEFAULT-FE), matching the FE picker which offers
	// the user's chat models. Match BOTH capability_flags schemas (canonical {"cap":true}
	// + legacy {"_capability":"cap"}) so a model the picker offered isn't rejected here.
	capQuery, capJSON, validateCap := defaultModelCapQuery(capability)
	var exists int
	err = s.pool.QueryRow(r.Context(), capQuery,
		modelID, userID, capJSON, validateCap).Scan(&exists)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusBadRequest, "DEFAULT_MODELS_MODEL_INVALID", "model not found, inactive, or lacks the capability")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DEFAULT_MODELS_QUERY_FAILED", "failed to validate model")
		return
	}

	if _, err := s.pool.Exec(r.Context(), `
INSERT INTO user_default_models (owner_user_id, capability, user_model_id, updated_at)
VALUES ($1, $2, $3, now())
ON CONFLICT (owner_user_id, capability)
DO UPDATE SET user_model_id = EXCLUDED.user_model_id, updated_at = now()`,
		userID, capability, modelID); err != nil {
		writeError(w, http.StatusInternalServerError, "DEFAULT_MODELS_SAVE_FAILED", "failed to save default")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"capability": capability, "user_model_id": modelID.String()})
}

// internalGetDefaultModel — GET /internal/default-models/{capability}?user_id=
// (X-Internal-Token). Returns the user's default model for the capability so a
// consumer can fall back to it when no scope-specific model is set. 404 when none.
func (s *Server) internalGetDefaultModel(w http.ResponseWriter, r *http.Request) {
	capability := chi.URLParam(r, "capability")
	if !defaultModelCapabilities[capability] {
		writeError(w, http.StatusBadRequest, "DEFAULT_MODELS_BAD_CAPABILITY", "unsupported capability")
		return
	}
	userIDStr := r.URL.Query().Get("user_id")
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "DEFAULT_MODELS_VALIDATION", "invalid user_id")
		return
	}
	var modelID uuid.UUID
	err = s.pool.QueryRow(r.Context(), `
SELECT d.user_model_id
FROM user_default_models d
JOIN user_models um ON um.user_model_id = d.user_model_id AND um.is_active = true
WHERE d.owner_user_id = $1 AND d.capability = $2`, userID, capability).Scan(&modelID)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "DEFAULT_MODEL_NOT_SET", "no default model for this capability")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DEFAULT_MODELS_QUERY_FAILED", "failed to resolve default")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"user_model_id": modelID.String(), "model_source": "user_model"})
}

// internalResolvePlannerModel — GET /internal/planner-model?user_id= (X-Internal-Token).
// Resolves the model the glossary plan-and-execute planner should use, WITH a
// sensible fallback so the feature works out of the box (MED-6): the user's explicit
// 'planner' default if they set one (D-1, a strong pinned model), else their best
// active CHAT model (preferring tool_calling, deterministic). 404 only when the user
// has no active chat model at all. The picking lives here because provider-registry
// owns user_models — glossary never queries this DB.
func (s *Server) internalResolvePlannerModel(w http.ResponseWriter, r *http.Request) {
	userID, err := uuid.Parse(r.URL.Query().Get("user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "DEFAULT_MODELS_VALIDATION", "invalid user_id")
		return
	}
	// 1. Explicit 'planner' default (a power user pinned a strong model).
	var modelID uuid.UUID
	err = s.pool.QueryRow(r.Context(), `
SELECT d.user_model_id
FROM user_default_models d
JOIN user_models um ON um.user_model_id = d.user_model_id AND um.is_active = true
WHERE d.owner_user_id = $1 AND d.capability = 'planner'`, userID).Scan(&modelID)
	if err == nil {
		writeJSON(w, http.StatusOK, map[string]any{
			"user_model_id": modelID.String(), "model_source": "user_model", "source": "planner_default"})
		return
	}
	if err != pgx.ErrNoRows {
		writeError(w, http.StatusInternalServerError, "DEFAULT_MODELS_QUERY_FAILED", "failed to resolve planner default")
		return
	}
	// 2. Fallback: the user's best active chat model. Prefer tool_calling (better at
	// structured planning); break ties deterministically by id. Both capability_flags
	// schemas are honored ({"chat":true} canonical + legacy {"_capability":"chat"}).
	err = s.pool.QueryRow(r.Context(), `
SELECT user_model_id
FROM user_models
WHERE owner_user_id = $1 AND is_active = true
  AND (capability_flags @> '{"chat":true}'::jsonb OR capability_flags->>'_capability' = 'chat')
ORDER BY (capability_flags @> '{"tool_calling":true}'::jsonb) DESC, user_model_id
LIMIT 1`, userID).Scan(&modelID)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "PLANNER_MODEL_NONE", "no active chat model for this user — add one in Settings")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DEFAULT_MODELS_QUERY_FAILED", "failed to resolve a chat model")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"user_model_id": modelID.String(), "model_source": "user_model", "source": "chat_fallback"})
}
