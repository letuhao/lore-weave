package api

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

type mcpServerRow struct {
	McpServerID     uuid.UUID       `json:"mcp_server_id"`
	Tier            string          `json:"tier"`
	OwnerUserID     *uuid.UUID      `json:"owner_user_id,omitempty"`
	BookID          *uuid.UUID      `json:"book_id,omitempty"`
	DisplayName     string          `json:"display_name"`
	EndpointURL     string          `json:"endpoint_url"`
	Transport       string          `json:"transport"`
	ToolPrefix      string          `json:"tool_name_prefix"`
	Status          string          `json:"status"`
	AuthKind        string          `json:"auth_kind"`
	IsExternal      bool            `json:"is_external"`
	secretCipher    string          // vault ciphertext — NEVER serialized
	HasSecret       bool            `json:"has_secret"`
	EgressAllowlist json.RawMessage `json:"egress_allowlist"`
	ScanResult      json.RawMessage `json:"scan_result"`
	LastHealth      json.RawMessage `json:"last_health"`
	LastScannedAt   *time.Time      `json:"last_scanned_at,omitempty"`
	CreatedAt       time.Time       `json:"created_at"`
	UpdatedAt       time.Time       `json:"updated_at"`
}

const mcpCols = `mcp_server_id, tier, owner_user_id, book_id, display_name, endpoint_url, transport, tool_name_prefix, status, auth_kind, is_external, secret_ciphertext, egress_allowlist, scan_result, last_health, last_scanned_at, created_at, updated_at`

func scanMcp(row interface{ Scan(...any) error }, m *mcpServerRow) error {
	if err := row.Scan(&m.McpServerID, &m.Tier, &m.OwnerUserID, &m.BookID, &m.DisplayName,
		&m.EndpointURL, &m.Transport, &m.ToolPrefix, &m.Status, &m.AuthKind, &m.IsExternal,
		&m.secretCipher, &m.EgressAllowlist, &m.ScanResult, &m.LastHealth, &m.LastScannedAt,
		&m.CreatedAt, &m.UpdatedAt); err != nil {
		return err
	}
	m.HasSecret = m.secretCipher != "" // public: has_secret only, never the ciphertext
	return nil
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

type createMcpReq struct {
	DisplayName     string     `json:"display_name"`
	EndpointURL     string     `json:"endpoint_url"`
	Tier            string     `json:"tier"`
	BookID          *uuid.UUID `json:"book_id"`
	AuthKind        string     `json:"auth_kind"`        // none|bearer|oauth2
	BearerToken     string     `json:"bearer_token"`     // write-only; encrypted into the vault, never echoed
	EgressAllowlist []string   `json:"egress_allowlist"` // extra outbound hosts the ai-gateway egress path permits
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
	// Provider-gateway invariant FIRST (syntactic, DNS-independent): a model-capability
	// endpoint must go through provider-registry BYOK, never register as an MCP tool
	// server. Checked before the SSRF resolve so an unresolvable model host still gets
	// the correct pointer error rather than a generic resolve failure.
	if m := looksLikeModelEndpoint(req.EndpointURL, req.DisplayName); m != "" {
		writeError(w, http.StatusBadRequest, "MODEL_CAPABILITY_NOT_ALLOWED",
			"this looks like a model endpoint ("+m+"); register model capabilities as a BYOK credential in provider-registry, not as an MCP tool server")
		return
	}
	// P3 SSRF guard: a user URL is validated + classified (internal targets allowed
	// only under the dev flag). Public MCP servers are accepted; internal/loopback/
	// metadata addresses are rejected (the SSRF hole).
	class, err := classifyRegistrationURL(r.Context(), nil, req.EndpointURL, s.cfg.AllowInternalMcpTargets)
	if err != nil {
		writeError(w, http.StatusBadRequest, "SSRF_BLOCKED", err.Error())
		return
	}
	authKind := req.AuthKind
	if authKind == "" {
		authKind = "none"
	}
	if authKind != "none" && authKind != "bearer" && authKind != "oauth2" {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "auth_kind must be none, bearer, or oauth2")
		return
	}
	// Bearer secret is encrypted into the vault at write time; never round-trips.
	var secretCipher, secretKeyRef string
	if authKind == "bearer" {
		if strings.TrimSpace(req.BearerToken) == "" {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "bearer_token required when auth_kind is bearer")
			return
		}
		secretCipher, secretKeyRef, err = s.encryptSecret(req.BearerToken)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "VAULT_ERROR", "could not seal credential")
			return
		}
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
	// Egress allowlist always includes the endpoint's own host; extra hosts are additive.
	egress := buildEgressAllowlist(class.Normalized, req.EgressAllowlist)
	// Status machine: an EXTERNAL server is QUARANTINED (pending) until the
	// supply-chain scan clears it (REG-P3-05); internal/dev + System start active.
	status := "active"
	if class.IsExternal {
		status = "pending"
	}
	var row mcpServerRow
	err = scanMcp(s.db.QueryRow(r.Context(),
		`INSERT INTO mcp_server_registrations
		   (tier, owner_user_id, book_id, display_name, endpoint_url, tool_name_prefix, status,
		    auth_kind, is_external, secret_ciphertext, secret_key_ref, egress_allowlist)
		 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING `+mcpCols,
		tier, ownerArg, bookArg, req.DisplayName, class.Normalized, prefix, status,
		authKind, class.IsExternal, secretCipher, secretKeyRef, egress), &row)
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
	// External servers register QUARANTINED (pending); kick a best-effort supply-chain
	// scan that flips pending→active (clean) or suspended (flagged). The wizard also
	// triggers a synchronous rescan on its Health & Scan step.
	if class.IsExternal {
		s.scanAsync(row.McpServerID)
	}
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

