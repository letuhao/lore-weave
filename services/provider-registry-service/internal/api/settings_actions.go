package api

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

// NET-NEW per-provider Tier-W confirm + preview routes (C-CONFIRM). The settings
// MCP server's Tier-W tool (settings_model_delete) only MINTS a confirm token; this
// pair is the ONLY write path (INV-9). Both are JWT-gated (the user's browser
// token) — the MCP/mint path can never call them, so the LLM can't self-confirm.
//
// confirm order (carried from the glossary class-C spine): verify token → re-check
// user == caller → check single-use ledger → re-validate + run effect. The
// descriptor is the confused-deputy guard: a token minted for settings.model_delete
// can confirm nothing else.

type settingsConfirmReq struct {
	ConfirmToken string `json:"confirm_token"`
}

type settingsPreviewRow struct {
	Label string `json:"label"`
	Value string `json:"value"`
	Note  string `json:"note,omitempty"`
}
type settingsActionPreview struct {
	Descriptor  string               `json:"descriptor"`
	Title       string               `json:"title"`
	PreviewRows []settingsPreviewRow `json:"preview_rows"`
	Destructive bool                 `json:"destructive"`
}

// tokenHash is the single-use ledger key for a stateless confirm token (the kit
// token carries no jti). SHA-256 over the full token string.
func tokenHash(tok string) string {
	sum := sha256.Sum256([]byte(tok))
	return hex.EncodeToString(sum[:])
}

// resolveConfirmCaller returns the redeeming user's ID for the settings confirm
// route, trusting EITHER a valid Bearer JWT (browser UI) or a trusted
// internal-service envelope (X-Internal-Token, constant-time compare, +
// X-User-Id) — the shape auth-service's public-MCP confirm-replay
// (mcp_approvals.go::replayConfirm) sends, since it is a trusted internal
// caller and can never present the owner's Bearer JWT. Mirrors
// glossary-service/book-service's identical retrofit and
// composition/translation/knowledge-service's existing Python dual-auth
// pattern (D-PMCP-WORKER-CARRIER). Found live 2026-07-08: this route 401'd
// every confirm-replay unconditionally (comment above said "the MCP/mint path
// can never call them" — true for propose, but the REPLAY path is a distinct,
// legitimate trusted-internal caller this route never accounted for). The
// internal-token branch fails closed (never falls through to Bearer) if
// X-User-Id is missing/malformed.
func (s *Server) resolveConfirmCaller(r *http.Request) (uuid.UUID, bool) {
	return lwmcp.ResolveEnvelopeOrBearerCaller(r, s.cfg.InternalServiceToken, s.auth)
}

// decodeSettingsConfirm reads + verifies the confirm token — from the `token`
// query param (auth-service's internal confirm-replay, nil body) or the JSON
// body `{confirm_token}` (the browser UI) — re-checks user==caller and the
// descriptor. Writes the 4xx itself and returns ok=false on any failure. Also
// returns the raw token string for the single-use ledger key.
func (s *Server) decodeSettingsConfirm(w http.ResponseWriter, r *http.Request, userID uuid.UUID) (lwmcp.ConfirmClaims, string, bool) {
	token := strings.TrimSpace(r.URL.Query().Get("token"))
	if token == "" {
		var body settingsConfirmReq
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil || strings.TrimSpace(body.ConfirmToken) == "" {
			writeError(w, http.StatusBadRequest, "SETTINGS_VALIDATION", "confirm_token is required")
			return lwmcp.ConfirmClaims{}, "", false
		}
		token = body.ConfirmToken
	}
	claims, err := lwmcp.VerifyConfirmToken(s.cfg.ConfirmTokenSigningSecret, token)
	if errors.Is(err, lwmcp.ErrConfirmTokenExpired) {
		writeError(w, http.StatusUnprocessableEntity, "SETTINGS_ACTION_TOKEN", "confirmation expired — propose again")
		return lwmcp.ConfirmClaims{}, "", false
	}
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "SETTINGS_ACTION_TOKEN", "invalid confirmation")
		return lwmcp.ConfirmClaims{}, "", false
	}
	// Bound to the proposer — a different signed-in user cannot redeem it even with
	// the string (checked BEFORE consuming so a stranger can't burn it).
	if claims.UserID != userID {
		writeError(w, http.StatusForbidden, "SETTINGS_FORBIDDEN", "confirmation not valid for this user")
		return lwmcp.ConfirmClaims{}, "", false
	}
	if claims.Descriptor != settingsConfirmDescriptor {
		writeError(w, http.StatusUnprocessableEntity, "SETTINGS_ACTION_TOKEN", "unknown action")
		return lwmcp.ConfirmClaims{}, "", false
	}
	return claims, token, true
}

