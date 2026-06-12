package adminjwt

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// signWith builds a token from claims, sets kid, and signs with the given
// method/key — the test stand-in for the auth-service signer. RS256 signing is
// what auth-service's KMS path reproduces byte-for-byte (proven by its own
// golden-vector test); here we only need valid tokens to exercise Verify.
func signWith(t *testing.T, method jwt.SigningMethod, key any, kid string, claims AdminClaims) string {
	t.Helper()
	tok := jwt.NewWithClaims(method, claims)
	if kid != "" {
		tok.Header["kid"] = kid
	}
	s, err := tok.SignedString(key)
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	return s
}

func goodClaims() AdminClaims {
	now := time.Now()
	return AdminClaims{
		Role:       "admin",
		Scopes:     []string{"admin:read", "admin:write"},
		BreakGlass: false,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   "11111111-1111-1111-1111-111111111111",
			Issuer:    Issuer,
			Audience:  jwt.ClaimStrings{Audience},
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(10 * time.Minute)),
			ID:        "22222222-2222-2222-2222-222222222222",
		},
	}
}

func newKey(t *testing.T) (*rsa.PrivateKey, string) {
	t.Helper()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("genkey: %v", err)
	}
	fp, err := KeyFingerprint(&priv.PublicKey)
	if err != nil {
		t.Fatalf("fingerprint: %v", err)
	}
	return priv, fp
}

func TestVerify_RoundTrip(t *testing.T) {
	priv, kid := newKey(t)
	tok := signWith(t, jwt.SigningMethodRS256, priv, kid, goodClaims())

	got, err := Verify(tok, &priv.PublicKey, kid)
	if err != nil {
		t.Fatalf("Verify: %v", err)
	}
	if got.Subject != "11111111-1111-1111-1111-111111111111" {
		t.Errorf("subject = %q", got.Subject)
	}
	if got.Role != "admin" {
		t.Errorf("role = %q", got.Role)
	}
	if len(got.Scopes) != 2 || got.Scopes[0] != "admin:read" {
		t.Errorf("scopes = %v", got.Scopes)
	}
	if got.BreakGlass {
		t.Error("break_glass should be false")
	}
}

func TestVerify_RejectsAlgNone(t *testing.T) {
	priv, kid := newKey(t)
	// alg:none token — the classic downgrade.
	tok := signWith(t, jwt.SigningMethodNone, jwt.UnsafeAllowNoneSignatureType, kid, goodClaims())
	if _, err := Verify(tok, &priv.PublicKey, kid); err == nil {
		t.Fatal("expected alg:none to be rejected")
	}
}

func TestVerify_RejectsHSDowngrade(t *testing.T) {
	priv, kid := newKey(t)
	// Alg-confusion: attacker signs HS256 using the (public) PKIX bytes as the
	// HMAC secret, hoping the verifier feeds the public key in as a symmetric key.
	pubDER, err := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	tok := signWith(t, jwt.SigningMethodHS256, pubDER, kid, goodClaims())
	if _, err := Verify(tok, &priv.PublicKey, kid); err == nil {
		t.Fatal("expected HS256 downgrade to be rejected")
	}
}

func TestVerify_RejectsExpired(t *testing.T) {
	priv, kid := newKey(t)
	c := goodClaims()
	c.ExpiresAt = jwt.NewNumericDate(time.Now().Add(-time.Minute))
	tok := signWith(t, jwt.SigningMethodRS256, priv, kid, c)
	if _, err := Verify(tok, &priv.PublicKey, kid); err == nil {
		t.Fatal("expected expired token to be rejected")
	}
}

func TestVerify_RequiresExp(t *testing.T) {
	priv, kid := newKey(t)
	c := goodClaims()
	c.ExpiresAt = nil
	tok := signWith(t, jwt.SigningMethodRS256, priv, kid, c)
	if _, err := Verify(tok, &priv.PublicKey, kid); err == nil {
		t.Fatal("expected missing-exp token to be rejected")
	}
}

func TestVerify_RejectsKIDMismatch(t *testing.T) {
	priv, kid := newKey(t)
	tok := signWith(t, jwt.SigningMethodRS256, priv, kid, goodClaims())
	if _, err := Verify(tok, &priv.PublicKey, "deadbeef-not-the-kid"); err == nil {
		t.Fatal("expected kid mismatch to be rejected")
	}
}

func TestVerify_RejectsWrongIssuerAudience(t *testing.T) {
	priv, kid := newKey(t)

	cIss := goodClaims()
	cIss.Issuer = "evil-issuer"
	if _, err := Verify(signWith(t, jwt.SigningMethodRS256, priv, kid, cIss), &priv.PublicKey, kid); err == nil {
		t.Error("expected wrong issuer to be rejected")
	}

	cAud := goodClaims()
	cAud.Audience = jwt.ClaimStrings{"some-other-service"}
	if _, err := Verify(signWith(t, jwt.SigningMethodRS256, priv, kid, cAud), &priv.PublicKey, kid); err == nil {
		t.Error("expected wrong audience to be rejected")
	}
}

