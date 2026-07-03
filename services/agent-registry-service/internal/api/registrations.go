package api

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"net"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

type mcpServerRow struct {
	McpServerID   uuid.UUID  `json:"mcp_server_id"`
	Tier          string     `json:"tier"`
	OwnerUserID   *uuid.UUID `json:"owner_user_id,omitempty"`
	BookID        *uuid.UUID `json:"book_id,omitempty"`
	DisplayName   string     `json:"display_name"`
	EndpointURL   string     `json:"endpoint_url"`
	Transport     string     `json:"transport"`
	ToolPrefix    string     `json:"tool_name_prefix"`
	Status        string     `json:"status"`
	CreatedAt     time.Time  `json:"created_at"`
	UpdatedAt     time.Time  `json:"updated_at"`
}

const mcpCols = `mcp_server_id, tier, owner_user_id, book_id, display_name, endpoint_url, transport, tool_name_prefix, status, created_at, updated_at`

func scanMcp(row interface{ Scan(...any) error }, m *mcpServerRow) error {
	return row.Scan(&m.McpServerID, &m.Tier, &m.OwnerUserID, &m.BookID, &m.DisplayName,
		&m.EndpointURL, &m.Transport, &m.ToolPrefix, &m.Status, &m.CreatedAt, &m.UpdatedAt)
}

// userToolPrefix is the mandatory per-owner tool namespace: user tools can never
// shadow a System tool because they're forced under `u_<hash8(owner)>_`. Book tier
// uses `b_<hash8(book)>_`. Deterministic so it's stable across registrations.
func userToolPrefix(tier string, owner, book uuid.UUID) string {
	switch tier {
	case "book":
		return "b_" + hash8(book.String()) + "_"
	default:
		return "u_" + hash8(owner.String()) + "_"
	}
}

func hash8(s string) string {
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:])[:8]
}

// isInternalHost restricts P2 registrations to internal endpoints (private IPs,
// loopback, docker service names, *.internal). Arbitrary public hosts are a P3
// concern (they need the full SSRF guard + OAuth + scan). This is NOT the P3
// security boundary — it's the P2 scoping guard that keeps the overlay mechanism
// testable without opening the external surface early.
func isInternalHost(raw string) (string, bool) {
	u, err := url.Parse(raw)
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" {
		return "", false
	}
	host := u.Hostname()
	lower := strings.ToLower(host)
	if lower == "localhost" || lower == "host.docker.internal" || strings.HasSuffix(lower, ".internal") {
		return u.String(), true
	}
	if ip := net.ParseIP(host); ip != nil {
		if ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast() {
			return u.String(), true
		}
		return "", false // a public IP is external → P3
	}
	// A bare service name (no dots) is a docker-network internal service.
	if !strings.Contains(host, ".") {
		return u.String(), true
	}
	return "", false // has a public-looking domain → external → P3
}

type createMcpReq struct {
	DisplayName string     `json:"display_name"`
	EndpointURL string     `json:"endpoint_url"`
	Tier        string     `json:"tier"`
	BookID      *uuid.UUID `json:"book_id"`
}

