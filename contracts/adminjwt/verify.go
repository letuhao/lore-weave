package adminjwt

import (
	"crypto/rsa"
	"errors"
	"fmt"

	"github.com/golang-jwt/jwt/v5"
)

// ErrVerify is the sentinel wrapped by all verification failures.
var ErrVerify = errors.New("adminjwt: verify")

// Verify validates an admin JWT against pub and returns its claims.
//
// Strict by construction (PRR-29/30 fail-closed):
//   - RS256 ONLY — WithValidMethods rejects alg:none and any HS/EC/PS variant,
//     and the keyfunc re-asserts *jwt.SigningMethodRSA (defense in depth against
//     an alg-confusion downgrade that swaps the public-key bytes in as an HMAC
//     secret).
//   - exp is required and enforced (WithExpirationRequired).
//   - iss and aud are pinned to the package constants.
//   - if expectKID != "", the token's "kid" header MUST equal it. expectKID is
//     KeyFingerprint(pub), so a token signed under a different key — or a stale
//     ADMIN_JWT_PUBLIC_KEY_PEM on the verifier — fails with a clear kid error
//     instead of a silent signature mismatch on every token.
func Verify(tokenStr string, pub *rsa.PublicKey, expectKID string) (AdminClaims, error) {
	if pub == nil {
		return AdminClaims{}, fmt.Errorf("%w: nil public key", ErrVerify)
	}
	parser := jwt.NewParser(
		jwt.WithValidMethods([]string{"RS256"}),
		jwt.WithIssuer(Issuer),
		jwt.WithAudience(Audience),
		jwt.WithExpirationRequired(),
	)
	var claims AdminClaims
	tok, err := parser.ParseWithClaims(tokenStr, &claims, func(t *jwt.Token) (any, error) {
		if _, ok := t.Method.(*jwt.SigningMethodRSA); !ok {
			return nil, fmt.Errorf("%w: unexpected signing method %v", ErrVerify, t.Header["alg"])
		}
		if expectKID != "" {
			kid, _ := t.Header["kid"].(string)
			if kid != expectKID {
				return nil, fmt.Errorf("%w: kid mismatch (token=%q expected=%q)", ErrVerify, kid, expectKID)
			}
		}
		return pub, nil
	})
	if err != nil {
		return AdminClaims{}, fmt.Errorf("%w: %v", ErrVerify, err)
	}
	if !tok.Valid {
		return AdminClaims{}, fmt.Errorf("%w: token invalid", ErrVerify)
	}
	return claims, nil
}