func TestVerify_RejectsWrongKey(t *testing.T) {
	priv, kid := newKey(t)
	other, _ := newKey(t)
	tok := signWith(t, jwt.SigningMethodRS256, priv, kid, goodClaims())
	// Verify against a DIFFERENT public key but pass the original kid so the kid
	// check passes and we exercise the signature check itself.
	if _, err := Verify(tok, &other.PublicKey, kid); err == nil {
		t.Fatal("expected wrong-key signature to be rejected")
	}
}

func TestParseRSAPublicKeyPEM_AcceptsSPKI(t *testing.T) {
	priv, _ := newKey(t)
	der, err := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	spki := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der})

	pub, err := ParseRSAPublicKeyPEM(spki)
	if err != nil {
		t.Fatalf("ParseRSAPublicKeyPEM: %v", err)
	}
	if pub.N.Cmp(priv.PublicKey.N) != 0 {
		t.Error("parsed key modulus differs from original")
	}
}

func TestParseRSAPublicKeyPEM_RejectsPKCS1(t *testing.T) {
	priv, _ := newKey(t)
	// PKCS#1 "RSA PUBLIC KEY" — a valid RSA public key in the WRONG envelope.
	pkcs1 := pem.EncodeToMemory(&pem.Block{
		Type:  "RSA PUBLIC KEY",
		Bytes: x509.MarshalPKCS1PublicKey(&priv.PublicKey),
	})
	if _, err := ParseRSAPublicKeyPEM(pkcs1); err == nil {
		t.Fatal("expected PKCS#1 RSA PUBLIC KEY block to be rejected (SPKI only)")
	}
}

func TestParseRSAPublicKeyPEM_RejectsGarbage(t *testing.T) {
	if _, err := ParseRSAPublicKeyPEM([]byte("not a pem")); err == nil {
		t.Fatal("expected non-PEM input to be rejected")
	}
}

func TestKeyFingerprint_StableAndKeyBound(t *testing.T) {
	priv, _ := newKey(t)
	fp1, err := KeyFingerprint(&priv.PublicKey)
	if err != nil {
		t.Fatalf("fingerprint: %v", err)
	}
	fp2, _ := KeyFingerprint(&priv.PublicKey)
	if fp1 != fp2 {
		t.Error("fingerprint not stable for the same key")
	}
	other, _ := newKey(t)
	fpOther, _ := KeyFingerprint(&other.PublicKey)
	if fp1 == fpOther {
		t.Error("fingerprint collided across different keys")
	}
	if len(fp1) != 64 { // hex of 32-byte SHA-256
		t.Errorf("fingerprint length = %d, want 64", len(fp1))
	}
}

func TestValidateBreakGlass(t *testing.T) {
	base := BreakGlassRequest{
		PrimaryActor:   "alice",
		SecondaryActor: "bob",
		Reason:         repeat("x", MinReasonLen),
		IncidentTicket: "INC-1",
		RequestedTTL:   time.Hour,
	}
	if err := ValidateBreakGlass(base); err != nil {
		t.Fatalf("valid request rejected: %v", err)
	}

	bad := map[string]func(*BreakGlassRequest){
		"empty primary":     func(r *BreakGlassRequest) { r.PrimaryActor = "" },
		"empty secondary":   func(r *BreakGlassRequest) { r.SecondaryActor = "" },
		"same actor":        func(r *BreakGlassRequest) { r.SecondaryActor = r.PrimaryActor },
		"short reason":      func(r *BreakGlassRequest) { r.Reason = repeat("x", MinReasonLen-1) },
		"whitespace reason": func(r *BreakGlassRequest) { r.Reason = repeat(" ", MinReasonLen+10) },
		"no ticket":         func(r *BreakGlassRequest) { r.IncidentTicket = "" },
		"zero ttl":          func(r *BreakGlassRequest) { r.RequestedTTL = 0 },
		"ttl too long":      func(r *BreakGlassRequest) { r.RequestedTTL = MaxBreakGlassTTL + time.Second },
	}
	for name, mut := range bad {
		t.Run(name, func(t *testing.T) {
			r := base
			mut(&r)
			if err := ValidateBreakGlass(r); err == nil {
				t.Errorf("%s: expected rejection", name)
			}
		})
	}
}

func repeat(s string, n int) string {
	out := make([]byte, 0, len(s)*n)
	for i := 0; i < n; i++ {
		out = append(out, s...)
	}
	return string(out)
}
