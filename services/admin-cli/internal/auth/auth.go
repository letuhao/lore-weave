// Package auth validates the admin JWT issued by auth-service.
//
// V1 (cycle 36) ships a SKELETON: the framework calls Validate() and accepts
// any non-empty token claiming admin scope. Real JWT signature verification +
// scope claims wire up alongside the auth-service admin-scope feature (cycle
// 18+).
//
// Why a skeleton: the policy seam exists so every command in the framework
// already gates on auth.Validate(); future work just swaps the body without
// touching command handlers.
package auth

import (
	"errors"
	"fmt"
	"strings"
)

// ErrAuth is returned by Validate on rejection.
var ErrAuth = errors.New("admin-cli/auth")

// Claims is the in-memory view of an admin JWT.
type Claims struct {
	Subject     string   // user_ref_id
	Role        string   // "admin" | "sre" | "founder"
	Scopes      []string // ["admin:read", "admin:write", "admin:destructive"]
	BreakGlass  bool
	ExpiresUnix int64
}

// Validate inspects a token. V1 SKELETON: token format
//
//	dev:<user>:<role>:<scopes-csv-using-pipe-not-comma>[:break-glass]
//
// Scopes use `|` as separator (NOT `,`) because individual scope strings like
// `admin:read` contain a colon and we use `:` as the outer field separator.
// Example: `dev:ops1:sre:admin:read|admin:destructive`.
//
// Returns Claims on success.
//
// Production swap: replace this with a real RS256/JWS verifier reading the
// auth-service signing key. The CALLER does not change.
func Validate(token string) (Claims, error) {
	token = strings.TrimSpace(token)
	if token == "" {
		return Claims{}, fmt.Errorf("%w: empty token", ErrAuth)
	}
	if !strings.HasPrefix(token, "dev:") {
		return Claims{}, fmt.Errorf("%w: V1 skeleton only accepts `dev:` tokens (real JWT wires in cycle 18+ auth-service)", ErrAuth)
	}
	body := strings.TrimPrefix(token, "dev:")
	// SplitN(":", 3) so anything after user:role is one big "rest" string
	// (scopes may contain colons; break-glass suffix lives at the end).
	parts := strings.SplitN(body, ":", 3)
	if len(parts) < 3 {
		return Claims{}, fmt.Errorf("%w: bad token shape — expected dev:<user>:<role>:<scopes>[:break-glass]", ErrAuth)
	}
	scopesRaw := parts[2]
	breakGlass := false
	// If `:break-glass` is suffixed, slice it off.
	if strings.HasSuffix(scopesRaw, ":break-glass") {
		scopesRaw = strings.TrimSuffix(scopesRaw, ":break-glass")
		breakGlass = true
	}
	c := Claims{
		Subject:    parts[0],
		Role:       parts[1],
		Scopes:     splitScopes(scopesRaw),
		BreakGlass: breakGlass,
	}
	if c.Subject == "" || c.Role == "" {
		return Claims{}, fmt.Errorf("%w: subject/role empty", ErrAuth)
	}
	return c, nil
}

// splitScopes splits the scopes blob on `|` (pipe), trimming whitespace.
// Comma is accepted as a legacy delimiter so older tokens keep working.
func splitScopes(s string) []string {
	delim := "|"
	if !strings.Contains(s, "|") && strings.Contains(s, ",") {
		delim = ","
	}
	parts := strings.Split(s, delim)
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

// HasScope returns true if c carries the given scope.
func (c Claims) HasScope(s string) bool {
	for _, x := range c.Scopes {
		if x == s {
			return true
		}
	}
	return false
}

// RequireScopeForTier returns the scope a caller needs for a tier string.
func RequireScopeForTier(tier string) string {
	switch tier {
	case "tier-1-destructive":
		return "admin:destructive"
	case "tier-2-griefing":
		return "admin:write"
	case "tier-3-informational":
		return "admin:read"
	}
	return "admin:read"
}
