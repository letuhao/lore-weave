package ratelimit

import (
	"bytes"
	"encoding/json"
	"io"
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
	// The object does not close inside the old 8192-byte probe window, but
	// the probe now decodes the whole first JSON value, so the email must
	// still be extracted — falling back to the empty-account bucket would
	// hand the attacker a second full budget for this account.
	if got := accountFromLoginBody(r); got != "big@example.com" {
		t.Fatalf("oversized body: account %q, want big@example.com", got)
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
	// The email sits past the old 8192-byte probe window, but the probe now
	// decodes the whole first JSON value, so it must still be extracted.
	// The handler must still receive the complete body either way.
	pw := strings.Repeat("a1", 4500) // 9 000 chars
	raw := `{"password":"` + pw + `","email":"late@example.com"}`
	if len(raw) <= 8192 {
		t.Fatalf("fixture too small: %d bytes", len(raw))
	}
	r := httptest.NewRequest(http.MethodPost, "/v1/auth/login", strings.NewReader(raw))
	if got := accountFromLoginBody(r); got != "late@example.com" {
		t.Fatalf("email past probe window: account %q, want late@example.com", got)
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

func TestAccountFromLoginBodyOversizedPaddingKeepsAccount(t *testing.T) {
	// F3: the email appears FIRST but an ignored padding field extends the
	// credentials object past the old 8193-byte probe window. The probe used
	// to fail decoding the truncated prefix and fall back to the
	// empty-account bucket, while the handler decoded the same object fine
	// and acted on the named account — a second full budget per target.
	pad := strings.Repeat("x", 9000)
	raw := `{"email":"victim@example.com","password":"bad","padding":"` + pad + `"}`
	if len(raw) <= 8193 {
		t.Fatalf("fixture too small: %d bytes", len(raw))
	}
	r := httptest.NewRequest(http.MethodPost, "/v1/auth/login", strings.NewReader(raw))
	if got := accountFromLoginBody(r); got != "victim@example.com" {
		t.Fatalf("oversized padded body: account %q, want victim@example.com", got)
	}
	var body struct {
		Email   string `json:"email"`
		Padding string `json:"padding"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		t.Fatalf("restored body decode: %v", err)
	}
	if body.Email != "victim@example.com" || len(body.Padding) != len(pad) {
		t.Fatalf("restored body: email=%q padding=%d chars", body.Email, len(body.Padding))
	}
}

func TestAuthRateLimitCappedIPRejectedWithoutReadingBody(t *testing.T) {
	// F4: an IP that already exhausted its budget must get its 429 without
	// the middleware touching the request body. Before the fix the account
	// probe ran first, so a POST with Expect: 100-continue that withholds
	// its body received 100 Continue and blocked in the probe instead of
	// the immediate 429 — against a real Go HTTP server.
	accountL := New(time.Minute, 100)
	ipL := New(time.Minute, 1)
	h := AuthRateLimitMiddleware(accountL, ipL, "login", http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	srv := httptest.NewServer(h)
	defer srv.Close()
	// Generous client timeout: the test's own verdict comes from the
	// elapsed-time assertion below, not from this timeout.
	client := &http.Client{Timeout: 10 * time.Second}
	// Exhaust the single IP allowance with a normal request.
	resp, err := client.Post(srv.URL, "application/json", strings.NewReader(`{"email":"a@example.com","password":"pw"}`))
	if err != nil {
		t.Fatalf("exhausting request: %v", err)
	}
	_ = resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("exhausting request: status %d, want 200", resp.StatusCode)
	}
	// Now the IP is capped. Send a POST with Expect: 100-continue whose
	// body never yields a byte: the middleware must answer 429 at once,
	// without touching the body. The pipe's safety valve closes it after
	// 3s so a body-blocking middleware cannot hang the test — the
	// elapsed-time assertion below is the verdict: a prompt 429 arrives in
	// milliseconds, while a body-blocked 429 only arrives once the valve
	// fires (a bare client timeout cannot unblock it: the transport's body
	// writer stays stuck on the unread pipe).
	pr, pw := io.Pipe()
	defer pw.Close()
	time.AfterFunc(3*time.Second, func() { _ = pw.Close() })
	req, err := http.NewRequest(http.MethodPost, srv.URL, pr)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Expect", "100-continue")
	req.ContentLength = -1
	start := time.Now()
	resp, err = client.Do(req)
	elapsed := time.Since(start)
	if err != nil {
		t.Fatalf("capped-IP request with withheld body: %v (no prompt 429 — the middleware blocked reading the body)", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusTooManyRequests {
		t.Fatalf("capped-IP request: status %d, want 429", resp.StatusCode)
	}
	if elapsed > 2*time.Second {
		t.Fatalf("capped-IP 429 took %v, want a prompt rejection without waiting on the body", elapsed)
	}
}
