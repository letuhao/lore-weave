package api

import (
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

// parseIntQuery reads a bounded int query param, falling back to def when the value
// is absent/malformed/out-of-range (i.e. it does NOT clamp — an out-of-range value
// yields def, which keeps the read bounded by [min,max] either way).
func parseIntQuery(r *http.Request, name string, def, min, max int) int {
	v := r.URL.Query().Get(name)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil || n < min || n > max {
		return def
	}
	return n
}

// Public MCP per-key call audit (P3 / H-O). The mcp-public-gateway edge fires a
// best-effort batch of audit rows after each external-agent request; the owner
// reads their own key's call history. See docs/specs/2026-06-26-public-mcp/03 §H-O.

// validMcpAuditOutcomes mirrors the mcp_call_audit.outcome CHECK constraint — an
// unknown outcome is dropped at ingest (defense-in-depth; the DB would reject it
// anyway, but we skip the row rather than fail the whole batch).
var validMcpAuditOutcomes = map[string]bool{
	"relayed": true, "denied_scope": true, "rate_limited": true,
	"unauthorized": true, "upstream_error": true, "tool_error": true,
}

type mcpAuditRowIn struct {
	KeyID       string  `json:"key_id"`
	OwnerUserID string  `json:"owner_user_id"`
	Method      string  `json:"method"`
	ToolName    *string `json:"tool_name,omitempty"`
	Outcome     string  `json:"outcome"`
	TraceID     *string `json:"trace_id,omitempty"`
}

type mcpAuditView struct {
	AuditID   string  `json:"audit_id"`
	Method    string  `json:"method"`
	ToolName  *string `json:"tool_name,omitempty"`
	Outcome   string  `json:"outcome"`
	TraceID   *string `json:"trace_id,omitempty"`
	CreatedAt string  `json:"created_at"`
}

// internalIngestMcpAudit — POST /internal/mcp-keys/audit (X-Internal-Token).
// Accepts a batch (a JSON-RPC batch maps to N rows). Best-effort: malformed/unknown
// rows are skipped, never failing the others; the edge fires this fire-and-forget so
// a 4xx here never affects the agent's response. Returns the count inserted.
func (s *Server) internalIngestMcpAudit(w http.ResponseWriter, r *http.Request) {
	var rows []mcpAuditRowIn
	if err := json.NewDecoder(r.Body).Decode(&rows); err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid json (expected an array)")
		return
	}
	if len(rows) == 0 {
		writeJSON(w, http.StatusOK, map[string]any{"inserted": 0})
		return
	}
	inserted := 0
	for _, row := range rows {
		keyID, err := uuid.Parse(row.KeyID)
		if err != nil {
			continue
		}
		ownerID, err := uuid.Parse(row.OwnerUserID)
		if err != nil {
			continue
		}
		if row.Method == "" || !validMcpAuditOutcomes[row.Outcome] {
			continue
		}
		if _, err := s.pool.Exec(r.Context(), `
			INSERT INTO mcp_call_audit (key_id, owner_user_id, method, tool_name, outcome, trace_id)
			VALUES ($1, $2, $3, $4, $5, $6)`,
			keyID, ownerID, row.Method, row.ToolName, row.Outcome, row.TraceID); err != nil {
			// Best-effort: a single bad row (e.g. owner deleted mid-batch → FK violation)
			// must not lose the rest. Skip and continue.
			continue
		}
		inserted++
	}
	writeJSON(w, http.StatusOK, map[string]any{"inserted": inserted})
}

// listMcpKeyAudit — GET /v1/account/mcp-keys/{key_id}/audit (JWT, owner-only).
// Returns the recent call history for a key the caller OWNS. Owner-scoping is
// enforced in the WHERE (owner_user_id = caller) so a key that isn't theirs (or
// doesn't exist) yields an empty list — same anti-oracle posture as revoke's 404.
func (s *Server) listMcpKeyAudit(w http.ResponseWriter, r *http.Request) {
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
	keyID, err := uuid.Parse(chi.URLParam(r, "key_id"))
	if err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid key_id")
		return
	}
	limit := parseIntQuery(r, "limit", 50, 1, 200)
	offset := parseIntQuery(r, "offset", 0, 0, 1_000_000)

	rows, err := s.pool.Query(r.Context(), `
		SELECT audit_id, method, tool_name, outcome, trace_id, created_at
		FROM mcp_call_audit
		WHERE owner_user_id = $1 AND key_id = $2
		ORDER BY created_at DESC
		LIMIT $3 OFFSET $4`, uid, keyID, limit, offset)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "audit read failed")
		return
	}
	defer rows.Close()
	items := []mcpAuditView{}
	for rows.Next() {
		var (
			auditID         uuid.UUID
			method, outcome string
			toolName, trace *string
			createdAt       time.Time
		)
		if err := rows.Scan(&auditID, &method, &toolName, &outcome, &trace, &createdAt); err != nil {
			writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "audit scan failed")
			return
		}
		items = append(items, mcpAuditView{
			AuditID:   auditID.String(),
			Method:    method,
			ToolName:  toolName,
			Outcome:   outcome,
			TraceID:   trace,
			CreatedAt: createdAt.UTC().Format(time.RFC3339),
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}