func (s *Server) createMcpServer(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	var req createMcpReq
	if !decodeJSON(w, r, &req) {
		return
	}
	endpoint, internal := isInternalHost(strings.TrimSpace(req.EndpointURL))
	if !internal {
		writeError(w, http.StatusBadRequest, "EXTERNAL_NOT_ALLOWED", "P2 accepts internal endpoints only; external MCP servers arrive with the P3 security layer (OAuth + SSRF guard + scan)")
		return
	}
	tier := req.Tier
	if tier == "" {
		tier = "user"
	}
	var ownerArg, bookArg any
	var prefix string
	switch tier {
	case "user":
		ownerArg = uid
		prefix = userToolPrefix("user", uid, uuid.Nil)
	case "system":
		if role != "admin" {
			writeError(w, http.StatusForbidden, "FORBIDDEN", "only admin may register System-tier servers")
			return
		}
		prefix = "" // System tools keep their own prefix (no namespacing)
	case "book":
		if req.BookID == nil {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "book_id required for book tier")
			return
		}
		if !s.requireBookGrant(w, r, *req.BookID, uid) {
			return
		}
		bookArg = *req.BookID
		prefix = userToolPrefix("book", uuid.Nil, *req.BookID)
	default:
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "invalid tier")
		return
	}
	// D2 quota: 10 MCP servers per user.
	if tier == "user" && s.queryInt(r.Context(), `SELECT COUNT(*) FROM mcp_server_registrations WHERE tier='user' AND owner_user_id=$1`, uid) >= quotaMCPServers {
		writeError(w, http.StatusTooManyRequests, "QUOTA_EXCEEDED", "MCP server limit reached (max 10 per user)")
		return
	}
	var row mcpServerRow
	err := scanMcp(s.db.QueryRow(r.Context(),
		`INSERT INTO mcp_server_registrations (tier, owner_user_id, book_id, display_name, endpoint_url, tool_name_prefix, status)
		 VALUES ($1,$2,$3,$4,$5,$6,'active') RETURNING `+mcpCols,
		tier, ownerArg, bookArg, req.DisplayName, endpoint, prefix), &row)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "DUPLICATE", "this endpoint is already registered in your scope")
			return
		}
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not register server")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(role), "mcp_server", "register", &row.McpServerID, row.DisplayName, tier, nil)
	s.bumpCatalogVersion(r.Context())
	registryWrites.WithLabelValues("mcp_server", "register").Inc()
	writeJSON(w, http.StatusCreated, row)
}

func (s *Server) listMcpServers(w http.ResponseWriter, r *http.Request) {
	uid, _, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	q := r.URL.Query()
	limit := clampLimit(q.Get("limit"))
	offset := atoiDefault(q.Get("offset"), 0)
	if offset < 0 {
		offset = 0
	}
	where := []string{"(tier = 'system' OR (tier = 'user' AND owner_user_id = $1))"}
	args := []any{uid}
	if v := q.Get("status"); v != "" {
		args = append(args, v)
		where = append(where, "status = $"+strconv.Itoa(len(args)))
	}
	whereSQL := strings.Join(where, " AND ")
	total := s.queryInt(r.Context(), `SELECT COUNT(*) FROM mcp_server_registrations WHERE `+whereSQL, args...)
	args = append(args, limit, offset)
	rows, err := s.db.Query(r.Context(),
		`SELECT `+mcpCols+` FROM mcp_server_registrations WHERE `+whereSQL+` ORDER BY created_at DESC LIMIT $`+strconv.Itoa(len(args)-1)+` OFFSET $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not list servers")
		return
	}
	defer rows.Close()
	items := []mcpServerRow{}
	for rows.Next() {
		var m mcpServerRow
		if err := scanMcp(rows, &m); err != nil {
			continue
		}
		items = append(items, m)
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total, "limit": limit, "offset": offset})
}

func (s *Server) deleteMcpServer(w http.ResponseWriter, r *http.Request) {
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
	if err := s.db.QueryRow(r.Context(), `SELECT tier, owner_user_id, book_id FROM mcp_server_registrations WHERE mcp_server_id = $1`, mid).Scan(&tier, &owner, &book); err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "server not found")
		return
	}
	if !s.authorizeRowWrite(r, tier, owner, book, uid, role) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "server not found")
		return
	}
	if _, err := s.db.Exec(r.Context(), `DELETE FROM mcp_server_registrations WHERE mcp_server_id = $1`, mid); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not delete server")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(role), "mcp_server", "delete", &mid, "", tier, nil)
	s.bumpCatalogVersion(r.Context())
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) setMcpEnabled(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	mid, ok := parseUUIDParam(w, r, "mcp_server_id")
	if !ok {
		return
	}
	// visibility: System ∪ own
	var n int
	_ = s.db.QueryRow(r.Context(), `SELECT COUNT(*) FROM mcp_server_registrations WHERE mcp_server_id=$1 AND (tier='system' OR (tier='user' AND owner_user_id=$2))`, mid, uid).Scan(&n)
	if n == 0 {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "server not found")
		return
	}
	var body struct {
		Enabled bool `json:"enabled"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	_, err := s.db.Exec(r.Context(),
		`INSERT INTO mcp_server_enablement (mcp_server_id, owner_user_id, enabled) VALUES ($1,$2,$3)
		 ON CONFLICT (mcp_server_id, owner_user_id) DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = now()`,
		mid, uid, body.Enabled)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not set enablement")
		return
	}
	action := "disable"
	if body.Enabled {
		action = "enable"
	}
	s.audit(r.Context(), uid, actorKindOf(role), "mcp_server", action, &mid, "", "", nil)
	s.bumpCatalogVersion(r.Context())
	writeJSON(w, http.StatusOK, map[string]any{"mcp_server_id": mid, "enabled": body.Enabled})
}

