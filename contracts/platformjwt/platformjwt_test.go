package platformjwt

import (
	"crypto/rand"
	"crypto/rsa"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// signWith builds a token from claims and signs it with the given method/key —
// the test stand-in for the auth-service HS256 signer. For the adversarial
// downgrade cases it also signs with alg:none / RS256 to prove Verify rejects
// them.
func signWith(t *testing.T, method jwt.SigningMethod, key any, claims AccessClaims) string {
	t.Helper()
	tok := jwt.NewWithClaims(method, claims)
	s, err := tok.SignedString(key)
	if err != nil {
		t.Fatalf("sign: %v", err)
	}
	return s
}

const (
	testSubject = "11111111-1111-1111-1111-111111111111"
)

func testSecret() []byte { return []byte("shared-platform-jwt-secret-for-tests") }

func goodClaims() AccessClaims {
	now := time.Now()
	return AccessClaims{
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   testSubject,
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(10 * time.Minute)),
		},
	}
}

func TestVerify_RoundTrip(t *testing.T) {
	tok := signWith(t, jwt.SigningMethodHS256, testSecret(), goodClaims())

	got, err := Verify(tok, testSecret())
	if err != nil {
		t.Fatalf("Verify: %v", err)
	}
	if got.Subject != testSubject {
		t.Errorf("subject = %q, want %q", got.Subject, testSubject)
	}
	id, err := got.UserID()
	if err != nil {
		t.Fatalf("UserID: %v", err)
	}
	if id.String() != testSubject {
		t.Errorf("UserID = %q, want %q", id, testSubject)
	}
}

func TestVerify_RejectsAlgNone(t *testing.T) {
	// alg:none — the classic downgrade to an unsigned token.
	tok := signWith(t, jwt.SigningMethodNone, jwt.UnsafeAllowNoneSignatureType, goodClaims())
	if _, err := Verify(tok, testSecret()); err == nil {
		t.Fatal("expected alg:none to be rejected")
	} else if !errors.Is(err, ErrVerify) {
		t.Errorf("error not wrapped by ErrVerify: %v", err)
	}
}

func TestVerify_RejectsRSDowngrade(t *testing.T) {
	// Alg-confusion: a token minted with an RS256 header. Verify pins HS256, so
	// the asymmetric algorithm must be rejected outright — the verifier must
	// never treat an RS/EC/PS token as if it were HMAC.
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("genkey: %v", err)
	}
	tok := signWith(t, jwt.SigningMethodRS256, priv, goodClaims())
	if _, err := Verify(tok, testSecret()); err == nil {
		t.Fatal("expected RS256 downgrade to be rejected")
	}
}

func TestVerify_RejectsExpired(t *testing.T) {
	c := goodClaims()
	c.ExpiresAt = jwt.NewNumericDate(time.Now().Add(-time.Minute))
	tok := signWith(t, jwt.SigningMethodHS256, testSecret(), c)
	if _, err := Verify(tok, testSecret()); err == nil {
		t.Fatal("expected expired token to be rejected")
	}
}

func TestVerify_RequiresExp(t *testing.T) {
	c := goodClaims()
	c.ExpiresAt = nil
	tok := signWith(t, jwt.SigningMethodHS256, testSecret(), c)
	if _, err := Verify(tok, testSecret()); err == nil {
		t.Fatal("expected missing-exp token to be rejected")
	}
}

func TestVerify_RejectsTamperedSignature(t *testing.T) {
	tok := signWith(t, jwt.SigningMethodHS256, testSecret(), goodClaims())
	// Flip a char at the FRONT of the signature segment, NOT the last char: the
	// last base64url char of a 32-byte HS256 sig encodes only 4 significant bits,
	// so A/B/C/D decode to identical bytes and a last-char flip is a no-op ~6% of
	// runs (flaky). A front char carries a full 6 bits → the decoded signature
	// always changes → verification must fail deterministically.
	i := strings.LastIndexByte(tok, '.') + 1
	b := []byte(tok)
	if b[i] == 'Z' {
		b[i] = 'Y'
	} else {
		b[i] = 'Z'
	}
	if _, err := Verify(string(b), testSecret()); err == nil {
		t.Fatal("expected tampered signature to be rejected")
	}
}

// TestVerify_AcceptsAudAndIss pins Go↔Python parity on the two standard claims
// neither verifier enforces: a real auth token may carry `aud`/`iss`, and Verify
// must accept it (the Python side had to explicitly set verify_aud=False to match
// this, since PyJWT rejects an aud-bearing token by default). A drift here means
// the same token would authenticate through Go services but 401 through Python.
func TestVerify_AcceptsAudAndIss(t *testing.T) {
	c := goodClaims()
	c.Audience = jwt.ClaimStrings{"loreweave-api"}
	c.Issuer = "loreweave-auth"
	tok := signWith(t, jwt.SigningMethodHS256, testSecret(), c)
	got, err := Verify(tok, testSecret())
	if err != nil {
		t.Fatalf("aud/iss-bearing token must verify (Python parity): %v", err)
	}
	if got.Subject != testSubject {
		t.Errorf("subject = %q, want %q", got.Subject, testSubject)
	}
}

func TestVerify_RejectsWrongSecret(t *testing.T) {
	tok := signWith(t, jwt.SigningMethodHS256, testSecret(), goodClaims())
	if _, err := Verify(tok, []byte("a-different-secret")); err == nil {
		t.Fatal("expected wrong-secret token to be rejected")
	}
}

func TestVerify_RejectsEmptySecret(t *testing.T) {
	tok := signWith(t, jwt.SigningMethodHS256, testSecret(), goodClaims())
	if _, err := Verify(tok, nil); err == nil {
		t.Fatal("expected empty secret to be rejected")
	}
	if _, err := Verify(tok, []byte{}); err == nil {
		t.Fatal("expected zero-length secret to be rejected")
	}
}

func TestVerify_RejectsMalformed(t *testing.T) {
	for _, tok := range []string{
		"",
		"not-a-jwt",
		"only.two",
		"aaa.bbb.ccc",
	} {
		if _, err := Verify(tok, testSecret()); err == nil {
			t.Errorf("expected malformed token %q to be rejected", tok)
		}
	}
}

func TestVerify_RejectsNonUUIDSub(t *testing.T) {
	c := goodClaims()
	c.Subject = "not-a-uuid"
	tok := signWith(t, jwt.SigningMethodHS256, testSecret(), c)
	if _, err := Verify(tok, testSecret()); err == nil {
		t.Fatal("expected non-UUID sub to be rejected")
	}
}

func TestVerify_RejectsEmptySub(t *testing.T) {
	c := goodClaims()
	c.Subject = ""
	tok := signWith(t, jwt.SigningMethodHS256, testSecret(), c)
	if _, err := Verify(tok, testSecret()); err == nil {
		t.Fatal("expected empty sub to be rejected")
	}
}
