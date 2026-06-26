package api

import (
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/loreweave/auth-service/internal/authpwd"
	"github.com/loreweave/auth-service/internal/ratelimit"
)

// Public MCP API keys (P1, docs/specs/2026-06-26-public-mcp/03 §5).
//
// An external agent presents `Authorization: Bearer lw_pk_<random>` to the
// mcp-public-gateway edge; the edge resolves it via POST /internal/mcp-keys/resolve.
// The raw secret is shown ONCE at creation and only an Argon2id hash is stored.
// Lookup is by the non-secret key_prefix, then a constant-time hash verify of the
// candidates (authpwd.Verify). The resolve path re-checks users.account_status
// ='active' so a deleted/suspended owner's key dies immediately (H-L).

const (
	mcpKeyVisiblePrefix = "lw_pk_"
	// key_prefix stored for O(1) lookup = visible-prefix + this many body chars.
	mcpKeyPrefixBodyLen = 6
	mcpKeyBodyBytes     = 24 // 24 random bytes → ~32 url-safe chars of secret body
)

// mcpResolveMaxPerWindow caps resolve ATTEMPTS per key_prefix per window so a
// caller who knows a valid prefix can't force unbounded Argon2id verifications
// (H-H — the cheap pre-check runs BEFORE the slow hash). A legitimate agent reuses
// one key and the edge caches the resolution ~30-60s, so real traffic stays far
// below this; only a hammering attacker hits it.
const (
	mcpResolveMaxPerWindow = 30
	mcpResolveWindow       = time.Minute
)

// maxMcpKeysPerUser caps active keys per user so a runaway/abusive account can't
// mint unbounded credentials (mirrors book-service's maxBooksPerUser ceiling).
const maxMcpKeysPerUser = 50

type mcpKeyCreateReq struct {
	Name             string   `json:"name"`
	Scopes           []string `json:"scopes"`
	RateLimitRPM     *int     `json:"rate_limit_rpm"`
	SpendCapUSD      *float64 `json:"spend_cap_usd"`
	AllowSelfConfirm bool     `json:"allow_self_confirm"`
	ExpiresAt        *string  `json:"expires_at"` // RFC3339; null = no expiry
}

// mcpKeyView is the metadata shape returned by list/get — NEVER the secret or hash.
type mcpKeyView struct {
	KeyID            string   `json:"key_id"`
	Name             string   `json:"name"`
	KeyPrefix        string   `json:"key_prefix"`
	Scopes           []string `json:"scopes"`
	SpendCapUSD      *float64 `json:"spend_cap_usd"`
	RateLimitRPM     int      `json:"rate_limit_rpm"`
	AllowSelfConfirm bool     `json:"allow_self_confirm"`
	Status           string   `json:"status"`
	LastUsedAt       *string  `json:"last_used_at"`
	ExpiresAt        *string  `json:"expires_at"`
	CreatedAt        string   `json:"created_at"`
}

// generateMcpAPIKey returns the full secret + the stored prefix. The prefix is the
// visible scheme + a few body chars: enough to look up O(1) without being the secret.
func generateMcpAPIKey() (full, prefix string, err error) {
	b := make([]byte, mcpKeyBodyBytes)
	if _, err = rand.Read(b); err != nil {
		return "", "", err
	}
	body := base64.RawURLEncoding.EncodeToString(b)
	full = mcpKeyVisiblePrefix + body
	prefix = full[:len(mcpKeyVisiblePrefix)+mcpKeyPrefixBodyLen]
	return full, prefix, nil
}

// mcpKeyPrefixOf extracts the stored-prefix slice from a presented key, or "" if
// the key is too short / not an lw_pk_ key (a cheap reject before any DB/hash work).
func mcpKeyPrefixOf(key string) string {
	if !strings.HasPrefix(key, mcpKeyVisiblePrefix) {
		return ""
	}
	if len(key) < len(mcpKeyVisiblePrefix)+mcpKeyPrefixBodyLen {
		return ""
	}
	return key[:len(mcpKeyVisiblePrefix)+mcpKeyPrefixBodyLen]
}

