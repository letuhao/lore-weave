package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

// Public MCP human-approval queue (P4 / OD-2, docs/specs/2026-06-26-public-mcp/03 §6.3).
//
// A DEFAULT public key (allow_self_confirm=false) that calls a Tier-W "propose" tool
// gets a confirm_token back WITHOUT spending. The mcp-public-gateway edge does NOT hand
// that token to the agent — it diverts the propose here (POST /internal/mcp-keys/approvals)
// and returns the agent only {status:"pending_human_approval", approval_id}. The owner then:
//   - lists their pending approvals (GET /v1/account/mcp-keys/approvals)
//   - APPROVES one → auth replays the confirm_token to the OWNING domain's
//     POST /v1/<domain>/actions/confirm (the only spend path) tagged with X-Mcp-Key-Id so
//     the cost attributes to the AGENT's key, not the human session (the carrier rail, P4-D)
//   - or DENIES → the token is dropped, never replayed.
//
// Tenancy (CLAUDE.md User Boundaries): every owner-facing query filters by
// owner_user_id = the JWT caller; a row that isn't theirs (or doesn't exist) is a uniform
// 404 (anti-oracle, same posture as the audit/revoke paths).

// approvalDefaultTTL bounds how long a queued approval is shown as actionable when the
// edge doesn't supply an explicit expiry. It is ADVISORY: the real gate is the domain's
// own re-verify of the (single-use, expiry-bound) confirm token at execute time.
const approvalDefaultTTL = 30 * time.Minute

// approvalExecuteTimeout caps the replayed confirm. A priced confirm effect (e.g.
// composition.generate) runs the engine IN-PROCESS and can take minutes on a slow local
// model, so this mirrors the generous bearer TTL the effect itself uses (15m) + headroom.
const approvalExecuteTimeout = 16 * time.Minute

type mcpApprovalCreateReq struct {
	KeyID        string          `json:"key_id"`
	OwnerUserID  string          `json:"owner_user_id"`
	ToolName     string          `json:"tool_name"`
	Domain       string          `json:"domain"`
	ConfirmToken string          `json:"confirm_token"`
	Preview      json.RawMessage `json:"preview,omitempty"`
	CostEstimate *float64        `json:"cost_estimate_usd,omitempty"`
	ExpiresAt    string          `json:"expires_at,omitempty"` // RFC3339; defaults to now+TTL
}

type mcpApprovalView struct {
	ApprovalID   string          `json:"approval_id"`
	KeyID        string          `json:"key_id"`
	ToolName     string          `json:"tool_name"`
	Domain       string          `json:"domain"`
	Preview      json.RawMessage `json:"preview"`
	CostEstimate *float64        `json:"cost_estimate_usd,omitempty"`
	Status       string          `json:"status"`
	ExpiresAt    string          `json:"expires_at"`
	CreatedAt    string          `json:"created_at"`
	DecidedAt    *string         `json:"decided_at,omitempty"`
}

// internalCreateApproval — POST /internal/mcp-keys/approvals (X-Internal-Token).
// The edge diverts a default key's Tier-W propose here. Inserts a pending row and fires a
// best-effort notification; returns {approval_id} so the edge can hand it to the agent.
func (s *Server) internalCreateApproval(w http.ResponseWriter, r *http.Request) {
	var req mcpApprovalCreateReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid json")
		return
	}
	keyID, err := uuid.Parse(req.KeyID)
	if err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid key_id")
		return
	}
	ownerID, err := uuid.Parse(req.OwnerUserID)
	if err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid owner_user_id")
		return
	}
	if req.ToolName == "" || req.Domain == "" || req.ConfirmToken == "" {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "tool_name, domain and confirm_token are required")
		return
	}
	expiresAt := time.Now().Add(approvalDefaultTTL)
	if req.ExpiresAt != "" {
		if t, perr := time.Parse(time.RFC3339, req.ExpiresAt); perr == nil {
			expiresAt = t
		}
	}
	var preview []byte = []byte("{}")
	if len(req.Preview) > 0 {
		preview = req.Preview
	}

	var approvalID uuid.UUID
	err = s.pool.QueryRow(r.Context(), `
		INSERT INTO mcp_pending_approvals
			(key_id, owner_user_id, tool_name, domain, confirm_token, preview, cost_estimate_usd, expires_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		RETURNING approval_id`,
		keyID, ownerID, req.ToolName, req.Domain, req.ConfirmToken, preview, req.CostEstimate, expiresAt,
	).Scan(&approvalID)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "approval insert failed")
		return
	}

	// Fire-and-forget owner notification (best-effort — never block/fail the divert).
	go s.notifyApprovalPending(ownerID, approvalID, req.ToolName)

	writeJSON(w, http.StatusCreated, map[string]any{"approval_id": approvalID.String()})
}

