package api

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/loreweave/auth-service/internal/authjwt"
)

// P5 OAuth 2.1 authorization-code + PKCE flow (slice 2).
//
//   GET  /oauth/authorize           — validate the request, redirect a logged-in user to the FE consent page
//   POST /v1/account/oauth/consent  — (Bearer JWT) the user approves a DOWNSCOPED grant → mints a single-use code
//   POST /oauth/token               — code+PKCE → access+refresh token; refresh_token → rotate
//   POST /internal/oauth/clients    — (X-Internal-Token) seed/register a client (slice 3 adds the public RFC 7591 endpoint)
//
// Public PKCE clients hold no secret; the code_verifier IS the proof of possession.

type oauthClient struct {
	ClientID                string
	ClientName              string
	RedirectURIs            []string
	GrantTypes              []string
	TokenEndpointAuthMethod string
	ScopesRequested         []string
	Status                  string
}

func (s *Server) lookupOAuthClient(ctx context.Context, clientID string) (oauthClient, bool, error) {
	var c oauthClient
	err := s.pool.QueryRow(ctx, `
		SELECT client_id, client_name, redirect_uris, grant_types, token_endpoint_auth_method, scopes_requested, status
		FROM mcp_oauth_clients WHERE client_id = $1`, clientID,
	).Scan(&c.ClientID, &c.ClientName, &c.RedirectURIs, &c.GrantTypes, &c.TokenEndpointAuthMethod, &c.ScopesRequested, &c.Status)
	if errors.Is(err, pgx.ErrNoRows) {
		return oauthClient{}, false, nil
	}
	if err != nil {
		return oauthClient{}, false, err
	}
	return c, true, nil
}

// insertOAuthClient registers a new public PKCE client and returns its generated id.
// Shared by the slice-2 internal seed route and (slice 3) the public RFC 7591 endpoint.
func (s *Server) insertOAuthClient(ctx context.Context, name string, redirectURIs, scopesRequested []string, createdIP string) (string, error) {
	clientID := "mcp_" + randToken(18)
	_, err := s.pool.Exec(ctx, `
		INSERT INTO mcp_oauth_clients (client_id, client_name, redirect_uris, grant_types, token_endpoint_auth_method, scopes_requested, status, created_ip)
		VALUES ($1,$2,$3,'{authorization_code,refresh_token}','none',$4,'active',$5)`,
		clientID, name, redirectURIs, scopesRequested, createdIP)
	if err != nil {
		return "", err
	}
	return clientID, nil
}

// --- GET /oauth/authorize ---------------------------------------------------

func (s *Server) oauthAuthorize(w http.ResponseWriter, r *http.Request) {
	if s.oauth == nil {
		writeErr(w, http.StatusNotFound, "oauth_disabled", "oauth is not enabled")
		return
	}
	q := r.URL.Query()
	clientID := q.Get("client_id")
	redirectURI := q.Get("redirect_uri")

	client, found, err := s.lookupOAuthClient(r.Context(), clientID)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "server_error", "lookup failed")
		return
	}
	// Client / redirect_uri problems are shown DIRECTLY (never redirect to an
	// unvalidated/attacker URI — anti-open-redirect).
	if !found || client.Status != "active" {
		writeErr(w, http.StatusBadRequest, "invalid_client", "unknown or disabled client")
		return
	}
	if !redirectURIRegistered(redirectURI, client.RedirectURIs) {
		writeErr(w, http.StatusBadRequest, "invalid_redirect_uri", "redirect_uri is not registered for this client")
		return
	}
	// From here the redirect_uri is trusted — other errors go back to the client per OAuth.
	state := q.Get("state")
	if q.Get("response_type") != "code" {
		redirectError(w, r, redirectURI, "unsupported_response_type", state)
		return
	}
	if q.Get("code_challenge") == "" || q.Get("code_challenge_method") != "S256" {
		redirectError(w, r, redirectURI, "invalid_request", state) // PKCE S256 required
		return
	}
	if q.Get("resource") != s.oauth.resource {
		redirectError(w, r, redirectURI, "invalid_target", state) // RFC 8707 — wrong audience
		return
	}
	scopes := splitScopeParam(q.Get("scope"))
	if len(scopes) == 0 || !scopesAllKnown(scopes) {
		redirectError(w, r, redirectURI, "invalid_scope", state)
		return
	}

	// Hand off to the FE consent page (a logged-in user approves there, then POSTs to
	// the consent endpoint). We forward the validated request params verbatim.
	consent, err := url.Parse(s.oauth.consentURL)
	if err != nil || s.oauth.consentURL == "" {
		writeErr(w, http.StatusInternalServerError, "server_error", "consent URL not configured")
		return
	}
	cq := consent.Query()
	for _, k := range []string{"client_id", "redirect_uri", "scope", "state", "code_challenge", "code_challenge_method", "resource"} {
		if v := q.Get(k); v != "" {
			cq.Set(k, v)
		}
	}
	// Forward the registered display name so the consent screen can name the app
	// (the FE only ever has the opaque client_id otherwise). Display-only.
	if client.ClientName != "" {
		cq.Set("client_name", client.ClientName)
	}
	consent.RawQuery = cq.Encode()
	http.Redirect(w, r, consent.String(), http.StatusFound)
}

