package platformjwt

import (
	"errors"
	"fmt"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
)

// ErrVerify is the sentinel wrapped by all verification failures. Callers that
// only need accept/reject can compare with errors.Is(err, ErrVerify); the
// wrapped message carries the specific reason for logs.
var ErrVerify = errors.New("platformjwt: verify")

// Verify validates a platform user JWT against the shared HS256 secret and
// returns its claims. It is the shared replacement for the inline
// `accessClaims{}` + `jwt.ParseWithClaims(... SigningMethodHS256)` blocks that
// each domain service carried; the accept/reject behavior is identical to those
// blocks, with two intentional hardenings (exp required, sub must be a UUID)
// that real platform tokens already satisfy.
//
// Strict by construction (fail-closed):
//   - HS256 ONLY — WithValidMethods rejects alg:none and any RS/EC/PS variant,
//     and the keyfunc re-asserts *jwt.SigningMethodHMAC (defense in depth
//     against an alg-confusion downgrade).
//   - exp is required and enforced (WithExpirationRequired).
//   - sub is parsed as a UUID; a token whose subject is not a UUID is rejected.
//
// secret is the shared symmetric platform-JWT secret (the []byte form each
// service already holds, e.g. []byte(cfg.JWTSecret)). An empty secret is a
// misconfiguration and is rejected rather than used to verify.
func Verify(tokenStr string, secret []byte) (*AccessClaims, error) {
	if len(secret) == 0 {
		return nil, fmt.Errorf("%w: empty secret", ErrVerify)
	}
	parser := jwt.NewParser(
		jwt.WithValidMethods([]string{"HS256"}),
		jwt.WithExpirationRequired(),
	)
	var claims AccessClaims
	tok, err := parser.ParseWithClaims(tokenStr, &claims, func(t *jwt.Token) (any, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("%w: unexpected signing method %v", ErrVerify, t.Header["alg"])
		}
		return secret, nil
	})
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrVerify, err)
	}
	if !tok.Valid {
		return nil, fmt.Errorf("%w: token invalid", ErrVerify)
	}
	if _, err := uuid.Parse(claims.Subject); err != nil {
		return nil, fmt.Errorf("%w: sub is not a valid UUID: %v", ErrVerify, err)
	}
	return &claims, nil
}
