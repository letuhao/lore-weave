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
	"os"
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

// AllowDevTokensEnv, when set to "1", enables the dev-token shortcut. It MUST
// be unset in production: production fails closed and requires a real signed
// JWT verified against the auth-service key (pending PRR-30 / D-ADMIN-CLI-JWT).
// This prevents the forgeable `dev:` token from ever authenticating a real env.
const AllowDevTokensEnv = "ADMIN_CLI_ALLOW_DEV_TOKENS"

// Validate inspects an admin token and returns Claims on success.
//
// Security posture (PRR-29, fail-closed):
//   - `dev:` tokens are a LOCAL-DEV shortcut, accepted ONLY when
//     ADMIN_CLI_ALLOW_DEV_TOKENS=1. Otherwise rejected — a forged dev token
//     cannot authenticate in production.
//   - Any non-`dev:` token requires real signed-JWT verification, not yet wired
//     (PRR-30). Until then Validate FAILS CLOSED rather than trust an
//     unverified token. Production wiring swaps in an RS256/JWS verifier reading
//     the auth-service signing key; the CALLER (dispatcher) does not change.
//
// Dev-token format (when enabled): dev:<user>:<role>:<scopes-pipe-separated>[:break-glass]
// Scopes use `|` (NOT `,`) because scope strings like `admin:read` contain a
// colon and `:` is the outer field separator.
func Validate(token string) (Claims, error) {
	token = strings.TrimSpace(token)
	if token == "" {
		return Claims{}, fmt.Errorf("%w: empty token", ErrAuth)
	}
	if strings.HasPrefix(token, "dev:") {
		if os.Getenv(AllowDevTokensEnv) != "1" {
			return Claims{}, fmt.Errorf("%w: `dev:` tokens are disabled (fail-closed). Set %s=1 for LOCAL DEV only; production must present a signed JWT (real verifier pending PRR-30 / D-ADMIN-CLI-JWT)", ErrAuth, AllowDevTokensEnv)
		}
		return parseDevToken(token)
	}
	// Non-dev token: real JWT verification is not wired yet (PRR-30). Refuse
	// rather than accept an unverified token.
	return Claims{}, fmt.Errorf("%w: signed-JWT verification not yet wired (PRR-30 / D-ADMIN-CLI-JWT); refusing to authenticate an unverified token", ErrAuth)
}

// parseDevToken parses the dev-token shortcut. Only reached when
// ADMIN_CLI_ALLOW_DEV_TOKENS=1 (see Validate).
func parseDevToken(token string) (Claims, error) {
	body := strings.TrimPrefix(token, "dev:")
	// SplitN(":", 3) so anything after user:role is one big "rest" string
	// (scopes may contain colons; break-glass suffix lives at the end).
	parts := strings.SplitN(body, ":", 3)
	if len(parts) < 3 {
		return Claims{}, fmt.Errorf("%w: bad token shape — expected dev:<user>:<role>:<scopes>[:break-glass]", ErrAuth)
	}
	scopesRaw := parts[2]
	breakGlass := false
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