// --- /v1/account/mcp-keys (JWT, owner-only) ---

func (s *Server) createMcpKey(w http.ResponseWriter, r *http.Request) {
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
	// Q-GATE: key creation is OFF unless the platform flag is enabled.
	if !s.cfg.PublicMcpEnabled {
		writeErr(w, http.StatusForbidden, "AUTH_PUBLIC_MCP_DISABLED", "public MCP access is not enabled on this platform")
		return
	}
	var req mcpKeyCreateReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid json")
		return
	}
	req.Name = strings.TrimSpace(req.Name)
	if req.Name == "" || len(req.Name) > 100 {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "name is required (1-100 chars)")
		return
	}
	rpm := 60
	if req.RateLimitRPM != nil {
		if *req.RateLimitRPM < 1 || *req.RateLimitRPM > 6000 {
			writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "rate_limit_rpm must be 1-6000")
			return
		}
		rpm = *req.RateLimitRPM
	}
	if req.SpendCapUSD != nil && *req.SpendCapUSD < 0 {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "spend_cap_usd must be >= 0")
		return
	}
	var expiresAt *time.Time
	if req.ExpiresAt != nil && strings.TrimSpace(*req.ExpiresAt) != "" {
		t, perr := time.Parse(time.RFC3339, *req.ExpiresAt)
		if perr != nil {
			writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "expires_at must be RFC3339")
			return
		}
		expiresAt = &t
	}
	scopes := req.Scopes
	if scopes == nil {
		scopes = []string{}
	}

	// Per-user active-key ceiling (anti-runaway).
	var active int
	if err := s.pool.QueryRow(r.Context(),
		`SELECT count(*) FROM mcp_api_keys WHERE owner_user_id = $1 AND status = 'active'`, uid,
	).Scan(&active); err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "create failed")
		return
	}
	if active >= maxMcpKeysPerUser {
		writeErr(w, http.StatusConflict, "AUTH_MCP_KEY_LIMIT", "active key limit reached; revoke an unused key first")
		return
	}

	full, prefix, err := generateMcpAPIKey()
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "key generation failed")
		return
	}
	hash, err := authpwd.Hash(full)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "key hashing failed")
		return
	}
	var keyID uuid.UUID
	var createdAt time.Time
	err = s.pool.QueryRow(r.Context(), `
		INSERT INTO mcp_api_keys (owner_user_id, name, key_prefix, key_hash, scopes, spend_cap_usd, rate_limit_rpm, allow_self_confirm, expires_at)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
		RETURNING key_id, created_at`,
		uid, req.Name, prefix, hash, scopes, req.SpendCapUSD, rpm, req.AllowSelfConfirm, expiresAt,
	).Scan(&keyID, &createdAt)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "create failed")
		return
	}
	// The ONLY time the full secret is ever returned (H-Q copy-once).
	writeJSON(w, http.StatusCreated, map[string]any{
		"key_id":     keyID.String(),
		"name":       req.Name,
		"key":        full, // shown once — never retrievable again
		"key_prefix": prefix,
		"scopes":     scopes,
		"created_at": createdAt.UTC().Format(time.RFC3339Nano),
	})
}

