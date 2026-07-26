package api

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
)

// TestRequireUserID covers the platform-user JWT path migrated to the shared
// contracts/platformjwt verifier (there was no direct test before the migration).
// The verifier is HS256-pinned, requires exp, and requires a UUID sub; a valid
// token is accepted, and every failure mode returns (uuid.Nil, false).
func TestRequireUserID(t *testing.T) {
	t.Parallel()
	secret := "12345678901234567890123456789012"
	uid := uuid.New()

	sign := func(claims jwt.RegisteredClaims, method jwt.SigningMethod, key any) string {
		tok := jwt.NewWithClaims(method, claims)
		s, err := tok.SignedString(key)
		if err != nil {
			t.Fatalf("sign: %v", err)
		}
		return s
	}
	valid := jwt.RegisteredClaims{
		Subject:   uid.String(),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(5 * time.Minute)),
	}

	srv := &Server{secret: []byte(secret)}
	reqWith := func(authz string) *http.Request {
		r := httptest.NewRequest(http.MethodGet, "/", nil)
		if authz != "" {
			r.Header.Set("Authorization", authz)
		}
		return r
	}

	// Accept: a valid HS256 token → the sub UUID.
	got, ok := srv.requireUserID(reqWith("Bearer " + sign(valid, jwt.SigningMethodHS256, []byte(secret))))
	if !ok || got != uid {
		t.Fatalf("valid token: got=%v ok=%v, want uid=%v", got, ok, uid)
	}

	// Reject: missing header, no Bearer prefix, wrong secret, expired, non-UUID sub.
	expired := valid
	expired.ExpiresAt = jwt.NewNumericDate(time.Now().Add(-time.Minute))
	noExp := jwt.RegisteredClaims{Subject: uid.String()}
	badSub := jwt.RegisteredClaims{Subject: "not-a-uuid", ExpiresAt: valid.ExpiresAt}

	cases := map[string]string{
		"missing header":   "",
		"no bearer prefix": sign(valid, jwt.SigningMethodHS256, []byte(secret)),
		"wrong secret":     "Bearer " + sign(valid, jwt.SigningMethodHS256, []byte("00000000000000000000000000000000")),
		"expired":          "Bearer " + sign(expired, jwt.SigningMethodHS256, []byte(secret)),
		"missing exp":      "Bearer " + sign(noExp, jwt.SigningMethodHS256, []byte(secret)),
		"non-UUID sub":     "Bearer " + sign(badSub, jwt.SigningMethodHS256, []byte(secret)),
		"garbage":          "Bearer not.a.jwt",
	}
	for name, authz := range cases {
		if _, ok := srv.requireUserID(reqWith(authz)); ok {
			t.Errorf("%s: expected reject, got ok=true", name)
		}
	}
}
