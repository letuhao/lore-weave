package loreweave_mcp

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

const testConfirmSecret = "test-confirm-secret"

func TestConfirmToken_RoundTrip(t *testing.T) {
	user := uuid.New()
	res := uuid.New()
	payload := map[string]any{"ids": []string{"a", "b"}}

	tok, err := MintConfirmToken(testConfirmSecret, user, res, "book.publish", payload, 5*time.Minute)
	if err != nil {
		t.Fatalf("Mint = %v", err)
	}
	claims, err := VerifyConfirmToken(testConfirmSecret, tok)
	if err != nil {
		t.Fatalf("Verify = %v", err)
	}
	if claims.UserID != user || claims.ResourceID != res {
		t.Errorf("claims user/res = %v/%v, want %v/%v", claims.UserID, claims.ResourceID, user, res)
	}
	if claims.Descriptor != "book.publish" {
		t.Errorf("claims descriptor = %q, want book.publish (intent must be bound)", claims.Descriptor)
	}
	var got map[string]any
	if err := json.Unmarshal(claims.Payload, &got); err != nil {
		t.Fatalf("payload unmarshal = %v", err)
	}
	if ids, _ := got["ids"].([]any); len(ids) != 2 {
		t.Errorf("payload ids = %v, want 2 elements", got["ids"])
	}
}

func TestConfirmToken_Expired(t *testing.T) {
	tok, err := MintConfirmToken(testConfirmSecret, uuid.New(), uuid.New(), "x", nil, -1*time.Second)
	if err != nil {
		t.Fatalf("Mint = %v", err)
	}
	if _, err := VerifyConfirmToken(testConfirmSecret, tok); !errors.Is(err, ErrConfirmTokenExpired) {
		t.Fatalf("Verify = %v, want ErrConfirmTokenExpired", err)
	}
}

func TestConfirmToken_Tampered(t *testing.T) {
	tok, err := MintConfirmToken(testConfirmSecret, uuid.New(), uuid.New(), "x", map[string]any{"x": 1}, time.Minute)
	if err != nil {
		t.Fatalf("Mint = %v", err)
	}
	// Flip the first character of the payload segment → signature no longer matches.
	b := []byte(tok)
	if b[0] == 'A' {
		b[0] = 'B'
	} else {
		b[0] = 'A'
	}
	if _, err := VerifyConfirmToken(testConfirmSecret, string(b)); !errors.Is(err, ErrConfirmTokenInvalid) {
		t.Fatalf("tampered Verify = %v, want ErrConfirmTokenInvalid", err)
	}

	// Malformed (no separator) is also invalid.
	if _, err := VerifyConfirmToken(testConfirmSecret, "garbage"); !errors.Is(err, ErrConfirmTokenInvalid) {
		t.Fatalf("malformed Verify = %v, want ErrConfirmTokenInvalid", err)
	}
}

// TestConfirmToken_DescriptorTamperEvident is the confused-deputy regression
// guard: the descriptor (intent) is inside the HMAC, so re-encoding the payload
// segment with a DIFFERENT descriptor — even though it is still valid JSON and
// still base64url — MUST break the signature. This is what stops a token minted
// for "book.publish" from being silently re-pointed at "book.delete".
func TestConfirmToken_DescriptorTamperEvident(t *testing.T) {
	user := uuid.New()
	res := uuid.New()

	tok, err := MintConfirmToken(testConfirmSecret, user, res, "book.publish", map[string]any{"x": 1}, time.Minute)
	if err != nil {
		t.Fatalf("Mint = %v", err)
	}

	// Decode the payload segment, swap the descriptor to "book.delete", re-encode
	// it as valid JSON+base64url, and reattach the ORIGINAL signature. The token is
	// structurally well-formed; only the descriptor changed.
	parts := strings.Split(tok, ".")
	if len(parts) != 2 {
		t.Fatalf("token has %d parts, want 2", len(parts))
	}
	body, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		t.Fatalf("decode payload = %v", err)
	}
	var claims ConfirmClaims
	if err := json.Unmarshal(body, &claims); err != nil {
		t.Fatalf("unmarshal claims = %v", err)
	}
	if claims.Descriptor != "book.publish" {
		t.Fatalf("precondition: minted descriptor = %q, want book.publish", claims.Descriptor)
	}
	claims.Descriptor = "book.delete" // tamper the intent
	tampered, err := json.Marshal(claims)
	if err != nil {
		t.Fatalf("marshal tampered = %v", err)
	}
	forged := base64.RawURLEncoding.EncodeToString(tampered) + "." + parts[1]

	if _, err := VerifyConfirmToken(testConfirmSecret, forged); !errors.Is(err, ErrConfirmTokenInvalid) {
		t.Fatalf("descriptor-tampered Verify = %v, want ErrConfirmTokenInvalid (descriptor is inside the HMAC)", err)
	}
}

// TestConfirmToken_DescriptorBoundExactly asserts that a validly-minted token's
// verified Descriptor is returned EXACTLY as minted — so a confirm route
// dispatching on claims.Descriptor cannot be fooled into running the wrong action.
func TestConfirmToken_DescriptorBoundExactly(t *testing.T) {
	tok, err := MintConfirmToken(testConfirmSecret, uuid.New(), uuid.New(), "book.delete", nil, time.Minute)
	if err != nil {
		t.Fatalf("Mint = %v", err)
	}
	claims, err := VerifyConfirmToken(testConfirmSecret, tok)
	if err != nil {
		t.Fatalf("Verify = %v", err)
	}
	if claims.Descriptor != "book.delete" {
		t.Fatalf("verified descriptor = %q, want exactly book.delete", claims.Descriptor)
	}
}

// TestConfirmToken_AtExpiryBoundary pins the `>=` expiry check: a token whose Exp
// is exactly the current second is REJECTED (expired), not accepted. The token is
// minted with ttl=0 so Exp == now-at-mint; by verify time now >= Exp holds.
func TestConfirmToken_AtExpiryBoundary(t *testing.T) {
	tok, err := MintConfirmToken(testConfirmSecret, uuid.New(), uuid.New(), "x", nil, 0)
	if err != nil {
		t.Fatalf("Mint = %v", err)
	}
	if _, err := VerifyConfirmToken(testConfirmSecret, tok); !errors.Is(err, ErrConfirmTokenExpired) {
		t.Fatalf("at-expiry Verify = %v, want ErrConfirmTokenExpired (Exp==now must be rejected)", err)
	}
}

func TestConfirmToken_WrongSecretRejected(t *testing.T) {
	tok, err := MintConfirmToken("secret-A", uuid.New(), uuid.New(), "x", nil, time.Minute)
	if err != nil {
		t.Fatalf("Mint = %v", err)
	}
	// Verify under a different secret → invalid signature.
	if _, err := VerifyConfirmToken("secret-B", tok); !errors.Is(err, ErrConfirmTokenInvalid) {
		t.Fatalf("Verify under wrong secret = %v, want ErrConfirmTokenInvalid", err)
	}
}

func TestConfirmToken_FailsClosedWithoutSecret(t *testing.T) {
	if _, err := MintConfirmToken("", uuid.New(), uuid.New(), "x", nil, time.Minute); !errors.Is(err, ErrConfirmTokenInvalid) {
		t.Fatalf("Mint without secret = %v, want ErrConfirmTokenInvalid", err)
	}
	if _, err := VerifyConfirmToken("", "x.y"); !errors.Is(err, ErrConfirmTokenInvalid) {
		t.Fatalf("Verify without secret = %v, want ErrConfirmTokenInvalid", err)
	}
}
