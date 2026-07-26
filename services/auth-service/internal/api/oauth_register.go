package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/loreweave/auth-service/internal/ratelimit"
)

// P5 slice 3 — open Dynamic Client Registration (RFC 7591).
//
//   POST /oauth/register  — PUBLIC (no auth). A third-party MCP client self-registers
//                           a PUBLIC PKCE client (no secret) and gets a client_id back.
//
// Hardening (the locked PO "open DCR behind flag+rate-limit+audit" decision):
//   - kill-switch: OAUTH_DCR_ENABLED (s.oauth.dcrEnabled) → 403 when off.
//   - per-IP rate limit (s.oauth.dcrRL) → 429 before any work/row write.
//   - every attempt (issued OR rejected) is recorded append-only in
//     mcp_oauth_client_registrations for abuse detection.
//
// Open DCR is safe because a registered client is inert on its own: a code is always
// PKCE-bound to the registering client and only minted after the resource owner's
// explicit consent, and the edge enforces scope per call. So accepting an arbitrary
// (well-formed) redirect_uri is the intended RFC 7591 behaviour, not a hole.

// supportedGrantTypes is the only set this AS issues (authorization_code + refresh).
var supportedGrantTypes = map[string]bool{"authorization_code": true, "refresh_token": true}

// Input bounds on the PUBLIC registration endpoint (DoS surface — an unauthenticated
// caller within the rate limit must not be able to push a huge body / huge arrays).
const (
	maxDCRBodyBytes     = 16 << 10 // 16 KiB request body
	maxDCRRedirectURIs  = 10
	maxDCRClientNameLen = 256
)