// confirmSettingsAction handles POST /v1/settings/actions/confirm — the token-gated,
// single-use Tier-W write path. Currently the only descriptor is
// settings.model_delete.
func (s *Server) confirmSettingsAction(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.resolveConfirmCaller(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	claims, rawToken, ok := s.decodeSettingsConfirm(w, r, userID)
	if !ok {
		return
	}
	// Single-use: claim the token hash now (BEFORE the effect). A replay → 0 rows.
	claimed, err := s.consumeSettingsToken(r.Context(), tokenHash(rawToken), claims.Descriptor, time.Unix(claims.Exp, 0))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "SETTINGS_INTERNAL", "confirmation failed")
		return
	}
	if !claimed {
		writeError(w, http.StatusUnprocessableEntity, "SETTINGS_ACTION_TOKEN", "already confirmed — propose again")
		return
	}

	switch claims.Descriptor {
	case settingsConfirmDescriptor:
		s.effectModelDelete(w, r.Context(), userID, claims)
	default:
		writeError(w, http.StatusUnprocessableEntity, "SETTINGS_ACTION_TOKEN", "unknown action")
	}
}

// effectModelDelete performs the actual delete, scoped to the proposing user AND
// the token's bound resource id (defense in depth — the token's ResourceID is the
// model id, re-checked against owner_user_id here).
func (s *Server) effectModelDelete(w http.ResponseWriter, ctx context.Context, userID uuid.UUID, claims lwmcp.ConfirmClaims) {
	tag, err := s.pool.Exec(ctx, `DELETE FROM user_models WHERE user_model_id=$1 AND owner_user_id=$2`, claims.ResourceID, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "SETTINGS_INTERNAL", "delete failed")
		return
	}
	if tag.RowsAffected() == 0 {
		// The model was already deleted between propose and confirm — re-proposable.
		writeError(w, http.StatusUnprocessableEntity, "SETTINGS_ACTION_TOKEN", "the model no longer exists — propose again")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// previewSettingsAction handles POST /v1/settings/actions/preview — JWT-gated,
// read-only, NEVER consumes the token. Re-renders the confirm card from CURRENT
// state so the human confirms against what is true now.
func (s *Server) previewSettingsAction(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	claims, _, ok := s.decodeSettingsConfirm(w, r, userID)
	if !ok {
		return
	}
	switch claims.Descriptor {
	case settingsConfirmDescriptor:
		s.previewModelDelete(w, r.Context(), userID, claims)
	default:
		writeError(w, http.StatusUnprocessableEntity, "SETTINGS_ACTION_TOKEN", "unknown action")
	}
}

func (s *Server) previewModelDelete(w http.ResponseWriter, ctx context.Context, userID uuid.UUID, claims lwmcp.ConfirmClaims) {
	var alias *string
	var providerModelName, providerKind string
	err := s.pool.QueryRow(ctx, `
SELECT alias, provider_model_name, provider_kind FROM user_models
WHERE user_model_id=$1 AND owner_user_id=$2`, claims.ResourceID, userID).Scan(&alias, &providerModelName, &providerKind)
	out := settingsActionPreview{Descriptor: settingsConfirmDescriptor, Destructive: true, Title: "Delete model"}
	if errors.Is(err, pgx.ErrNoRows) {
		out.PreviewRows = []settingsPreviewRow{{Label: "status", Value: "already removed", Note: "nothing to delete — this model no longer exists"}}
		writeJSON(w, http.StatusOK, out)
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "SETTINGS_INTERNAL", "preview failed")
		return
	}
	label := providerModelName
	if alias != nil && *alias != "" {
		label = *alias
	}
	out.Title = "Delete model " + label
	out.PreviewRows = []settingsPreviewRow{
		{Label: "model", Value: label},
		{Label: "provider", Value: providerKind},
		{Label: "provider model name", Value: providerModelName},
	}
	writeJSON(w, http.StatusOK, out)
}

// consumeSettingsToken records the token hash, enforcing single-use. Returns
// claimed=true the first time; a replay hits the PK (ON CONFLICT DO NOTHING → 0
// rows) → claimed=false.
func (s *Server) consumeSettingsToken(ctx context.Context, hash, descriptor string, exp time.Time) (bool, error) {
	tag, err := s.pool.Exec(ctx,
		`INSERT INTO settings_consumed_tokens (token_hash, descriptor, exp) VALUES ($1,$2,$3)
		 ON CONFLICT (token_hash) DO NOTHING`, hash, descriptor, exp)
	if err != nil {
		return false, err
	}
	return tag.RowsAffected() > 0, nil
}