// internalMcpCredentials (X-Internal-Token) — REG-P3-02. The ONLY route that
// decrypts a server's vault secret, for the ai-gateway egress path to inject the
// bearer/oauth token into an outbound call. Owner-filtered: the caller passes the
// resolution user_id and only that user's own (or a System) server is returned;
// the plaintext secret NEVER appears on any JWT-facing route. The public serializer
// exposes has_secret only.
func (s *Server) internalMcpCredentials(w http.ResponseWriter, r *http.Request) {
	if s.db == nil {
		writeError(w, http.StatusServiceUnavailable, "NO_DB", "database unavailable")
		return
	}
	mid, ok := parseUUIDParam(w, r, "mcp_server_id")
	if !ok {
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
	var authKind, cipher string
	err = s.db.QueryRow(r.Context(),
		`SELECT auth_kind, secret_ciphertext FROM mcp_server_registrations
		 WHERE mcp_server_id = $1
		   AND ( tier = 'system'
		      OR (tier = 'user' AND owner_user_id = $2)
		      OR (tier = 'book' AND book_id = $3) )`,
		mid, uid, nullUUID(bookID)).Scan(&authKind, &cipher)
	if err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "server not found") // anti-oracle
		return
	}
	secret, err := s.decryptSecret(cipher)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "VAULT_ERROR", "could not open credential")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"mcp_server_id": mid,
		"auth_kind":     authKind,
		"secret":        secret, // plaintext — internal-token only, never on a JWT route
	})
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
		`SELECT reg.mcp_server_id, reg.endpoint_url, reg.transport, reg.tool_name_prefix, reg.tier, reg.is_external, reg.egress_allowlist, en.enabled
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
		ID              string          `json:"mcp_server_id"`
		EndpointID      string          `json:"endpoint_url"`
		Transport       string          `json:"transport"`
		ToolPrefix      string          `json:"tool_name_prefix"`
		Tier            string          `json:"tier"`
		IsExternal      bool            `json:"is_external"`
		EgressAllowlist json.RawMessage `json:"egress_allowlist"`
	}
	servers := []outServer{}
	for rows.Next() {
		var id uuid.UUID
		var endpoint, transport, prefix, tier string
		var isExternal bool
		var egress json.RawMessage
		var override *bool
		if err := rows.Scan(&id, &endpoint, &transport, &prefix, &tier, &isExternal, &egress, &override); err != nil {
			continue
		}
		if override != nil && !*override { // default-on; explicit disable removes it
			continue
		}
		servers = append(servers, outServer{
			ID: id.String(), EndpointID: endpoint, Transport: transport, ToolPrefix: prefix, Tier: tier,
			IsExternal: isExternal, EgressAllowlist: egress,
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
