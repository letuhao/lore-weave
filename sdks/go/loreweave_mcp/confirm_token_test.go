package loreweave_mcp

import (
	"encoding/json"
	"errors"
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