func (s *Server) listMcpKeys(w http.ResponseWriter, r *http.Request) {
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
	rows, err := s.pool.Query(r.Context(), `
		SELECT key_id, name, key_prefix, scopes, spend_cap_usd, rate_limit_rpm, allow_self_confirm, status, last_used_at, expires_at, created_at
		FROM mcp_api_keys WHERE owner_user_id = $1 ORDER BY created_at DESC`, uid)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "list failed")
		return
	}
	defer rows.Close()
	items := []mcpKeyView{}
	for rows.Next() {
		v, scanErr := scanMcpKeyView(rows)
		if scanErr != nil {
			writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "scan failed")
			return
		}
		items = append(items, v)
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) revokeMcpKey(w http.ResponseWriter, r *http.Request) {
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
	// Owner-scoped: a user can only revoke their own key. Anti-oracle: a key that
	// isn't theirs (or doesn't exist) yields the same 404.
	tag, err := s.pool.Exec(r.Context(),
		`UPDATE mcp_api_keys SET status = 'revoked' WHERE key_id = $1 AND owner_user_id = $2 AND status = 'active'`,
		keyID, uid)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "revoke failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeErr(w, http.StatusNotFound, "AUTH_MCP_KEY_NOT_FOUND", "key not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) patchMcpKey(w http.ResponseWriter, r *http.Request) {
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
	var body struct {
		Name             *string  `json:"name"`
		Scopes           []string `json:"scopes"`
		RateLimitRPM     *int     `json:"rate_limit_rpm"`
		SpendCapUSD      *float64 `json:"spend_cap_usd"`
		AllowSelfConfirm *bool    `json:"allow_self_confirm"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid json")
		return
	}
	var name *string
	if body.Name != nil {
		n := strings.TrimSpace(*body.Name)
		if n == "" || len(n) > 100 {
			writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "name must be 1-100 chars")
			return
		}
		name = &n
	}
	if body.RateLimitRPM != nil && (*body.RateLimitRPM < 1 || *body.RateLimitRPM > 6000) {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "rate_limit_rpm must be 1-6000")
		return
	}
	if body.SpendCapUSD != nil && *body.SpendCapUSD < 0 {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "spend_cap_usd must be >= 0")
		return
	}
	// COALESCE-style partial update; scopes only replaced when provided (non-nil).
	var scopes any
	if body.Scopes != nil {
		scopes = body.Scopes
	}
	tag, err := s.pool.Exec(r.Context(), `
		UPDATE mcp_api_keys SET
		  name = COALESCE($3, name),
		  scopes = COALESCE($4, scopes),
		  rate_limit_rpm = COALESCE($5, rate_limit_rpm),
		  spend_cap_usd = CASE WHEN $6::boolean THEN $7 ELSE spend_cap_usd END,
		  allow_self_confirm = COALESCE($8, allow_self_confirm)
		WHERE key_id = $1 AND owner_user_id = $2 AND status = 'active'`,
		keyID, uid, name, scopes, body.RateLimitRPM, body.SpendCapUSD != nil, body.SpendCapUSD, body.AllowSelfConfirm)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "update failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeErr(w, http.StatusNotFound, "AUTH_MCP_KEY_NOT_FOUND", "key not found")
		return
	}
	var v mcpKeyView
	row := s.pool.QueryRow(r.Context(), `
		SELECT key_id, name, key_prefix, scopes, spend_cap_usd, rate_limit_rpm, allow_self_confirm, status, last_used_at, expires_at, created_at
		FROM mcp_api_keys WHERE key_id = $1`, keyID)
	v, err = scanMcpKeyView(row)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "scan failed")
		return
	}
	writeJSON(w, http.StatusOK, v)
}

// --- POST /internal/mcp-keys/resolve (X-Internal-Token) ---

type mcpResolveReq struct {
	Key string `json:"key"`
}

type mcpResolveResp struct {
	UserID           string   `json:"user_id"`
	KeyID            string   `json:"key_id"`
	Scopes           []string `json:"scopes"`
	AllowSelfConfirm bool     `json:"allow_self_confirm"`
	SpendCapUSD      *float64 `json:"spend_cap_usd"`
	RateLimitRPM     int      `json:"rate_limit_rpm"`
}

// internalResolveMcpKey is the edge's hot path: a candidate key → identity + policy,
// or a uniform 401 (no oracle distinguishing bad-key / wrong-secret / dead-account).
func (s *Server) internalResolveMcpKey(w http.ResponseWriter, r *http.Request) {
	var req mcpResolveReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid json")
		return
	}
	// Trim once and use the SAME value for both the prefix lookup and the hash
	// verify (consistency — never look up by one form and verify another).
	key := strings.TrimSpace(req.Key)
	prefix := mcpKeyPrefixOf(key)
	if prefix == "" {
		writeErr(w, http.StatusUnauthorized, "AUTH_MCP_KEY_INVALID", "invalid key")
		return
	}
	// H-H: cap resolve ATTEMPTS per prefix BEFORE the Argon2id verify, so a known
	// prefix can't be used to burn CPU. Keyed by prefix (stricter than per-IP — an
	// attacker rotating IPs is still bounded).
	if !s.mcpResolveRL.Allow("mcpkey:" + prefix) {
		w.Header().Set("Retry-After", "60")
		writeErr(w, http.StatusTooManyRequests, "AUTH_RATE_LIMITED", "too many key attempts")
		return
	}
	rows, err := s.pool.Query(r.Context(), `
		SELECT k.key_id, k.owner_user_id, k.key_hash, k.scopes, k.allow_self_confirm, k.spend_cap_usd, k.rate_limit_rpm, k.expires_at, u.account_status
		FROM mcp_api_keys k JOIN users u ON u.id = k.owner_user_id
		WHERE k.key_prefix = $1 AND k.status = 'active'`, prefix)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "resolve failed")
		return
	}
	defer rows.Close()
	now := time.Now()
	for rows.Next() {
		var keyID, ownerID uuid.UUID
		var keyHash, accountStatus string
		var scopes []string
		var allowSelfConfirm bool
		var spendCap *float64
		var rpm int
		var expiresAt *time.Time
		if err := rows.Scan(&keyID, &ownerID, &keyHash, &scopes, &allowSelfConfirm, &spendCap, &rpm, &expiresAt, &accountStatus); err != nil {
			continue
		}
		if expiresAt != nil && now.After(*expiresAt) {
			continue
		}
		ok, _ := authpwd.Verify(key, keyHash)
		if !ok {
			continue
		}
		// H-L: the owner account must be live; a deleted/suspended owner's key dies
		// immediately regardless of the edge's resolve cache.
		if accountStatus != "active" {
			writeErr(w, http.StatusUnauthorized, "AUTH_MCP_KEY_INVALID", "invalid key")
			return
		}
		if scopes == nil {
			scopes = []string{}
		}
		// best-effort last_used stamp (never block the hot path on it)
		_, _ = s.pool.Exec(r.Context(), `UPDATE mcp_api_keys SET last_used_at = now() WHERE key_id = $1`, keyID)
		writeJSON(w, http.StatusOK, mcpResolveResp{
			UserID:           ownerID.String(),
			KeyID:            keyID.String(),
			Scopes:           scopes,
			AllowSelfConfirm: allowSelfConfirm,
			SpendCapUSD:      spendCap,
			RateLimitRPM:     rpm,
		})
		return
	}
	// No active row matched (bad key / wrong secret) — uniform 401.
	writeErr(w, http.StatusUnauthorized, "AUTH_MCP_KEY_INVALID", "invalid key")
}

// scanMcpKeyView reads a metadata row (pgx.Row or pgx.Rows) into a view.
func scanMcpKeyView(row pgx.Row) (mcpKeyView, error) {
	var v mcpKeyView
	var keyID uuid.UUID
	var scopes []string
	var spendCap *float64
	var lastUsed, expiresAt *time.Time
	var createdAt time.Time
	if err := row.Scan(&keyID, &v.Name, &v.KeyPrefix, &scopes, &spendCap, &v.RateLimitRPM, &v.AllowSelfConfirm, &v.Status, &lastUsed, &expiresAt, &createdAt); err != nil {
		return mcpKeyView{}, err
	}
	if scopes == nil {
		scopes = []string{}
	}
	v.KeyID = keyID.String()
	v.Scopes = scopes
	v.SpendCapUSD = spendCap
	v.CreatedAt = createdAt.UTC().Format(time.RFC3339Nano)
	if lastUsed != nil {
		s := lastUsed.UTC().Format(time.RFC3339Nano)
		v.LastUsedAt = &s
	}
	if expiresAt != nil {
		s := expiresAt.UTC().Format(time.RFC3339Nano)
		v.ExpiresAt = &s
	}
	return v, nil
}

// newMcpResolveLimiter builds the per-prefix Argon2-DoS guard (H-H).
func newMcpResolveLimiter() *ratelimit.Limiter {
	return ratelimit.New(mcpResolveWindow, mcpResolveMaxPerWindow)
}
