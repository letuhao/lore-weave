package api

import (
	"encoding/base64"
	"math/big"
	"net/http"
	"time"

	"github.com/loreweave/auth-service/internal/authjwt"
	"github.com/loreweave/auth-service/internal/ratelimit"
)

// oauthDeps holds the P5 public-MCP OAuth 2.1 subsystem state. It reuses the admin
// RS256 signer (the key the edge verifies against via /oauth/jwks) but mints tokens
// with a DISTINCT issuer + audience (see authjwt.OAuthAccessClaims). nil => OAuth
// endpoints are disabled (404).
type oauthDeps struct {
	signer     authjwt.DigestSigner
	issuer     string
	resource   string // canonical MCP resource URL = the token audience (RFC 8707)
	accessTTL  time.Duration
	defaultRPM int
	codeTTL    time.Duration      // authorization-code TTL (single-use)
	refreshTTL time.Duration      // refresh-token TTL
	consentURL string             // FE consent page the authorize endpoint redirects to
	dcrEnabled bool               // open DCR (RFC 7591) /oauth/register kill-switch
	dcrRL      *ratelimit.Limiter // per-IP rate limiter for /oauth/register (nil = unlimited)
}

// OAuthOptions carries the P5 OAuth subsystem config for EnableOAuth.
type OAuthOptions struct {
	Issuer         string
	Resource       string
	AccessTTL      time.Duration
	DefaultRPM     int
	CodeTTL        time.Duration
	RefreshTTL     time.Duration
	ConsentURL     string
	DCREnabled     bool
	DCRRatePerHour int // per-IP /oauth/register cap (0 = unlimited)
}

// EnableOAuth turns on the P5 OAuth endpoints. Called by main when cfg.OAuthEnabled
// (admin signer present AND public MCP flag on), and by tests with an in-process
// signer. Reuses the admin RS256 signer to mint audience-bound access tokens with a
// distinct issuer.
func (s *Server) EnableOAuth(signer authjwt.DigestSigner, o OAuthOptions) {
	var dcrRL *ratelimit.Limiter
	if o.DCRRatePerHour > 0 {
		dcrRL = ratelimit.New(time.Hour, o.DCRRatePerHour)
	}
	s.oauth = &oauthDeps{
		signer:     signer,
		issuer:     o.Issuer,
		resource:   o.Resource,
		accessTTL:  o.AccessTTL,
		defaultRPM: o.DefaultRPM,
		codeTTL:    o.CodeTTL,
		refreshTTL: o.RefreshTTL,
		consentURL: o.ConsentURL,
		dcrEnabled: o.DCREnabled,
		dcrRL:      dcrRL,
	}
}

// oauthJWKS serves GET /oauth/jwks — an RFC 7517 JWK Set with the single RS256
// public key the edge uses to verify OAuth access tokens LOCALLY (no auth-service
// round-trip on the hot path). The kid matches the JWT header kid so the edge can
// select the right key across rotations.
func (s *Server) oauthJWKS(w http.ResponseWriter, r *http.Request) {
	if s.oauth == nil {
		writeErr(w, http.StatusNotFound, "oauth_disabled", "oauth is not enabled")
		return
	}
	pub := s.oauth.signer.PublicKey()
	jwk := map[string]any{
		"kty": "RSA",
		"use": "sig",
		"alg": "RS256",
		"kid": s.oauth.signer.KID(),
		"n":   base64.RawURLEncoding.EncodeToString(pub.N.Bytes()),
		"e":   base64.RawURLEncoding.EncodeToString(big.NewInt(int64(pub.E)).Bytes()),
	}
	w.Header().Set("Cache-Control", "public, max-age=3600")
	writeJSON(w, http.StatusOK, map[string]any{"keys": []any{jwk}})
}

// oauthASMetadata serves GET /.well-known/oauth-authorization-server — the RFC 8414
// Authorization Server Metadata a spec-compliant MCP client reads to discover the
// authorize/token/register/jwks endpoints. The endpoint URLs are absolute, rooted at
// the public app URL (the external origin the client reached us on). PKCE S256 only.
func (s *Server) oauthASMetadata(w http.ResponseWriter, r *http.Request) {
	if s.oauth == nil {
		writeErr(w, http.StatusNotFound, "oauth_disabled", "oauth is not enabled")
		return
	}
	base := s.oauthPublicBase()
	meta := map[string]any{
		"issuer":                                s.oauth.issuer,
		"authorization_endpoint":                base + "/oauth/authorize",
		"token_endpoint":                        base + "/oauth/token",
		"jwks_uri":                              base + "/oauth/jwks",
		"scopes_supported":                      oauthScopesSupported,
		"response_types_supported":              []string{"code"},
		"grant_types_supported":                 []string{"authorization_code", "refresh_token"},
		"code_challenge_methods_supported":      []string{"S256"},
		"token_endpoint_auth_methods_supported": []string{"none"},
	}
	// Only advertise the DCR endpoint when it's actually enabled (RFC 8414 — advertise
	// supported endpoints only; advertising it while disabled sends clients into a 403).
	if s.oauth.dcrEnabled {
		meta["registration_endpoint"] = base + "/oauth/register"
	}
	w.Header().Set("Cache-Control", "public, max-age=3600")
	writeJSON(w, http.StatusOK, meta)
}

// oauthPublicBase is the external origin to root absolute discovery URLs at. Prefer
// the configured PublicAppURL; fall back to the resource URL minus its /mcp suffix.
func (s *Server) oauthPublicBase() string {
	if s.cfg.PublicAppURL != "" {
		return trimTrailingSlash(s.cfg.PublicAppURL)
	}
	// resource is "<base>/mcp"; strip the suffix to recover the origin.
	res := trimTrailingSlash(s.oauth.resource)
	if len(res) > 4 && res[len(res)-4:] == "/mcp" {
		return res[:len(res)-4]
	}
	return res
}

func trimTrailingSlash(s string) string {
	for len(s) > 0 && s[len(s)-1] == '/' {
		s = s[:len(s)-1]
	}
	return s
}

// oauthScopesSupported is the advertised scope vocabulary (tier + domain), mirroring
// the edge TOOL_POLICY / FE MCP_SCOPES. Advisory for discovery; the edge is the
// authoritative scope gate.
var oauthScopesSupported = []string{
	"read", "paid_read", "write_auto", "write_confirm",
	"domain:book", "domain:glossary", "domain:knowledge", "domain:translation",
	"domain:composition", "domain:lore_enrichment", "domain:jobs", "domain:settings",
	"domain:catalog",
}
