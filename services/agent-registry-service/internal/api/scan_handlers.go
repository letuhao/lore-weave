package api

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/google/uuid"
)

// runScan probes a registered server, lints its tools, and drives the quarantine
// status machine. Returns the scan result + health for the caller to surface.
//
//	probe fails            → status='error'      (unreachable; never federates)
//	probe ok + clean       → status='active'     (cleared to federate)
//	probe ok + HIGH finding → status='suspended' (quarantined; needs accept-risk)
//
// scan_result / last_health / last_scanned_at are always persisted; the catalog
// version bumps so the ai-gateway overlay picks up the new effective set.
func (s *Server) runScan(ctx context.Context, mid uuid.UUID) (scanResult, probeHealth, string, error) {
	var endpoint, authKind, cipher, curStatus string
	var isExternal bool
	var owner *uuid.UUID
	if err := s.db.QueryRow(ctx,
		`SELECT endpoint_url, auth_kind, secret_ciphertext, status, is_external, owner_user_id FROM mcp_server_registrations WHERE mcp_server_id=$1`,
		mid).Scan(&endpoint, &authKind, &cipher, &curStatus, &isExternal, &owner); err != nil {
		return scanResult{}, probeHealth{}, "", err
	}
	secret, _ := s.decryptSecret(cipher)

	// For an INTERNAL loreweave server, mirror the ai-gateway overlay's federation
	// envelope (X-Internal-Token + X-User-Id) so the probe reaches an internal-token-
	// gated /mcp exactly as runtime federation does. External servers get only their
	// own registered auth (handled inside probeMCP).
	var extra map[string]string
	if !isExternal {
		uidStr := ""
		if owner != nil {
			uidStr = owner.String()
		}
		extra = map[string]string{"X-Internal-Token": s.cfg.InternalServiceToken, "X-User-Id": uidStr}
	}

	pctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	tools, health, probeErr := probeMCP(pctx, endpoint, authKind, secret, s.cfg.AllowInternalMcpTargets, extra)

	var res scanResult
	newStatus := curStatus
	if probeErr != nil {
		newStatus = "error"
		res = scanResult{ScannedAt: time.Now().UTC(), Clean: false, Findings: []scanFinding{}, Tools: []scannedTool{}}
	} else {
		res = scanTools(tools)
		if res.Clean {
			newStatus = "active"
		} else {
			newStatus = "suspended"
		}
	}
	scanJSON, _ := json.Marshal(res)
	healthJSON, _ := json.Marshal(health)
	_, _ = s.db.Exec(ctx,
		`UPDATE mcp_server_registrations
		   SET status=$2, scan_result=$3, last_health=$4, last_scanned_at=now(), updated_at=now()
		 WHERE mcp_server_id=$1`,
		mid, newStatus, string(scanJSON), string(healthJSON))
	s.bumpCatalogVersion(ctx)
	return res, health, newStatus, probeErr
}

// scanAsync runs a best-effort scan on a fresh context (used from register so the
// create response isn't blocked on the probe). A wizard flow calls rescan explicitly.
func (s *Server) scanAsync(mid uuid.UUID) {
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		_, _, _, _ = s.runScan(ctx, mid)
	}()
}

// rescanMcpServer — POST /mcp-servers/{id}/rescan. Synchronous: re-probe + re-scan,
// return the verdict. Owner/grant-gated like any write on the row.
func (s *Server) rescanMcpServer(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	mid, ok := parseUUIDParam(w, r, "mcp_server_id")
	if !ok {
		return
	}
	var tier string
	var owner, book *uuid.UUID
	if err := s.db.QueryRow(r.Context(), `SELECT tier, owner_user_id, book_id FROM mcp_server_registrations WHERE mcp_server_id=$1`, mid).Scan(&tier, &owner, &book); err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "server not found")
		return
	}
	if !s.authorizeRowWrite(r, tier, owner, book, uid, role) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "server not found")
		return
	}
	res, health, status, probeErr := s.runScan(r.Context(), mid)
	s.audit(r.Context(), uid, actorKindOf(role), "mcp_server", "rescan", &mid, "", tier, map[string]any{"clean": res.Clean, "status": status})
	resp := map[string]any{"mcp_server_id": mid, "status": status, "scan_result": res, "last_health": health}
	if probeErr != nil {
		resp["probe_error"] = probeErr.Error()
	}
	writeJSON(w, http.StatusOK, resp)
}

// getMcpServer — GET /mcp-servers/{id}. Server detail: full row (incl. scan_result,
// last_health, egress_allowlist, auth_kind, has_secret) for the detail page.
func (s *Server) getMcpServer(w http.ResponseWriter, r *http.Request) {
	uid, _, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	mid, ok := parseUUIDParam(w, r, "mcp_server_id")
	if !ok {
		return
	}
	var row mcpServerRow
	// visibility: System ∪ own ∪ any book the row belongs to (book grant enforced on
	// writes; reads of a book row the user can see are fine — filtered to own+system+
	// the requested book context is out of scope here, so restrict to system ∪ own).
	err := scanMcp(s.db.QueryRow(r.Context(),
		`SELECT `+mcpCols+` FROM mcp_server_registrations
		 WHERE mcp_server_id=$1 AND (tier='system' OR (tier='user' AND owner_user_id=$2))`, mid, uid), &row)
	if err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "server not found") // anti-oracle
		return
	}
	writeJSON(w, http.StatusOK, row)
}

// acceptRiskMcpServer — POST /mcp-servers/{id}/accept-risk. A human accept-risk on a
// quarantined (suspended) server: force status→active despite scan findings, audited.
// REG-P3-08. Owner/grant-gated.
func (s *Server) acceptRiskMcpServer(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	mid, ok := parseUUIDParam(w, r, "mcp_server_id")
	if !ok {
		return
	}
	var tier, status string
	var owner, book *uuid.UUID
	if err := s.db.QueryRow(r.Context(), `SELECT tier, owner_user_id, book_id, status FROM mcp_server_registrations WHERE mcp_server_id=$1`, mid).Scan(&tier, &owner, &book, &status); err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "server not found")
		return
	}
	if !s.authorizeRowWrite(r, tier, owner, book, uid, role) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "server not found")
		return
	}
	if status != "suspended" && status != "pending" {
		writeError(w, http.StatusConflict, "NOT_QUARANTINED", "only a quarantined (suspended/pending) server can be accept-risked")
		return
	}
	if _, err := s.db.Exec(r.Context(), `UPDATE mcp_server_registrations SET status='active', updated_at=now() WHERE mcp_server_id=$1`, mid); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not update status")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(role), "mcp_server", "accept_risk", &mid, "", tier, map[string]any{"from_status": status})
	s.bumpCatalogVersion(r.Context())
	writeJSON(w, http.StatusOK, map[string]any{"mcp_server_id": mid, "status": "active", "risk_accepted": true})
}
