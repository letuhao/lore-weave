package authjwt

import (
	"context"
	"crypto/rsa"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/adminjwt"

	"github.com/loreweave/auth-service/internal/authjwt/signertest"
)

func loadFixedSigner(t *testing.T) *signertest.LocalRSASigner {
	t.Helper()
	pemBytes, err := os.ReadFile("testdata/admin_test_key.pem")
	if err != nil {
		t.Fatalf("read test key: %v", err)
	}
	block, _ := pem.Decode(pemBytes)
	if block == nil {
		t.Fatal("no PEM block in test key")
	}
	key, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		t.Fatalf("parse PKCS8: %v", err)
	}
	rsaKey, ok := key.(*rsa.PrivateKey)
	if !ok {
		t.Fatalf("test key is not RSA: %T", key)
	}
	signer, err := signertest.New(rsaKey)
	if err != nil {
		t.Fatalf("signertest.New: %v", err)
	}
	return signer
}

// fixedClaims are deterministic (fixed iat/exp/jti) so the assembled token is a
// stable golden value for the FIXED test key.
func fixedClaims() adminjwt.AdminClaims {
	return adminjwt.AdminClaims{
		Role:       "admin",
		Scopes:     []string{"admin:read", "admin:write", "admin:destructive"},
		BreakGlass: false,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:  "11111111-1111-1111-1111-111111111111",
			Issuer:   adminjwt.Issuer,
			Audience: jwt.ClaimStrings{adminjwt.Audience},
			// Fixed timestamps keep the assembled token deterministic for the
			// wire/golden assertions; exp is far-future so Verify's expiry check
			// passes without coupling the test to wall-clock time.
			IssuedAt:  jwt.NewNumericDate(time.Unix(1700000000, 0).UTC()),
			ExpiresAt: jwt.NewNumericDate(time.Unix(4102444800, 0).UTC()), // 2100-01-01Z
			ID:        "22222222-2222-2222-2222-222222222222",
		},
	}
}

// TestAssemble_WireContract pins the RS256 wire assembly: deterministic output,
// exact header bytes, and round-trip verification through the real public-key
// PEM decode path. This is the regression guard the design's r1/r3 reviews
// required (KMS produces the same bytes; only the signing primitive differs).
func TestAssemble_WireContract(t *testing.T) {
	signer := loadFixedSigner(t)
	ctx := context.Background()
	claims := fixedClaims()

	tok, err := assembleRS256(ctx, signer, claims)
	if err != nil {
		t.Fatalf("assembleRS256: %v", err)
	}

	// Determinism: PKCS1v15 over a fixed key + fixed claims is byte-stable.
	tok2, _ := assembleRS256(ctx, signer, claims)
	if tok != tok2 {
		t.Fatal("assembleRS256 is not deterministic for a fixed key+claims")
	}

	parts := strings.Split(tok, ".")
	if len(parts) != 3 {
		t.Fatalf("expected 3 JWT segments, got %d", len(parts))
	}

	// Header bytes are pinned exactly: {"alg":"RS256","typ":"JWT","kid":"<fp>"}.
	hdrJSON, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		t.Fatalf("decode header: %v", err)
	}
	wantHdr := `{"alg":"RS256","typ":"JWT","kid":"` + signer.KID() + `"}`
	if string(hdrJSON) != wantHdr {
		t.Errorf("header mismatch:\n got %s\nwant %s", hdrJSON, wantHdr)
	}

	// Verify through the SPKI-PEM decode path (not an in-memory key) so the
	// GetPublicKey DER→PEM→*rsa.PublicKey chain is exercised.
	der, err := x509.MarshalPKIXPublicKey(signer.PublicKey())
	if err != nil {
		t.Fatalf("marshal pub: %v", err)
	}
	spkiPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der})
	pub, err := adminjwt.ParseRSAPublicKeyPEM(spkiPEM)
	if err != nil {
		t.Fatalf("ParseRSAPublicKeyPEM: %v", err)
	}
	got, err := adminjwt.Verify(tok, pub, signer.KID())
	if err != nil {
		t.Fatalf("adminjwt.Verify rejected an assembled token: %v", err)
	}
	if got.Subject != "11111111-1111-1111-1111-111111111111" || got.Role != "admin" || len(got.Scopes) != 3 {
		t.Errorf("verified claims unexpected: %+v", got)
	}

	// Sanity: the claims segment decodes to the same claims we signed.
	var rt adminjwt.AdminClaims
	cb, _ := base64.RawURLEncoding.DecodeString(parts[1])
	if err := json.Unmarshal(cb, &rt); err != nil {
		t.Fatalf("decode claims: %v", err)
	}
	if rt.ID != "22222222-2222-2222-2222-222222222222" {
		t.Errorf("jti mismatch: %s", rt.ID)
	}
}

func TestSignAdmin_VerifyRoundTrip(t *testing.T) {
	signer := loadFixedSigner(t)
	ctx := context.Background()
	subject := mustUUID(t, "33333333-3333-3333-3333-333333333333")

	issued, err := SignAdmin(ctx, signer, subject, "sre", []string{"admin:read"}, 15*time.Minute)
	if err != nil {
		t.Fatalf("SignAdmin: %v", err)
	}
	got, err := adminjwt.Verify(issued.Token, signer.PublicKey(), signer.KID())
	if err != nil {
		t.Fatalf("Verify: %v", err)
	}
	if got.Subject != subject.String() {
		t.Errorf("subject = %s", got.Subject)
	}
	if got.Role != "sre" {
		t.Errorf("role = %s", got.Role)
	}
	if got.BreakGlass {
		t.Error("admin token must not have break_glass=true")
	}
	if issued.JTI.String() != got.ID {
		t.Errorf("jti mismatch: issued=%s claim=%s", issued.JTI, got.ID)
	}
	if !issued.ExpiresAt.After(issued.IssuedAt) {
		t.Error("expiry not after issuance")
	}
}

func TestSignBreakGlass_SetsClaim(t *testing.T) {
	signer := loadFixedSigner(t)
	ctx := context.Background()
	subject := mustUUID(t, "44444444-4444-4444-4444-444444444444")

	issued, err := SignBreakGlass(ctx, signer, subject, "founder", []string{"admin:destructive"}, time.Hour)
	if err != nil {
		t.Fatalf("SignBreakGlass: %v", err)
	}
	got, err := adminjwt.Verify(issued.Token, signer.PublicKey(), signer.KID())
	if err != nil {
		t.Fatalf("Verify: %v", err)
	}
	if !got.BreakGlass {
		t.Error("break-glass token must have break_glass=true")
	}
}

func mustUUID(t *testing.T, s string) uuid.UUID {
	t.Helper()
	u, err := uuid.Parse(s)
	if err != nil {
		t.Fatalf("parse uuid: %v", err)
	}
	return u
}
