package ratelimit

import (
	"net/http"
	"net/http/httptest"
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
