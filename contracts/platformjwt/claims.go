package platformjwt

import (
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
)

// AccessClaims is the wire contract for a LoreWeave platform *user* access JWT.
//
// The user token is intentionally minimal: it carries only the standard
// RegisteredClaims, and the ONLY field every consumer reads is Subject ("sub"),
// which holds the authenticated user's UUID. There is no role/scope array here
// (that is the admin token's job — see contracts/adminjwt.AdminClaims); a
// regular user's authorization is resolved per-resource via E0 grants, not from
// the token body.
//
// RegisteredClaims supplies the standard fields:
//   - Subject  ("sub") — the user's UUID (see UserID); load-bearing.
//   - ExpiresAt("exp") — required (Verify enforces presence).
//   - IssuedAt ("iat") — optional.
//
// iss/aud are deliberately NOT pinned (see the package doc): auth-service does
// not set them on user tokens and the inline verifiers never checked them.
type AccessClaims struct {
	jwt.RegisteredClaims
}

// UserID parses the Subject ("sub") claim as the user's UUID. Verify already
// guarantees this succeeds for any token it returns, so callers that received
// their claims from Verify can treat the error as impossible; it is exported for
// call sites that parse claims by other means.
func (c AccessClaims) UserID() (uuid.UUID, error) {
	return uuid.Parse(c.Subject)
}
