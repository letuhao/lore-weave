package api

// #261 — the login throttle was keyed per IP alone (routeKey + ClientIP), so everyone
// behind one NAT shared ONE budget: the 61st person to open the app in a minute got a
// 429 without doing anything wrong. The credentials routes are now keyed in TWO tiers
// — per (route, IP, account) at RATE_LIMIT_MAX_REQUESTS plus a per-IP floor at
// RATE_LIMIT_IP_MAX_REQUESTS — and this file pins both halves. The RED run of
// TestLoginThrottleNATDistinctAccounts against the unfixed per-IP-only middleware
// (6th distinct-account login → 429) is pasted in the PR description.

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/loreweave/auth-service/internal/ratelimit"
)

// stubLogin stands in for the real login handler: the limiter is the subject, and the
// real handler needs a DB pool this unit test does not have.
func stubLogin(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
}

// newLoginThrottle composes the two tiers EXACTLY as server.go wires /v1/auth/login.
func newLoginThrottle(accountMax, ipMax int) http.Handler {
	accountL := ratelimit.New(time.Minute, accountMax)
	ipL := ratelimit.New(time.Minute, ipMax)
	return ratelimit.AuthRateLimitMiddleware(accountL, ipL, "login", http.HandlerFunc(stubLogin))
}

func postLogin(t *testing.T, h http.Handler, email string) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]string{"email": email, "password": "pw"})
	r := httptest.NewRequest(http.MethodPost, "/v1/auth/login", bytes.NewReader(body))
	r.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, r)
	return rec
}

// TestLoginThrottleNATDistinctAccounts — six different people behind one IP must all
// be able to sign in within the window. Against the pre-fix per-IP-only middleware
// (max=5), the 6th distinct-account login came back 429 — the false outage #261
// reports. The per-account tier gives every account its own full budget.
func TestLoginThrottleNATDistinctAccounts(t *testing.T) {
	h := newLoginThrottle(5, 15) // account cap 5, IP floor 15
	for i := 1; i <= 5; i++ {
		rec := postLogin(t, h, fmt.Sprintf("user%d@example.com", i))
		if rec.Code != http.StatusOK {
			t.Fatalf("login %d/5 (distinct accounts, one IP): expected 200, got %d", i, rec.Code)
		}
	}
	rec := postLogin(t, h, "user6@example.com")
	if rec.Code != http.StatusOK {
		t.Fatalf("6th DISTINCT-account login from one IP got %d — the per-IP-only key treated other people's logins as an attack (#261)", rec.Code)
	}
}

// The stuffing guard did not go away: ONE account hammering from one IP still hits
// its own (smaller) budget, and Retry-After survives byte-identical.
func TestLoginThrottleSameAccountStillCapped(t *testing.T) {
	h := newLoginThrottle(3, 15)
	for i := 1; i <= 3; i++ {
		if rec := postLogin(t, h, "attacker@example.com"); rec.Code != http.StatusOK {
			t.Fatalf("attempt %d: expected 200, got %d", i, rec.Code)
		}
	}
	rec := postLogin(t, h, "attacker@example.com")
	if rec.Code != http.StatusTooManyRequests {
		t.Fatalf("4th same-account login: expected 429, got %d", rec.Code)
	}
	if rec.Header().Get("Retry-After") == "" {
		t.Fatal("429 must keep the Retry-After header")
	}
}

// One IP spraying MANY accounts trips the IP floor before any single account budget
// matters — the credential-stuffing guard keeps doing its job.
func TestLoginThrottleIPFloorStillCapsSpray(t *testing.T) {
	h := newLoginThrottle(100, 10) // per-account cap deliberately generous; the floor binds
	for i := 1; i <= 10; i++ {
		rec := postLogin(t, h, fmt.Sprintf("spray%d@example.com", i))
		if rec.Code != http.StatusOK {
			t.Fatalf("spray login %d/10: expected 200 under the floor, got %d", i, rec.Code)
		}
	}
	if rec := postLogin(t, h, "spray11@example.com"); rec.Code != http.StatusTooManyRequests {
		t.Fatalf("11th distinct account past the IP floor: expected 429, got %d", rec.Code)
	}
}