func redirectError(w http.ResponseWriter, r *http.Request, redirectURI, code, state string) {
	u, err := url.Parse(redirectURI)
	if err != nil {
		writeErr(w, http.StatusBadRequest, code, "invalid redirect_uri")
		return
	}
	q := u.Query()
	q.Set("error", code)
	if state != "" {
		q.Set("state", state)
	}
	u.RawQuery = q.Encode()
	http.Redirect(w, r, u.String(), http.StatusFound)
}

// --- POST /v1/account/oauth/consent (Bearer JWT owner) ----------------------

func (s *Server) oauthConsent(w http.ResponseWriter, r *http.Request) {
	if s.oauth == nil {
		writeErr(w, http.StatusNotFound, "oauth_disabled", "oauth is not enabled")
		return
	}
	claims, err := s.parseAccess(r)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, jwtErrorCode(err), "invalid access token")
		return
	}
	owner, err := uuid.Parse(claims.Subject)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, "AUTH_TOKEN_INVALID", "invalid subject")
		return
	}
	var body struct {
		Action              string   `json:"action"` // "" / "approve" (default) | "deny"
		ClientID            string   `json:"client_id"`
		RedirectURI         string   `json:"redirect_uri"`
		GrantedScopes       []string `json:"granted_scopes"`
		RequestedScopes     []string `json:"requested_scopes"`
		CodeChallenge       string   `json:"code_challenge"`
		CodeChallengeMethod string   `json:"code_challenge_method"`
		Resource            string   `json:"resource"`
		State               string   `json:"state"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "invalid_request", "bad body")
		return
	}
	ctx := r.Context()
	client, found, err := s.lookupOAuthClient(ctx, body.ClientID)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "server_error", "lookup failed")
		return
	}
	if !found || client.Status != "active" {
		writeErr(w, http.StatusBadRequest, "invalid_client", "unknown or disabled client")
		return
	}
	if !redirectURIRegistered(body.RedirectURI, client.RedirectURIs) {
		writeErr(w, http.StatusBadRequest, "invalid_redirect_uri", "redirect_uri not registered")
		return
	}
	// Deny — the user refuses. The redirect_uri is now validated (registered for
	// this client), so we bounce per OAuth with error=access_denied. The FE never
	// constructs this redirect itself (anti-open-redirect — a direct link with an
	// unregistered redirect_uri 400s above instead of leaking the trusted origin).
	if body.Action == "deny" {
		u, perr := url.Parse(body.RedirectURI)
		if perr != nil {
			writeErr(w, http.StatusBadRequest, "invalid_redirect_uri", "redirect_uri not parseable")
			return
		}
		rq := u.Query()
		rq.Set("error", "access_denied")
		if body.State != "" {
			rq.Set("state", body.State)
		}
		u.RawQuery = rq.Encode()
		writeJSON(w, http.StatusOK, map[string]any{"redirect_uri": u.String()})
		return
	}
	if body.CodeChallenge == "" || body.CodeChallengeMethod != "S256" {
		writeErr(w, http.StatusBadRequest, "invalid_request", "PKCE S256 required")
		return
	}
	if body.Resource != s.oauth.resource {
		writeErr(w, http.StatusBadRequest, "invalid_target", "resource mismatch")
		return
	}
	granted := splitScopeParam(strings.Join(body.GrantedScopes, " "))
	if len(granted) == 0 || !scopesAllKnown(granted) {
		writeErr(w, http.StatusBadRequest, "invalid_scope", "unknown or empty scopes")
		return
	}
	// The user may only NARROW the client's request (when it was supplied).
	if len(body.RequestedScopes) > 0 && !scopesSubset(granted, splitScopeParam(strings.Join(body.RequestedScopes, " "))) {
		writeErr(w, http.StatusBadRequest, "invalid_scope", "granted scopes exceed the request")
		return
	}

	// Upsert the per-(owner,client) grant with the downscoped scopes (refresh set at token time).
	if _, err := s.pool.Exec(ctx, `
		INSERT INTO mcp_oauth_grants (owner_user_id, client_id, scopes, resource)
		VALUES ($1,$2,$3,$4)
		ON CONFLICT (owner_user_id, client_id)
		DO UPDATE SET scopes = EXCLUDED.scopes, resource = EXCLUDED.resource, revoked_at = NULL`,
		owner, body.ClientID, granted, body.Resource); err != nil {
		writeErr(w, http.StatusInternalServerError, "server_error", "grant upsert failed")
		return
	}

	// Mint a single-use authorization code (stored hashed, PKCE-bound, short-lived).
	code := randToken(32)
	if _, err := s.pool.Exec(ctx, `
		INSERT INTO mcp_oauth_codes (code_hash, owner_user_id, client_id, scopes, redirect_uri, resource, code_challenge, code_challenge_method, expires_at)
		VALUES ($1,$2,$3,$4,$5,$6,$7,'S256',$8)`,
		hashOpaque(code), owner, body.ClientID, granted, body.RedirectURI, body.Resource, body.CodeChallenge,
		time.Now().UTC().Add(s.oauth.codeTTL)); err != nil {
		writeErr(w, http.StatusInternalServerError, "server_error", "code mint failed")
		return
	}

	// Hand the browser the redirect target (FE performs the navigation).
	u, _ := url.Parse(body.RedirectURI)
	rq := u.Query()
	rq.Set("code", code)
	if body.State != "" {
		rq.Set("state", body.State)
	}
	u.RawQuery = rq.Encode()
	writeJSON(w, http.StatusOK, map[string]any{"redirect_uri": u.String()})
}

// --- POST /oauth/token ------------------------------------------------------

func (s *Server) oauthToken(w http.ResponseWriter, r *http.Request) {
	if s.oauth == nil {
		writeErr(w, http.StatusNotFound, "oauth_disabled", "oauth is not enabled")
		return
	}
	// Accept form-encoded (the OAuth default) or JSON.
	grantType, get := tokenParams(r)
	switch grantType {
	case "authorization_code":
		s.oauthTokenByCode(w, r, get)
	case "refresh_token":
		s.oauthTokenByRefresh(w, r, get)
	default:
		writeErr(w, http.StatusBadRequest, "unsupported_grant_type", "grant_type must be authorization_code or refresh_token")
	}
}

func (s *Server) oauthTokenByCode(w http.ResponseWriter, r *http.Request, get func(string) string) {
	ctx := r.Context()
	code := get("code")
	verifier := get("code_verifier")
	clientID := get("client_id")
	redirectURI := get("redirect_uri")
	if code == "" || verifier == "" {
		writeErr(w, http.StatusBadRequest, "invalid_request", "code and code_verifier required")
		return
	}
	// Atomic single-use consume: claim the code iff unconsumed AND unexpired.
	var (
		owner          uuid.UUID
		storedClient   string
		scopes         []string
		storedRedirect string
		resource       string
		challenge      string
	)
	err := s.pool.QueryRow(ctx, `
		UPDATE mcp_oauth_codes
		SET consumed_at = now()
		WHERE code_hash = $1 AND consumed_at IS NULL AND expires_at > now()
		RETURNING owner_user_id, client_id, scopes, redirect_uri, resource, code_challenge`, hashOpaque(code),
	).Scan(&owner, &storedClient, &scopes, &storedRedirect, &resource, &challenge)
	if errors.Is(err, pgx.ErrNoRows) {
		writeErr(w, http.StatusBadRequest, "invalid_grant", "code invalid, expired, or already used")
		return
	}
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "server_error", "code consume failed")
		return
	}
	if clientID != "" && clientID != storedClient {
		writeErr(w, http.StatusBadRequest, "invalid_grant", "client mismatch")
		return
	}
	if redirectURI != "" && redirectURI != storedRedirect {
		writeErr(w, http.StatusBadRequest, "invalid_grant", "redirect_uri mismatch")
		return
	}
	if !pkceVerifyS256(verifier, challenge) {
		writeErr(w, http.StatusBadRequest, "invalid_grant", "PKCE verification failed")
		return
	}

	// Fetch the grant id (the grant_id that rides x-mcp-key-id) for this (owner,client).
	var grantID uuid.UUID
	if err := s.pool.QueryRow(ctx,
		`SELECT id FROM mcp_oauth_grants WHERE owner_user_id=$1 AND client_id=$2`, owner, storedClient,
	).Scan(&grantID); err != nil {
		writeErr(w, http.StatusInternalServerError, "server_error", "grant missing")
		return
	}
	s.issueOAuthTokens(w, ctx, owner, grantID, storedClient, scopes, resource)
}

func (s *Server) oauthTokenByRefresh(w http.ResponseWriter, r *http.Request, get func(string) string) {
	ctx := r.Context()
	refresh := get("refresh_token")
	if refresh == "" {
		writeErr(w, http.StatusBadRequest, "invalid_request", "refresh_token required")
		return
	}
	var (
		grantID  uuid.UUID
		owner    uuid.UUID
		clientID string
		scopes   []string
		resource string
	)
	err := s.pool.QueryRow(ctx, `
		SELECT id, owner_user_id, client_id, scopes, resource
		FROM mcp_oauth_grants
		WHERE refresh_token_hash = $1 AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now())`,
		hashOpaque(refresh),
	).Scan(&grantID, &owner, &clientID, &scopes, &resource)
	if errors.Is(err, pgx.ErrNoRows) {
		writeErr(w, http.StatusBadRequest, "invalid_grant", "refresh token invalid, revoked, or expired")
		return
	}
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "server_error", "refresh lookup failed")
		return
	}
	s.issueOAuthTokens(w, ctx, owner, grantID, clientID, scopes, resource)
}

// issueOAuthTokens mints an access token + a ROTATED refresh token (stored hashed on
// the grant) and writes the OAuth token response. Shared by the code + refresh paths.
func (s *Server) issueOAuthTokens(w http.ResponseWriter, ctx context.Context, owner, grantID uuid.UUID, clientID string, scopes []string, resource string) {
	access, err := authjwt.SignOAuthAccessToken(ctx, s.oauth.signer, authjwt.OAuthMintInput{
		Issuer:   s.oauth.issuer,
		Subject:  owner,
		Audience: resource,
		ClientID: clientID,
		GrantID:  grantID.String(),
		Scope:    strings.Join(scopes, " "),
		TTL:      s.oauth.accessTTL,
	})
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "server_error", "token mint failed")
		return
	}
	refresh := randToken(32)
	if _, err := s.pool.Exec(ctx, `
		UPDATE mcp_oauth_grants
		SET refresh_token_hash = $1, expires_at = $2, last_used_at = now()
		WHERE id = $3`,
		hashOpaque(refresh), time.Now().UTC().Add(s.oauth.refreshTTL), grantID); err != nil {
		writeErr(w, http.StatusInternalServerError, "server_error", "refresh persist failed")
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	writeJSON(w, http.StatusOK, map[string]any{
		"access_token":  access.Token,
		"token_type":    "Bearer",
		"expires_in":    int(s.oauth.accessTTL.Seconds()),
		"refresh_token": refresh,
		"scope":         strings.Join(scopes, " "),
	})
}

// --- POST /internal/oauth/clients (X-Internal-Token) — seed/register --------

func (s *Server) internalRegisterOAuthClient(w http.ResponseWriter, r *http.Request) {
	if s.oauth == nil {
		writeErr(w, http.StatusNotFound, "oauth_disabled", "oauth is not enabled")
		return
	}
	var body struct {
		ClientName      string   `json:"client_name"`
		RedirectURIs    []string `json:"redirect_uris"`
		ScopesRequested []string `json:"scopes_requested"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || len(body.RedirectURIs) == 0 {
		writeErr(w, http.StatusBadRequest, "invalid_request", "redirect_uris required")
		return
	}
	clientID, err := s.insertOAuthClient(r.Context(), body.ClientName, body.RedirectURIs, body.ScopesRequested, "")
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "server_error", "client insert failed")
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"client_id":                  clientID,
		"token_endpoint_auth_method": "none",
		"grant_types":                []string{"authorization_code", "refresh_token"},
		"redirect_uris":              body.RedirectURIs,
	})
}

// --- helpers ----------------------------------------------------------------

// tokenParams returns the grant_type + a getter over form OR JSON body params.
func tokenParams(r *http.Request) (string, func(string) string) {
	ct := r.Header.Get("Content-Type")
	if strings.HasPrefix(ct, "application/json") {
		var m map[string]any
		_ = json.NewDecoder(r.Body).Decode(&m)
		get := func(k string) string {
			if v, ok := m[k].(string); ok {
				return v
			}
			return ""
		}
		return get("grant_type"), get
	}
	_ = r.ParseForm()
	return r.PostFormValue("grant_type"), r.PostFormValue
}

// randToken returns a URL-safe random token of n random bytes.
func randToken(n int) string {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		// rand.Read failing is fatal-grade; return empty so callers fail closed.
		return ""
	}
	return base64.RawURLEncoding.EncodeToString(b)
}
