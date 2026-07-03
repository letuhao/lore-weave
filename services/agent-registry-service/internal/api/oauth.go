package api

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/google/uuid"
)

// ── REG-P3-03 OAuth 2.1 + PKCE (S256) + RFC 8707 resource-scoped tokens ───────
//
// A user's external MCP server may require OAuth. We run the authorization-code +
// PKCE flow as a PUBLIC client (no client secret — the MCP norm): /oauth/start mints
// a PKCE verifier+state bound to the server, returns the authorization URL; the AS
// redirects the browser to /oauth/callback which exchanges the code for tokens scoped
// to the server via RFC 8707 `resource`. Access + refresh tokens are sealed in the
// AES-GCM vault, NEVER surfaced to the LLM. A background worker refreshes before expiry.

type oauthMeta struct {
	AuthorizationEndpoint string     `json:"authorization_endpoint"`
	TokenEndpoint         string     `json:"token_endpoint"`
	ClientID              string     `json:"client_id"`
	Scopes                []string   `json:"scopes,omitempty"`
	Resource              string     `json:"resource"` // RFC 8707 — the MCP server URL
	TokenType             string     `json:"token_type,omitempty"`
	TokenExpiresAt        *time.Time `json:"token_expires_at,omitempty"`
}

// oauthRegConfig is the OAuth block a client supplies at registration (auth_kind=oauth2).
type oauthRegConfig struct {
	AuthorizationEndpoint string   `json:"authorization_endpoint"`
	TokenEndpoint         string   `json:"token_endpoint"`
	ClientID              string   `json:"client_id"`
	Scopes                []string `json:"scopes"`
}

// ── PKCE ─────────────────────────────────────────────────────────────────────

func newPKCEVerifier() string {
	b := make([]byte, 32)
	_, _ = rand.Read(b)
	return base64.RawURLEncoding.EncodeToString(b)
}

// pkceS256Challenge = BASE64URL(SHA256(verifier)) per RFC 7636 §4.2.
func pkceS256Challenge(verifier string) string {
	sum := sha256.Sum256([]byte(verifier))
	return base64.RawURLEncoding.EncodeToString(sum[:])
}

func newOAuthState() string {
	b := make([]byte, 24)
	_, _ = rand.Read(b)
	return base64.RawURLEncoding.EncodeToString(b)
}

func (s *Server) oauthRedirectURI() string {
	return strings.TrimRight(s.cfg.PublicBaseURL, "/") + "/v1/agent-registry/oauth/callback"
}

// buildAuthorizationURL assembles the RFC 6749 + PKCE + RFC 8707 authorization URL.
func buildAuthorizationURL(meta oauthMeta, redirectURI, state, challenge string) (string, error) {
	u, err := url.Parse(meta.AuthorizationEndpoint)
	if err != nil {
		return "", err
	}
	q := u.Query()
	q.Set("response_type", "code")
	q.Set("client_id", meta.ClientID)
	q.Set("redirect_uri", redirectURI)
	q.Set("state", state)
	q.Set("code_challenge", challenge)
	q.Set("code_challenge_method", "S256")
	if len(meta.Scopes) > 0 {
		q.Set("scope", strings.Join(meta.Scopes, " "))
	}
	if meta.Resource != "" {
		q.Set("resource", meta.Resource) // RFC 8707 resource indicator
	}
	u.RawQuery = q.Encode()
	return u.String(), nil
}

// ── /oauth/start ─────────────────────────────────────────────────────────────

func (s *Server) startOAuth(w http.ResponseWriter, r *http.Request) {
	uid, _, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	mid, ok := parseUUIDParam(w, r, "mcp_server_id")
	if !ok {
		return
	}
	var tier, authKind string
	var owner *uuid.UUID
	var metaRaw []byte
	err := s.db.QueryRow(r.Context(),
		`SELECT tier, owner_user_id, auth_kind, oauth_meta FROM mcp_server_registrations
		 WHERE mcp_server_id=$1 AND tier='user' AND owner_user_id=$2`, mid, uid).Scan(&tier, &owner, &authKind, &metaRaw)
	if err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "server not found")
		return
	}
	if authKind != "oauth2" {
		writeError(w, http.StatusBadRequest, "NOT_OAUTH", "this server is not configured for OAuth")
		return
	}
	var meta oauthMeta
	_ = json.Unmarshal(metaRaw, &meta)
	if meta.AuthorizationEndpoint == "" || meta.TokenEndpoint == "" || meta.ClientID == "" {
		writeError(w, http.StatusBadRequest, "OAUTH_INCOMPLETE", "server oauth config is incomplete (authorization_endpoint, token_endpoint, client_id required)")
		return
	}
	verifier := newPKCEVerifier()
	state := newOAuthState()
	redirect := s.oauthRedirectURI()
	if _, err := s.db.Exec(r.Context(),
		`INSERT INTO oauth_flows (state, mcp_server_id, owner_user_id, code_verifier, redirect_uri)
		 VALUES ($1,$2,$3,$4,$5)`, state, mid, uid, verifier, redirect); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not start oauth flow")
		return
	}
	authURL, err := buildAuthorizationURL(meta, redirect, state, pkceS256Challenge(verifier))
	if err != nil {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "invalid authorization_endpoint")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"authorization_url": authURL, "state": state})
}

