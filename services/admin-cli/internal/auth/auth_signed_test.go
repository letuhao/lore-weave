package auth

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"

	"github.com/loreweave/foundation/contracts/adminjwt"
)

// signedTokenFixture produces (publicKeyPEM, token) for an RS256 admin JWT signed
// the way auth-service signs (correct iss/aud + kid = key fingerprint).
func signedTokenFixture(t *testing.T, mutate func(*adminjwt.AdminClaims), kidOverride string) (string, string) {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("genkey: %v", err)
	}
	der, _ := x509.MarshalPKIXPublicKey(&key.PublicKey)
	pubPEM := string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}))

	kid, err := adminjwt.KeyFingerprint(&key.PublicKey)
	if err != nil {
		t.Fatalf("fingerprint: %v", err)
	}
	if kidOverride != "" {
		kid = kidOverride
	}

	claims := adminjwt.AdminClaims{
		Role:       "admin",
		Scopes:     []string{"admin:read", "admin:destructive"},
		BreakGlass: true,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   "ops-7",
			Issuer:    adminjwt.Issuer,
			Audience:  jwt.ClaimStrings{adminjwt.Audience},
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(10 * time.Minute)),
			ID:        "abcd",
		},
	}
	if mutate != nil {
		mutate(&claims)
	}
	tok := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	tok.Header["kid"] = kid
	s, err := tok.SignedString(key)
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	return pubPEM, s
}

func TestValidate_SignedToken_HappyPath(t *testing.T) {
	pubPEM, tok := signedTokenFixture(t, nil, "")
	t.Setenv(PublicKeyEnv, pubPEM)

	c, err := Validate(tok)
	if err != nil {
		t.Fatalf("Validate signed token: %v", err)
	}
	if c.Subject != "ops-7" || c.Role != "admin" {
		t.Errorf("claims mapped wrong: %+v", c)
	}
	if !c.BreakGlass {
		t.Error("break_glass not mapped")
	}
	if !c.HasScope("admin:destructive") {
		t.Errorf("scopes not mapped: %+v", c.Scopes)
	}
	if c.ExpiresUnix == 0 {
		t.Error("ExpiresUnix not mapped")
	}
}

func TestValidate_SignedToken_NoPublicKeyFailsClosed(t *testing.T) {
	_, tok := signedTokenFixture(t, nil, "")
	// PublicKeyEnv intentionally unset.
	t.Setenv(PublicKeyEnv, "")
	if _, err := Validate(tok); err == nil {
		t.Fatal("expected fail-closed when no public key configured")
	}
}

func TestValidate_SignedToken_WrongKeyRejected(t *testing.T) {
	_, tok := signedTokenFixture(t, nil, "")
	// Configure a DIFFERENT key's PEM.
	otherPEM, _ := signedTokenFixture(t, nil, "")
	t.Setenv(PublicKeyEnv, otherPEM)
	if _, err := Validate(tok); err == nil {
		t.Fatal("expected rejection: token signed by a different key")
	}
}

func TestValidate_SignedToken_KIDMismatchRejected(t *testing.T) {
	pubPEM, tok := signedTokenFixture(t, nil, "deadbeef-wrong-kid")
	t.Setenv(PublicKeyEnv, pubPEM)
	if _, err := Validate(tok); err == nil {
		t.Fatal("expected rejection on kid mismatch")
	}
}

func TestValidate_SignedToken_WrongAudienceRejected(t *testing.T) {
	pubPEM, tok := signedTokenFixture(t, func(c *adminjwt.AdminClaims) {
		c.Audience = jwt.ClaimStrings{"some-other-service"}
	}, "")
	t.Setenv(PublicKeyEnv, pubPEM)
	if _, err := Validate(tok); err == nil {
		t.Fatal("expected rejection on wrong audience")
	}
}
