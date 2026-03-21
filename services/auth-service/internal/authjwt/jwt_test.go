package authjwt

import (
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
)

func TestSignParseRoundTrip(t *testing.T) {
	secret := []byte("01234567890123456789012345678901")
	userID := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	sid := uuid.MustParse("22222222-2222-2222-2222-222222222222")

	tok, err := SignAccess(secret, userID, sid, time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	claims, err := ParseAccess(secret, tok)
	if err != nil {
		t.Fatal(err)
	}
	if claims.Subject != userID.String() || claims.SessionID != sid.String() {
		t.Fatalf("claims: sub=%q sid=%q", claims.Subject, claims.SessionID)
	}
}

func TestParseWrongSecret(t *testing.T) {
	secret := []byte("01234567890123456789012345678901")
	other := []byte("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
	userID := uuid.New()
	sid := uuid.New()
	tok, err := SignAccess(secret, userID, sid, time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	_, err = ParseAccess(other, tok)
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestParseMalformed(t *testing.T) {
	secret := []byte("01234567890123456789012345678901")
	_, err := ParseAccess(secret, "not-a-jwt")
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestParseExpired(t *testing.T) {
	secret := []byte("01234567890123456789012345678901")
	userID := uuid.New()
	sid := uuid.New()
	tok, err := SignAccess(secret, userID, sid, -time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	_, err = ParseAccess(secret, tok)
	if err == nil {
		t.Fatal("expected error")
	}
	if !errors.Is(err, jwt.ErrTokenExpired) {
		t.Fatalf("want ErrTokenExpired, got %v", err)
	}
}

func TestParseWrongSigningMethod(t *testing.T) {
	secret := []byte("01234567890123456789012345678901")
	// Unsigned token triggers unexpected method in parser callback
	tok := jwt.New(jwt.SigningMethodNone)
	tokString, err := tok.SignedString(jwt.UnsafeAllowNoneSignatureType)
	if err != nil {
		t.Fatal(err)
	}
	_, err = ParseAccess(secret, tokString)
	if err == nil {
		t.Fatal("expected error")
	}
	if !strings.Contains(err.Error(), "unexpected signing method") {
		t.Fatalf("unexpected error: %v", err)
	}
}