// ── /oauth/callback (PUBLIC — the AS redirects the browser here) ─────────────

func (s *Server) oauthCallback(w http.ResponseWriter, r *http.Request) {
	if s.db == nil {
		http.Error(w, "database unavailable", http.StatusServiceUnavailable)
		return
	}
	q := r.URL.Query()
	if e := q.Get("error"); e != "" {
		s.redirectOAuthResult(w, r, "error", q.Get("error_description"))
		return
	}
	code, state := q.Get("code"), q.Get("state")
	if code == "" || state == "" {
		s.redirectOAuthResult(w, r, "error", "missing code or state")
		return
	}
	mid, owner, err := s.completeOAuth(r.Context(), state, code)
	if err != nil {
		s.redirectOAuthResult(w, r, "error", err.Error())
		return
	}
	// A freshly-authorized server is now probeable → scan it (pending→active/suspended).
	s.audit(r.Context(), owner, "user", "mcp_server", "oauth_connect", &mid, "", "user", nil)
	s.scanAsync(mid)
	s.redirectOAuthResult(w, r, "connected", "")
}

// completeOAuth consumes the state (single-use), exchanges the code for tokens, and
// seals them. Pure of the async scan/audit so it is unit-testable with a mock pool.
func (s *Server) completeOAuth(ctx context.Context, state, code string) (uuid.UUID, uuid.UUID, error) {
	// Consume the flow row exactly once (bind state → server/owner/verifier).
	var mid, owner uuid.UUID
	var verifier, redirect string
	err := s.db.QueryRow(ctx,
		`DELETE FROM oauth_flows WHERE state=$1 AND expires_at > now()
		 RETURNING mcp_server_id, owner_user_id, code_verifier, redirect_uri`, state).Scan(&mid, &owner, &verifier, &redirect)
	if err != nil {
		return uuid.Nil, uuid.Nil, fmt.Errorf("invalid or expired state")
	}
	var metaRaw []byte
	if err := s.db.QueryRow(ctx, `SELECT oauth_meta FROM mcp_server_registrations WHERE mcp_server_id=$1`, mid).Scan(&metaRaw); err != nil {
		return uuid.Nil, uuid.Nil, fmt.Errorf("server gone")
	}
	var meta oauthMeta
	_ = json.Unmarshal(metaRaw, &meta)
	tok, err := s.exchangeCode(ctx, meta, code, verifier, redirect)
	if err != nil {
		return uuid.Nil, uuid.Nil, fmt.Errorf("token exchange failed")
	}
	if err := s.storeOAuthTokens(ctx, mid, meta, tok); err != nil {
		return uuid.Nil, uuid.Nil, fmt.Errorf("could not store tokens")
	}
	return mid, owner, nil
}

func (s *Server) redirectOAuthResult(w http.ResponseWriter, r *http.Request, status, detail string) {
	dest := strings.TrimRight(s.cfg.PublicBaseURL, "/") + "/extensions?mcp_oauth=" + url.QueryEscape(status)
	if detail != "" {
		dest += "&detail=" + url.QueryEscape(detail)
	}
	http.Redirect(w, r, dest, http.StatusFound)
}

// ── token endpoint calls ─────────────────────────────────────────────────────

type tokenResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	TokenType    string `json:"token_type"`
	ExpiresIn    int64  `json:"expires_in"`
}

func (s *Server) exchangeCode(ctx context.Context, meta oauthMeta, code, verifier, redirect string) (tokenResponse, error) {
	form := url.Values{}
	form.Set("grant_type", "authorization_code")
	form.Set("code", code)
	form.Set("redirect_uri", redirect)
	form.Set("client_id", meta.ClientID)
	form.Set("code_verifier", verifier)
	if meta.Resource != "" {
		form.Set("resource", meta.Resource)
	}
	return s.postToken(ctx, meta.TokenEndpoint, form)
}

func (s *Server) refreshToken(ctx context.Context, meta oauthMeta, refresh string) (tokenResponse, error) {
	form := url.Values{}
	form.Set("grant_type", "refresh_token")
	form.Set("refresh_token", refresh)
	form.Set("client_id", meta.ClientID)
	if meta.Resource != "" {
		form.Set("resource", meta.Resource)
	}
	return s.postToken(ctx, meta.TokenEndpoint, form)
}

