package api

import (
	"errors"
	"net/http/httptest"
	"testing"

	"github.com/golang-jwt/jwt/v5"
)

func TestValidEmail(t *testing.T) {
	tests := []struct {
		in   string
		want bool
	}{
		{"a@b.co", true},
		{"user.name+tag@example.com", true},
		{"", false},
		{"no-at", false},
		{"spaces @x.com", false},
	}
	for _, tt := range tests {
		if got := validEmail(tt.in); got != tt.want {
			t.Errorf("validEmail(%q) = %v, want %v", tt.in, got, tt.want)
		}
	}
}

func TestValidPassword(t *testing.T) {
	min := 8
	if !validPassword("abcdefg1", min) {
		t.Fatal("letter+digit+len ok")
	}
	if validPassword("abcdefgh", min) {
		t.Fatal("no digit")
	}
	if validPassword("12345678", min) {
		t.Fatal("no letter")
	}
	if validPassword("short1", min) {
		t.Fatal("too short")
	}
}

func TestBearerToken(t *testing.T) {
	r := httptest.NewRequest("GET", "/", nil)
	if bearerToken(r) != "" {
		t.Fatal("empty")
	}
	r.Header.Set("Authorization", "Bearer  tok123 ")
	if bearerToken(r) != "tok123" {
		t.Fatalf("got %q", bearerToken(r))
	}
	r.Header.Set("Authorization", "bearer  lower ")
	if bearerToken(r) != "lower" {
		t.Fatalf("case: %q", bearerToken(r))
	}
}

func TestJWTErrorCode(t *testing.T) {
	if jwtErrorCode(nil) != "" {
		t.Fatal("nil")
	}
	if jwtErrorCode(jwt.ErrTokenExpired) != "AUTH_TOKEN_EXPIRED" {
		t.Fatal(jwtErrorCode(jwt.ErrTokenExpired))
	}
	if jwtErrorCode(jwt.ErrTokenMalformed) != "AUTH_TOKEN_INVALID" {
		t.Fatal(jwtErrorCode(jwt.ErrTokenMalformed))
	}
	if jwtErrorCode(errors.New("other")) != "AUTH_TOKEN_INVALID" {
		t.Fatal(jwtErrorCode(errors.New("other")))
	}
}