// countMcpServers is used by getUsage (D2 quota strip).
func (s *Server) countMcpServers(ctx context.Context, uid uuid.UUID) int {
	return s.queryInt(ctx, `SELECT COUNT(*) FROM mcp_server_registrations WHERE tier='user' AND owner_user_id=$1`, uid)
}

// internalEffectiveMcpServers (X-Internal-Token) — REG-P2-02. Returns the MCP
// server endpoints ai-gateway should federate into THIS (user, book) catalog:
// the user's + book's + System registrations, effective-enabled + status=active,
// each with its mandatory tool_name_prefix. The catalog_version is the Q-CACHE
// etag the gateway compares per turn.
func (s *Server) internalEffectiveMcpServers(w http.ResponseWriter, r *http.Request) {
	if s.db == nil {
		writeError(w, http.StatusServiceUnavailable, "NO_DB", "database unavailable")
		return
	}
	uid, err := uuid.Parse(r.URL.Query().Get("user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "user_id required")
		return
	}
	bookID := uuid.Nil
	if v := r.URL.Query().Get("book_id"); v != "" {
		if b, e := uuid.Parse(v); e == nil {
			bookID = b
		}
	}
	rows, err := s.db.Query(r.Context(),
		`SELECT reg.mcp_server_id, reg.endpoint_url, reg.transport, reg.tool_name_prefix, reg.tier, en.enabled
		 FROM mcp_server_registrations reg
		 LEFT JOIN mcp_server_enablement en ON en.mcp_server_id = reg.mcp_server_id AND en.owner_user_id = $1
		 WHERE reg.status = 'active'
		   AND ( reg.tier = 'system'
		      OR (reg.tier = 'user' AND reg.owner_user_id = $1)
		      OR (reg.tier = 'book' AND reg.book_id = $2) )`,
		uid, nullUUID(bookID))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not resolve servers")
		return
	}
	defer rows.Close()
	type outServer struct {
		ID         string `json:"mcp_server_id"`
		EndpointID string `json:"endpoint_url"`
		Transport  string `json:"transport"`
		ToolPrefix string `json:"tool_name_prefix"`
		Tier       string `json:"tier"`
	}
	servers := []outServer{}
	for rows.Next() {
		var id uuid.UUID
		var endpoint, transport, prefix, tier string
		var override *bool
		if err := rows.Scan(&id, &endpoint, &transport, &prefix, &tier, &override); err != nil {
			continue
		}
		if override != nil && !*override { // default-on; explicit disable removes it
			continue
		}
		servers = append(servers, outServer{
			ID: id.String(), EndpointID: endpoint, Transport: transport, ToolPrefix: prefix, Tier: tier,
		})
	}
	version := s.catalogVersion(r.Context())
	w.Header().Set("ETag", `"v`+strconv.FormatInt(version, 10)+`"`)
	writeJSON(w, http.StatusOK, map[string]any{
		"catalog_version": version,
		"user_id":         uid,
		"book_id":         nullUUID(bookID),
		"servers":         servers,
	})
}