// postToken POSTs a form to the token endpoint through the SSRF-safe client (the
// token_endpoint is user-influenced, so it is dialed through the same guard as probes).
func (s *Server) postToken(ctx context.Context, endpoint string, form url.Values) (tokenResponse, error) {
	client := newProbeClient(s.cfg.AllowInternalMcpTargets)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, strings.NewReader(form.Encode()))
	if err != nil {
		return tokenResponse{}, err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Accept", "application/json")
	resp, err := client.Do(req)
	if err != nil {
		return tokenResponse{}, err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode >= 400 {
		return tokenResponse{}, fmt.Errorf("token endpoint %d: %s", resp.StatusCode, snippet(string(body)))
	}
	var tr tokenResponse
	if err := json.Unmarshal(body, &tr); err != nil {
		return tokenResponse{}, fmt.Errorf("token response parse: %w", err)
	}
	if tr.AccessToken == "" {
		return tokenResponse{}, fmt.Errorf("token response missing access_token")
	}
	return tr, nil
}

// storeOAuthTokens seals the access + refresh tokens into the vault and records the
// expiry in oauth_meta. The plaintext never leaves this function.
func (s *Server) storeOAuthTokens(ctx context.Context, mid uuid.UUID, meta oauthMeta, tok tokenResponse) error {
	accessCipher, _, err := s.encryptSecret(tok.AccessToken)
	if err != nil {
		return err
	}
	refreshCipher := ""
	if tok.RefreshToken != "" {
		refreshCipher, _, err = s.encryptSecret(tok.RefreshToken)
		if err != nil {
			return err
		}
	}
	if tok.ExpiresIn > 0 {
		exp := time.Now().UTC().Add(time.Duration(tok.ExpiresIn) * time.Second)
		meta.TokenExpiresAt = &exp
	}
	if tok.TokenType != "" {
		meta.TokenType = tok.TokenType
	}
	metaJSON, _ := json.Marshal(meta)
	_, err = s.db.Exec(ctx,
		`UPDATE mcp_server_registrations
		   SET secret_ciphertext=$2, refresh_ciphertext=$3, oauth_meta=$4, updated_at=now()
		 WHERE mcp_server_id=$1`, mid, accessCipher, refreshCipher, string(metaJSON))
	return err
}

// ── refresh worker ───────────────────────────────────────────────────────────

// StartRefreshWorker refreshes oauth2 tokens nearing expiry. Runs until ctx is done.
func (s *Server) StartRefreshWorker(ctx context.Context) {
	ticker := time.NewTicker(2 * time.Minute)
	go func() {
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				s.refreshExpiringTokens(ctx)
			}
		}
	}()
}

// refreshExpiringTokens finds oauth2 servers whose access token expires within 5
// minutes and refreshes them (rotating before expiry so a turn never hits an expired
// token). Failures are logged into last_health but do not crash the loop.
func (s *Server) refreshExpiringTokens(ctx context.Context) {
	if s.db == nil {
		return
	}
	rows, err := s.db.Query(ctx,
		`SELECT mcp_server_id, oauth_meta, refresh_ciphertext FROM mcp_server_registrations
		 WHERE auth_kind='oauth2' AND refresh_ciphertext <> ''
		   AND (oauth_meta->>'token_expires_at') IS NOT NULL
		   AND (oauth_meta->>'token_expires_at')::timestamptz < now() + interval '5 minutes'`)
	if err != nil {
		return
	}
	type job struct {
		mid     uuid.UUID
		metaRaw []byte
		refresh string
	}
	var jobs []job
	for rows.Next() {
		var j job
		if err := rows.Scan(&j.mid, &j.metaRaw, &j.refresh); err == nil {
			jobs = append(jobs, j)
		}
	}
	rows.Close()
	for _, j := range jobs {
		var meta oauthMeta
		_ = json.Unmarshal(j.metaRaw, &meta)
		refresh, err := s.decryptSecret(j.refresh)
		if err != nil || refresh == "" {
			continue
		}
		tok, err := s.refreshToken(ctx, meta, refresh)
		if err != nil {
			continue // keep the old token; the next tick retries
		}
		if tok.RefreshToken == "" {
			tok.RefreshToken = refresh // some AS omit a rotated refresh token
		}
		if err := s.storeOAuthTokens(ctx, j.mid, meta, tok); err != nil {
			// The AS may have rotated (invalidated) the old refresh token during the
			// exchange; if the store failed we now hold a token we can't persist. Log
			// it so the stuck connection is visible rather than silently dying at expiry.
			slog.Error("oauth refresh store failed", "mcp_server_id", j.mid, "error", err)
		}
	}
}