// internalSelfConfirm — POST /internal/mcp-keys/confirm (X-Internal-Token).
//
// The mcp-public-gateway edge calls this when a key with BOTH `write_confirm` and
// `allow_self_confirm` executes a Tier-W action via the `confirm_action(token, domain)`
// tool — the AGENT is the second actor (no human queue). The edge has already verified
// the dual flags; this replays the token to the owning domain's confirm route tagged with
// `X-Mcp-Key-Id` so the spend attributes to the agent's key (the carrier rail). No approval
// row is created — self-confirm bypasses the OD-2 queue entirely.
func (s *Server) internalSelfConfirm(w http.ResponseWriter, r *http.Request) {
	var req struct {
		KeyID        string `json:"key_id"`
		OwnerUserID  string `json:"owner_user_id"`
		Domain       string `json:"domain"`
		ConfirmToken string `json:"confirm_token"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid json")
		return
	}
	keyID, err := uuid.Parse(req.KeyID)
	if err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid key_id")
		return
	}
	ownerID, err := uuid.Parse(req.OwnerUserID)
	if err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid owner_user_id")
		return
	}
	if req.Domain == "" || req.ConfirmToken == "" {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "domain and confirm_token are required")
		return
	}
	baseURL, ok := s.cfg.DomainConfirmServiceURLs[req.Domain]
	if !ok || baseURL == "" {
		writeErr(w, http.StatusUnprocessableEntity, "AUTH_CONFIRM_DOMAIN_UNROUTABLE", "this action's domain is not executable on this deployment")
		return
	}
	spendCap := s.lookupKeySpendCap(r.Context(), keyID)
	resp, body, execErr := s.replayConfirm(r.Context(), baseURL, req.Domain, req.ConfirmToken, ownerID, keyID, spendCap)
	if execErr != nil {
		writeErr(w, http.StatusBadGateway, "AUTH_CONFIRM_EXECUTE_FAILED", "could not reach the action's service")
		return
	}
	writeConfirmReplayResult(w, confirmReplayLabel(resp), body)
}

// confirmReplayLabel maps a domain confirm-replay HTTP status to a terminal label, shared
// by the human-approve and self-confirm paths (the approve path also drives a row update
// off it). 2xx→executed; 409→reprice_required (single-use token can't re-confirm at the
// new price — leave pending / surface); 410→expired; anything else→failed.
func confirmReplayLabel(resp int) string {
	switch {
	case resp >= 200 && resp < 300:
		return "executed"
	case resp == http.StatusConflict:
		return "reprice_required"
	case resp == http.StatusGone:
		return "expired"
	default:
		return "failed"
	}
}

// writeConfirmReplayResult writes the HTTP response for a confirm-replay label so the
// human-approve and self-confirm paths surface the domain result identically.
func writeConfirmReplayResult(w http.ResponseWriter, label string, body []byte) {
	switch label {
	case "executed":
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(map[string]any{"status": "executed", "result": json.RawMessage(orEmptyJSON(body))})
	case "reprice_required":
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusConflict)
		_ = json.NewEncoder(w).Encode(map[string]any{"status": "reprice_required", "detail": json.RawMessage(orEmptyJSON(body))})
	case "expired":
		writeErr(w, http.StatusGone, "AUTH_APPROVAL_EXPIRED", "this confirmation has expired — propose it again")
	default:
		writeErr(w, http.StatusBadGateway, "AUTH_APPROVAL_EXECUTE_FAILED", "the action's service rejected the confirmation")
	}
}

// listMcpApprovals — GET /v1/account/mcp-keys/approvals?status= (JWT, owner-only).
// A pending row past its expiry reads as "expired" (lazy — no sweeper needed).
func (s *Server) listMcpApprovals(w http.ResponseWriter, r *http.Request) {
	claims, err := s.parseAccess(r)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, jwtErrorCode(err), "invalid access token")
		return
	}
	uid, err := uuid.Parse(claims.Subject)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, "AUTH_TOKEN_INVALID", "invalid subject")
		return
	}
	statusFilter := r.URL.Query().Get("status")
	limit := parseIntQuery(r, "limit", 50, 1, 200)
	offset := parseIntQuery(r, "offset", 0, 0, 1_000_000)

	// Build the query: optionally filter by status. "pending" must also exclude rows
	// whose token has expired (those read as "expired"), so the owner's actionable list
	// is honest about what can still be approved.
	q := `
		SELECT approval_id, key_id, tool_name, domain, preview, cost_estimate_usd, status, expires_at, created_at, decided_at
		FROM mcp_pending_approvals
		WHERE owner_user_id = $1`
	args := []any{uid}
	if statusFilter == "pending" {
		q += ` AND status = 'pending' AND expires_at > now()`
	} else if statusFilter != "" {
		q += ` AND status = $2`
		args = append(args, statusFilter)
	}
	q += fmt.Sprintf(` ORDER BY created_at DESC LIMIT $%d OFFSET $%d`, len(args)+1, len(args)+2)
	args = append(args, limit, offset)

	rows, err := s.pool.Query(r.Context(), q, args...)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "approvals read failed")
		return
	}
	defer rows.Close()
	items := []mcpApprovalView{}
	now := time.Now()
	for rows.Next() {
		v, derr := scanApprovalView(rows, now)
		if derr != nil {
			writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "approvals scan failed")
			return
		}
		items = append(items, v)
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

// denyMcpApproval — POST /v1/account/mcp-keys/approvals/{approval_id}/deny (JWT, owner-only).
// Drops the token (never replayed). Only a pending row of the caller's can be denied.
func (s *Server) denyMcpApproval(w http.ResponseWriter, r *http.Request) {
	uid, approvalID, ok := s.approvalOwnerAndID(w, r)
	if !ok {
		return
	}
	tag, err := s.pool.Exec(r.Context(), `
		UPDATE mcp_pending_approvals
		SET status = 'denied', decided_at = now()
		WHERE approval_id = $1 AND owner_user_id = $2 AND status = 'pending'`,
		approvalID, uid)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "deny failed")
		return
	}
	if tag.RowsAffected() == 0 {
		// Not theirs, doesn't exist, or already decided — uniform 404 (anti-oracle).
		writeErr(w, http.StatusNotFound, "AUTH_NOT_FOUND", "approval not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "denied"})
}

// approveMcpApproval — POST /v1/account/mcp-keys/approvals/{approval_id}/approve (JWT, owner-only).
// THE spend point: replays the confirm token to the owning domain's confirm route tagged with
// X-Mcp-Key-Id so cost attributes to the agent's key (P4-D carrier). 2xx → executed.
func (s *Server) approveMcpApproval(w http.ResponseWriter, r *http.Request) {
	uid, approvalID, ok := s.approvalOwnerAndID(w, r)
	if !ok {
		return
	}
	// Load the row, owner-scoped (anti-oracle 404 if not theirs / absent).
	var (
		keyID         uuid.UUID
		domain, token string
		status        string
		expiresAt     time.Time
	)
	err := s.pool.QueryRow(r.Context(), `
		SELECT key_id, domain, confirm_token, status, expires_at
		FROM mcp_pending_approvals
		WHERE approval_id = $1 AND owner_user_id = $2`,
		approvalID, uid).Scan(&keyID, &domain, &token, &status, &expiresAt)
	if err != nil {
		writeErr(w, http.StatusNotFound, "AUTH_NOT_FOUND", "approval not found")
		return
	}
	if status != "pending" {
		writeErr(w, http.StatusConflict, "AUTH_APPROVAL_NOT_PENDING", "approval already "+status)
		return
	}
	if time.Now().After(expiresAt) {
		_, _ = s.pool.Exec(r.Context(), `UPDATE mcp_pending_approvals SET status='expired', decided_at=now() WHERE approval_id=$1`, approvalID)
		writeErr(w, http.StatusGone, "AUTH_APPROVAL_EXPIRED", "this approval has expired — ask the agent to propose it again")
		return
	}
	baseURL, ok := s.cfg.DomainConfirmServiceURLs[domain]
	if !ok || baseURL == "" {
		// A deploy/config gap (the domain's service URL isn't wired) — leave pending so it
		// becomes executable once configured; tell the owner clearly.
		writeErr(w, http.StatusUnprocessableEntity, "AUTH_APPROVAL_DOMAIN_UNROUTABLE", "this action's domain is not executable on this deployment")
		return
	}
	// Resolve the key's LIVE per-key spend cap (the key may have been re-capped or revoked
	// since propose — use the current value; a missing key → nil cap = owner guardrail only).
	spendCap := s.lookupKeySpendCap(r.Context(), keyID)

	resp, body, execErr := s.replayConfirm(r.Context(), baseURL, domain, token, uid, keyID, spendCap)
	if execErr != nil {
		writeErr(w, http.StatusBadGateway, "AUTH_APPROVAL_EXECUTE_FAILED", "could not reach the action's service")
		return
	}
	label := confirmReplayLabel(resp)
	// Drive the row's terminal status off the outcome BEFORE writing the response. A
	// reprice (409) leaves the row 'pending' — the single-use token can't re-confirm at
	// the new price, so the owner can deny it and ask the agent to re-propose.
	switch label {
	case "executed":
		_, _ = s.pool.Exec(r.Context(), `UPDATE mcp_pending_approvals SET status='executed', decided_at=now() WHERE approval_id=$1`, approvalID)
	case "expired":
		_, _ = s.pool.Exec(r.Context(), `UPDATE mcp_pending_approvals SET status='expired', decided_at=now() WHERE approval_id=$1`, approvalID)
	case "failed":
		_, _ = s.pool.Exec(r.Context(), `UPDATE mcp_pending_approvals SET status='failed', decided_at=now() WHERE approval_id=$1`, approvalID)
	}
	writeConfirmReplayResult(w, label, body)
}

// --- helpers ---

// approvalOwnerAndID parses the JWT subject + the {approval_id} path param. On any failure
// it writes the error response and returns ok=false.
func (s *Server) approvalOwnerAndID(w http.ResponseWriter, r *http.Request) (uuid.UUID, uuid.UUID, bool) {
	claims, err := s.parseAccess(r)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, jwtErrorCode(err), "invalid access token")
		return uuid.Nil, uuid.Nil, false
	}
	uid, err := uuid.Parse(claims.Subject)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, "AUTH_TOKEN_INVALID", "invalid subject")
		return uuid.Nil, uuid.Nil, false
	}
	approvalID, err := uuid.Parse(chi.URLParam(r, "approval_id"))
	if err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid approval_id")
		return uuid.Nil, uuid.Nil, false
	}
	return uid, approvalID, true
}

// lookupKeySpendCap reads a key's current per-key spend cap (nil if the key was revoked/deleted).
func (s *Server) lookupKeySpendCap(ctx context.Context, keyID uuid.UUID) *float64 {
	var cap *float64
	_ = s.pool.QueryRow(ctx, `SELECT spend_cap_usd FROM mcp_api_keys WHERE key_id = $1`, keyID).Scan(&cap)
	return cap
}

// replayConfirm POSTs the approved confirm token to the owning domain's confirm route,
// tagging the AGENT's key so the spend attributes to it (and carries its per-key cap).
// Returns (statusCode, responseBody, transportError).
func (s *Server) replayConfirm(ctx context.Context, baseURL, domain, token string, owner, keyID uuid.UUID, spendCap *float64) (int, []byte, error) {
	target := fmt.Sprintf("%s/v1/%s/actions/confirm?token=%s", baseURL, url.PathEscape(domain), url.QueryEscape(token))
	cctx, cancel := context.WithTimeout(ctx, approvalExecuteTimeout)
	defer cancel()
	httpReq, err := http.NewRequestWithContext(cctx, http.MethodPost, target, nil)
	if err != nil {
		return 0, nil, err
	}
	httpReq.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	httpReq.Header.Set("X-User-Id", owner.String())
	httpReq.Header.Set("X-Mcp-Key-Id", keyID.String())
	if spendCap != nil {
		httpReq.Header.Set("X-Mcp-Spend-Cap-Usd", fmt.Sprintf("%g", *spendCap))
	}
	client := &http.Client{Timeout: approvalExecuteTimeout}
	resp, err := client.Do(httpReq)
	if err != nil {
		return 0, nil, err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20)) // cap 1MiB
	return resp.StatusCode, body, nil
}

// notifyApprovalPending fires a best-effort owner notification (HTTP ingest, no broker).
func (s *Server) notifyApprovalPending(owner, approvalID uuid.UUID, toolName string) {
	if s.cfg.NotificationServiceInternalURL == "" || s.cfg.InternalServiceToken == "" {
		return
	}
	meta, _ := json.Marshal(map[string]any{"approval_id": approvalID.String(), "tool_name": toolName})
	payload, _ := json.Marshal(map[string]any{
		"user_id":  owner.String(),
		"category": "mcp_approval",
		"title":    "Agent action awaiting your approval",
		"body":     "An MCP agent requested: " + toolName + ". Review and approve or deny it.",
		"metadata": json.RawMessage(meta),
	})
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		s.cfg.NotificationServiceInternalURL+"/internal/notifications/", bytes.NewReader(payload))
	if err != nil {
		return
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	resp, err := (&http.Client{Timeout: 3 * time.Second}).Do(req)
	if err != nil {
		return
	}
	_ = resp.Body.Close()
}

// scanApprovalView reads one row into a view, projecting a pending-but-expired row to "expired".
func scanApprovalView(row interface {
	Scan(dest ...any) error
}, now time.Time) (mcpApprovalView, error) {
	var (
		v          mcpApprovalView
		approvalID uuid.UUID
		keyID      uuid.UUID
		preview    []byte
		cost       *float64
		expiresAt  time.Time
		createdAt  time.Time
		decidedAt  *time.Time
	)
	if err := row.Scan(&approvalID, &keyID, &v.ToolName, &v.Domain, &preview, &cost, &v.Status, &expiresAt, &createdAt, &decidedAt); err != nil {
		return mcpApprovalView{}, err
	}
	v.ApprovalID = approvalID.String()
	v.KeyID = keyID.String()
	v.Preview = orEmptyJSON(preview)
	v.CostEstimate = cost
	if v.Status == "pending" && now.After(expiresAt) {
		v.Status = "expired"
	}
	v.ExpiresAt = expiresAt.UTC().Format(time.RFC3339)
	v.CreatedAt = createdAt.UTC().Format(time.RFC3339)
	if decidedAt != nil {
		s := decidedAt.UTC().Format(time.RFC3339)
		v.DecidedAt = &s
	}
	return v, nil
}

// orEmptyJSON returns b, or `{}` when b is empty/nil (so a JSONB column never serializes to null).
func orEmptyJSON(b []byte) json.RawMessage {
	if len(b) == 0 {
		return json.RawMessage("{}")
	}
	return json.RawMessage(b)
}
