// Package svid — S11 JWT-SVID validation (Phase 5b foundation).
// Full mTLS/X.509 SVID is deferred to Envoy sidecar rollout.
package svid

import (
	"fmt"
	"strings"

	"github.com/golang-jwt/jwt/v5"
)

const HeaderPrefix = "SVID "

type Claims struct {
	SpiffeID string `json:"spiffe_id"`
	jwt.RegisteredClaims
}

// ParseAuthorization extracts and validates a JWT-SVID from Authorization header.
func ParseAuthorization(authHeader string, secret []byte) (*Claims, error) {
	if !strings.HasPrefix(authHeader, HeaderPrefix) {
		return nil, fmt.Errorf("missing SVID prefix")
	}
	tokenStr := strings.TrimSpace(strings.TrimPrefix(authHeader, HeaderPrefix))
	tok, err := jwt.ParseWithClaims(tokenStr, &Claims{}, func(t *jwt.Token) (interface{}, error) {
		if t.Method != jwt.SigningMethodHS256 {
			return nil, fmt.Errorf("unexpected signing method")
		}
		return secret, nil
	})
	if err != nil {
		return nil, err
	}
	claims, ok := tok.Claims.(*Claims)
	if !ok || !tok.Valid || claims.SpiffeID == "" {
		return nil, fmt.Errorf("invalid svid")
	}
	return claims, nil
}
