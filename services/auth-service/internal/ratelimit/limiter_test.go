package ratelimit

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestAllowWithinMax(t *testing.T) {
	l := New(10*time.Second, 3)
	if !l.Allow("k1") || !l.Allow("k1") || !l.Allow("k1") {
		t.Fatal("expected 3 allows in window")
	}
	if l.Allow("k1") {
		t.Fatal("4th should be denied")
	}
}

func TestSeparateKeys(t *testing.T) {
	l := New(10*time.Second, 1)
	if !l.Allow("a") {
		t.Fatal("a first")
	}
	if l.Allow("a") {
		t.Fatal("a second denied")
	}
	if !l.Allow("b") {
		t.Fatal("b independent")
	}
}

func TestWindowReset(t *testing.T) {
	l := New(30*time.Millisecond, 2)
	if !l.Allow("w") || !l.Allow("w") {
		t.Fatal("two allows")
	}
	if l.Allow("w") {
		t.Fatal("third denied")
	}
	time.Sleep(35 * time.Millisecond)
	if !l.Allow("w") {
		t.Fatal("after window should allow")
	}
}

func TestSweepEvictsExpiredEntries(t *testing.T) {
	l := New(30*time.Millisecond, 5)
	l.Allow("old") // window not elapsed yet → no sweep, entry persists
	if len(l.byKey) != 1 {
		t.Fatalf("expected 1 entry after first allow, got %d", len(l.byKey))
	}
	time.Sleep(35 * time.Millisecond) // let "old" fully expire
	l.Allow("new")                    // sweep interval elapsed → evicts expired "old"
	if _, ok := l.byKey["old"]; ok {
		t.Fatal("expired entry should have been swept")
	}
	if len(l.byKey) != 1 {
		t.Fatalf("expected only the live entry, got %d", len(l.byKey))
	}
}

func TestClientIPForwardedFor(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet, "/", nil)
	r.Header.Set("X-Forwarded-For", "203.0.113.1, 10.0.0.1")
	if got := ClientIP(r); got != "203.0.113.1" {
		t.Fatalf("ClientIP: %q", got)
	}
}

func TestMiddlewareRetryAfter(t *testing.T) {
	l := New(time.Hour, 1)
	h := Middleware(l, "login", http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	r := httptest.NewRequest(http.MethodPost, "/x", nil)
	r.RemoteAddr = "192.0.2.1:1234"
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("first: %d", w.Code)
	}
	w2 := httptest.NewRecorder()
	h.ServeHTTP(w2, r)
	if w2.Code != http.StatusTooManyRequests {
		t.Fatalf("second: %d", w2.Code)
	}
	if w2.Header().Get("Retry-After") == "" {
		t.Fatal("missing Retry-After")
	}
}

func TestAccountFromLoginBodyTrailingValue(t *testing.T) {
	// A body with a trailing JSON value: login/register decode a single value
	// with json.Decoder, so they act on the FIRST object. The probe must key
	// on that same account — not on the empty-account bucket, which would hand
	// the attacker a second full budget for the same target.
	r := httptest.NewRequest(http.MethodPost, "/v1/auth/login",
		strings.NewReader(`{"email":"victim@example.com","password":"bad"} {}`))
	if got := accountFromLoginBody(r); got != "victim@example.com" {
		t.Fatalf("trailing-value body: account %q, want victim@example.com", got)
	}
	// The handler must still see the first object unchanged.
	var body struct {
		Email string `json:"email"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.Email != "victim@example.com" {
		t.Fatalf("restored body decode: err=%v email=%q", err, body.Email)
	}
}

func TestAccountFromLoginBodyOversizedBody(t *testing.T) {
	// A valid credentials object past the 8192-byte probe window: a 10 KB
	// password is settable (validPassword has no maximum length), so the
	// probe must not truncate what the handler reads.
	pw := strings.Repeat("a1", 5000) // 10 000 chars, letter+digit
	raw, _ := json.Marshal(map[string]string{"email": "big@example.com", "password": pw})
	if len(raw) <= 8192 {
		t.Fatalf("fixture too small: %d bytes", len(raw))
	}
	r := httptest.NewRequest(http.MethodPost, "/v1/auth/login", bytes.NewReader(raw))
	// The object does not close inside the probe window, so the probe cannot
	// extract the email and the request falls back to the IP tier (account
	// ""). That is the documented graceful fallback — the defect was never
	// the bucket, it was the truncated body the handler received.
	if got := accountFromLoginBody(r); got != "" {
		t.Fatalf("oversized body: account %q, want empty (IP-tier fallback)", got)
	}
	var body struct {
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		t.Fatalf("restored body decode: %v", err)
	}
	if len(body.Password) != len(pw) {
		t.Fatalf("restored password: %d chars, want %d", len(body.Password), len(pw))
	}
}

func TestAccountFromLoginBodyEmailPastProbeWindow(t *testing.T) {
	// The email sits past the probe window, so the probe cannot see it and
	// the request falls back to the IP tier (account ""). The handler must
	// still receive the complete body — the probe window must never truncate
	// what the handler reads.
	pw := strings.Repeat("a1", 4500) // 9 000 chars
	raw := `{"password":"` + pw + `","email":"late@example.com"}`
	if len(raw) <= 8192 {
		t.Fatalf("fixture too small: %d bytes", len(raw))
	}
	r := httptest.NewRequest(http.MethodPost, "/v1/auth/login", strings.NewReader(raw))
	if got := accountFromLoginBody(r); got != "" {
		t.Fatalf("email past probe window: account %q, want empty (IP-tier fallback)", got)
	}
	var body struct {
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		t.Fatalf("restored body decode: %v", err)
	}
	if body.Email != "late@example.com" || len(body.Password) != len(pw) {
		t.Fatalf("restored body: email=%q password=%d chars", body.Email, len(body.Password))
	}
}
