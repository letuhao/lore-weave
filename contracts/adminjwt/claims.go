package adminjwt

import "github.com/golang-jwt/jwt/v5"

// Issuer and Audience are pinned: every admin token is issued by the
// auth-service ("iss") for consumption by admin-cli ("aud"). Verify rejects a
// token whose iss/aud do not match, so a token minted for a different audience
// cannot be replayed against admin-cli.
const (
	Issuer   = "loreweave-auth"
	Audience = "admin-cli"
)

// AdminClaims is the wire contract for an admin / break-glass JWT. The JSON tags
// are load-bearing — they are the on-the-wire claim names shared by signer and
// verifier; do not rename without bumping both sides.
//
// RegisteredClaims supplies the standard fields:
//   - Subject  ("sub") — the admin principal's user_ref_id
//   - Issuer   ("iss") — Issuer constant above
//   - Audience ("aud") — Audience constant above
//   - ExpiresAt("exp") — required (Verify enforces presence)
//   - IssuedAt ("iat")
//   - ID       ("jti") — unique per token (replay forensics)
type AdminClaims struct {
	Role       string   `json:"role"`
	Scopes     []string `json:"scopes"`
	BreakGlass bool     `json:"break_glass"`
	jwt.RegisteredClaims
}
