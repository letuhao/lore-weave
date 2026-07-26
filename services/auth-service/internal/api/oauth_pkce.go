package api

import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"strings"
)

// pkceVerifyS256 returns true iff base64url(sha256(verifier)) == challenge (RFC 7636
// S256). Constant-time compare. We support S256 ONLY (the AS metadata advertises only
// S256) — `plain` is rejected by the caller.
func pkceVerifyS256(verifier, challenge string) bool {
	if verifier == "" || challenge == "" {
		return false
	}
	sum := sha256.Sum256([]byte(verifier))
	computed := base64.RawURLEncoding.EncodeToString(sum[:])
	return subtle.ConstantTimeCompare([]byte(computed), []byte(challenge)) == 1
}

// redirectURIRegistered returns true iff uri EXACTLY matches a registered redirect URI
// (no prefix/substring matching — anti-open-redirect; an attacker can't append a path
// or query to escape to their own host).
func redirectURIRegistered(uri string, registered []string) bool {
	if uri == "" {
		return false
	}
	for _, r := range registered {
		if r == uri {
			return true
		}
	}
	return false
}

// splitScopeParam parses a space-delimited OAuth `scope` string (RFC 6749 §3.3) into a
// deduped slice, dropping empties and the `*` wildcard (never honored for OAuth).
func splitScopeParam(s string) []string {
	seen := map[string]struct{}{}
	out := []string{}
	for _, tok := range strings.Fields(s) {
		if tok == "*" {
			continue
		}
		if _, dup := seen[tok]; dup {
			continue
		}
		seen[tok] = struct{}{}
		out = append(out, tok)
	}
	return out
}

// scopesAllKnown returns true iff every scope is in the advertised vocabulary
// (oauthScopesSupported) — rejects garbage/typo scopes at consent time.
func scopesAllKnown(scopes []string) bool {
	known := map[string]struct{}{}
	for _, s := range oauthScopesSupported {
		known[s] = struct{}{}
	}
	for _, s := range scopes {
		if _, ok := known[s]; !ok {
			return false
		}
	}
	return true
}

// scopesSubset returns true iff every scope in `granted` is present in `requested`
// — the consenting user may NARROW the client's request, never widen it.
func scopesSubset(granted, requested []string) bool {
	set := map[string]struct{}{}
	for _, s := range requested {
		set[s] = struct{}{}
	}
	for _, g := range granted {
		if _, ok := set[g]; !ok {
			return false
		}
	}
	return true
}