func (s *Server) oauthRegister(w http.ResponseWriter, r *http.Request) {
	if s.oauth == nil {
		writeOAuthErr(w, http.StatusNotFound, "oauth_disabled", "oauth is not enabled")
		return
	}
	if !s.oauth.dcrEnabled {
		writeOAuthErr(w, http.StatusForbidden, "registration_disabled", "dynamic client registration is disabled")
		return
	}
	ip := ratelimit.ClientIP(r)
	// Rate-limit BEFORE parsing/auditing so a flood is shed without writing rows.
	if s.oauth.dcrRL != nil && !s.oauth.dcrRL.Allow("oauth_register:"+ip) {
		w.Header().Set("Retry-After", "3600")
		writeOAuthErr(w, http.StatusTooManyRequests, "rate_limited", "too many registration requests")
		return
	}

	// Cap the body BEFORE decoding (public endpoint — bound memory). An oversized
	// body makes Decode fail → the invalid_client_metadata branch below.
	r.Body = http.MaxBytesReader(w, r.Body, maxDCRBodyBytes)

	var body struct {
		ClientName              string   `json:"client_name"`
		RedirectURIs            []string `json:"redirect_uris"`
		GrantTypes              []string `json:"grant_types"`
		ResponseTypes           []string `json:"response_types"`
		TokenEndpointAuthMethod string   `json:"token_endpoint_auth_method"`
		Scope                   string   `json:"scope"`
		ScopesRequested         []string `json:"scopes_requested"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		s.auditRegistration(r.Context(), "", body.ClientName, body.RedirectURIs, "rejected", "invalid_client_metadata", ip)
		writeOAuthErr(w, http.StatusBadRequest, "invalid_client_metadata", "malformed or oversized request body")
		return
	}
	if len(body.ClientName) > maxDCRClientNameLen {
		s.auditRegistration(r.Context(), "", "", body.RedirectURIs, "rejected", "invalid_client_metadata", ip)
		writeOAuthErr(w, http.StatusBadRequest, "invalid_client_metadata", "client_name too long")
		return
	}

	// redirect_uris: required, bounded count, each a well-formed absolute URI with no
	// fragment (RFC 7591 §2 / OAuth 2.1). http(s) must carry a host.
	if len(body.RedirectURIs) == 0 || len(body.RedirectURIs) > maxDCRRedirectURIs {
		s.auditRegistration(r.Context(), "", body.ClientName, body.RedirectURIs, "rejected", "invalid_redirect_uri", ip)
		writeOAuthErr(w, http.StatusBadRequest, "invalid_redirect_uri", "between 1 and 10 redirect_uris are required")
		return
	}
	for _, u := range body.RedirectURIs {
		if !validRegistrationRedirectURI(u) {
			s.auditRegistration(r.Context(), "", body.ClientName, body.RedirectURIs, "rejected", "invalid_redirect_uri", ip)
			writeOAuthErr(w, http.StatusBadRequest, "invalid_redirect_uri", "redirect_uri must be an absolute URI without a fragment")
			return
		}
	}

	// We only mint PUBLIC PKCE clients (no secret). Reject an explicit other method.
	if body.TokenEndpointAuthMethod != "" && body.TokenEndpointAuthMethod != "none" {
		s.auditRegistration(r.Context(), "", body.ClientName, body.RedirectURIs, "rejected", "invalid_client_metadata", ip)
		writeOAuthErr(w, http.StatusBadRequest, "invalid_client_metadata", "only token_endpoint_auth_method=none (public PKCE) is supported")
		return
	}
	// grant_types: if supplied, must be a subset of what we issue.
	for _, g := range body.GrantTypes {
		if !supportedGrantTypes[g] {
			s.auditRegistration(r.Context(), "", body.ClientName, body.RedirectURIs, "rejected", "invalid_client_metadata", ip)
			writeOAuthErr(w, http.StatusBadRequest, "invalid_client_metadata", "unsupported grant_type: "+g)
			return
		}
	}
	// response_types: if supplied, only "code".
	for _, rt := range body.ResponseTypes {
		if rt != "code" {
			s.auditRegistration(r.Context(), "", body.ClientName, body.RedirectURIs, "rejected", "invalid_client_metadata", ip)
			writeOAuthErr(w, http.StatusBadRequest, "invalid_client_metadata", "only response_type=code is supported")
			return
		}
	}

	// Requested scopes (advisory) — accept the RFC `scope` string and/or our
	// scopes_requested[]; validate the vocabulary so a typo surfaces at registration.
	requested := body.ScopesRequested
	if body.Scope != "" {
		requested = append(requested, splitScopeParam(body.Scope)...)
	}
	requested = splitScopeParam(strings.Join(requested, " ")) // dedupe + drop '*'
	if len(requested) > 0 && !scopesAllKnown(requested) {
		s.auditRegistration(r.Context(), "", body.ClientName, body.RedirectURIs, "rejected", "invalid_scope", ip)
		writeOAuthErr(w, http.StatusBadRequest, "invalid_scope", "one or more requested scopes are unknown")
		return
	}

	clientID, err := s.insertOAuthClient(r.Context(), body.ClientName, body.RedirectURIs, requested, ip)
	if err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "client registration failed")
		return
	}
	s.auditRegistration(r.Context(), clientID, body.ClientName, body.RedirectURIs, "registered", "", ip)

	w.Header().Set("Cache-Control", "no-store")
	resp := map[string]any{
		"client_id":                  clientID,
		"client_id_issued_at":        time.Now().UTC().Unix(),
		"token_endpoint_auth_method": "none",
		"grant_types":                []string{"authorization_code", "refresh_token"},
		"response_types":             []string{"code"},
		"redirect_uris":              body.RedirectURIs,
		"client_name":                body.ClientName,
	}
	if len(requested) > 0 {
		resp["scope"] = strings.Join(requested, " ")
	}
	writeJSON(w, http.StatusCreated, resp)
}

// validRegistrationRedirectURI: absolute URI, no fragment; http(s) requires a host.
// Custom schemes (native-app redirects) are allowed as long as they're absolute.
func validRegistrationRedirectURI(raw string) bool {
	if raw == "" {
		return false
	}
	u, err := url.Parse(raw)
	if err != nil || u.Scheme == "" || u.Fragment != "" {
		return false
	}
	if (u.Scheme == "http" || u.Scheme == "https") && u.Host == "" {
		return false
	}
	return true
}

// auditRegistration appends one row to mcp_oauth_client_registrations. Best-effort —
// an audit failure must not break a registration (or leak via the error path).
func (s *Server) auditRegistration(ctx context.Context, clientID, name string, redirectURIs []string, outcome, reason, ip string) {
	var cid any
	if clientID != "" {
		cid = clientID
	}
	var rsn any
	if reason != "" {
		rsn = reason
	}
	_, _ = s.pool.Exec(ctx, `
		INSERT INTO mcp_oauth_client_registrations (client_id, client_name, redirect_uris, outcome, reason, created_ip)
		VALUES ($1,$2,$3,$4,$5,$6)`,
		cid, name, redirectURIs, outcome, rsn, ip)
}

// writeOAuthErr emits the RFC 6749/7591 error shape ({error, error_description}) — the
// public OAuth/DCR endpoints face spec-compliant third-party clients that parse it.
func writeOAuthErr(w http.ResponseWriter, status int, errCode, desc string) {
	writeJSON(w, status, map[string]string{"error": errCode, "error_description": desc})
}
