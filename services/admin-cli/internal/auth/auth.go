// Package auth validates the admin JWT issued by auth-service.
//
// 074/075: Validate now performs REAL RS256 signature verification of the
// auth-service-signed admin JWT (via the shared contracts/adminjwt module),
// against the public key in ADMIN_JWT_PUBLIC_KEY_PEM, with a kid binding so a
// stale/wrong key fails loudly. The `dev:` token shortcut remains, gated by
// ADMIN_CLI_ALLOW_DEV_TOKENS=1 for LOCAL DEV only. Everything is fail-closed:
// an empty/unverifiable token, or a missing public key for a signed token, is
// rejected rather than trusted.
//
// The framework's command handlers gate on auth.Validate() and did not change
// when the verifier body was swapped in.
package auth

import (
	"crypto/rsa"
	"errors"
	"fmt"
	"os"
	"strings"
	"sync"

	"github.com/loreweave/foundation/contracts/adminjwt"
)

// Parsed-public-key memo. The PEM comes from an env var that is effectively
// constant for a CLI process; we cache the parse + fingerprint keyed on the PEM
// string so repeated Validate calls (e.g. primary + second-actor token in one
// dispatch) don't re-parse, while a changed PEM (tests) still re-parses.
var (
	pubKeyMu  sync.RWMutex
	cachedPEM string
	cachedPub *rsa.PublicKey
	cachedKID string
)

func loadPublicKey(pemStr string) (*rsa.PublicKey, string, error) {
	pubKeyMu.RLock()
	if cachedPub != nil && pemStr == cachedPEM {
		pub, kid := cachedPub, cachedKID
		pubKeyMu.RUnlock()
		return pub, kid, nil
	}
	pubKeyMu.RUnlock()

	pub, err := adminjwt.ParseRSAPublicKeyPEM([]byte(pemStr))
	if err != nil {
		return nil, "", err
	}
	kid, err := adminjwt.KeyFingerprint(pub)
	if err != nil {
		return nil, "", err
	}
	pubKeyMu.Lock()
	cachedPEM, cachedPub, cachedKID = pemStr, pub, kid
	pubKeyMu.Unlock()
	return pub, kid, nil
}

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

// PublicKeyEnv holds the auth-service admin-signing RSA PUBLIC key (SPKI PEM).
// Required to verify production (non-dev) signed admin JWTs. Public keys are not
// secret; the kid binding (fingerprint) detects a stale/wrong key.
const PublicKeyEnv = "ADMIN_JWT_PUBLIC_KEY_PEM"

// Validate inspects an admin token and returns Claims on success.
//
// Security posture (PRR-29/PRR-30, fail-closed):
//   - `dev:` tokens are a LOCAL-DEV shortcut, accepted ONLY when
//     ADMIN_CLI_ALLOW_DEV_TOKENS=1. Otherwise rejected — a forged dev token
//     cannot authenticate in production.
//   - Any non-`dev:` token is verified as a real RS256 admin JWT against the
//     auth-service public key (see validateSigned). If no public key is
//     configured, or the signature/kid/iss/aud/exp fail, Validate FAILS CLOSED.
//     The CALLER (dispatcher) is unchanged.
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
			return Claims{}, fmt.Errorf("%w: `dev:` tokens are disabled (fail-closed). Set %s=1 for LOCAL DEV only; production must present a signed JWT", ErrAuth, AllowDevTokensEnv)
		}
		return parseDevToken(token)
	}
	// Non-dev token: verify the auth-service-signed admin JWT (RS256, 074/075).
	return validateSigned(token)
}

// validateSigned verifies a real RS256 admin JWT against the auth-service public
// key (ADMIN_JWT_PUBLIC_KEY_PEM). Fail-closed: if no public key is configured we
// refuse rather than trust an unverified token. The kid is bound to the key's
// fingerprint so a stale/wrong configured key fails loudly.
func validateSigned(token string) (Claims, error) {
	pemStr := os.Getenv(PublicKeyEnv)
	if pemStr == "" {
		return Claims{}, fmt.Errorf("%w: %s not set; cannot verify a signed admin JWT (fail-closed)", ErrAuth, PublicKeyEnv)
	}
	pub, kid, err := loadPublicKey(pemStr)
	if err != nil {
		return Claims{}, fmt.Errorf("%w: bad %s: %v", ErrAuth, PublicKeyEnv, err)
	}
	ac, err := adminjwt.Verify(token, pub, kid)
	if err != nil {
		return Claims{}, fmt.Errorf("%w: %v", ErrAuth, err)
	}
	c := Claims{
		Subject:    ac.Subject,
		Role:       ac.Role,
		Scopes:     ac.Scopes,
		BreakGlass: ac.BreakGlass,
	}
	if ac.ExpiresAt != nil {
		c.ExpiresUnix = ac.ExpiresAt.Unix()
	}
	return c, nil
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
