package ratelimit

import (
	"bytes"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"
)

type entry struct {
	count  int
	window time.Time
}

type Limiter struct {
	mu        sync.Mutex
	byKey     map[string]*entry
	window    time.Duration
	max       int
	lastSweep time.Time
}

func New(window time.Duration, max int) *Limiter {
	return &Limiter{
		byKey:     make(map[string]*entry),
		window:    window,
		max:       max,
		lastSweep: time.Now(),
	}
}

// sweep evicts entries whose window has fully expired (the next Allow would
// reset them anyway). Without this, every distinct key — including spoofed
// per-IP keys — leaves a permanent map entry, so the map grows unbounded.
// Caller MUST hold l.mu.
func (l *Limiter) sweep(now time.Time) {
	if now.Sub(l.lastSweep) < l.window {
		return
	}
	for k, e := range l.byKey {
		if now.Sub(e.window) >= l.window {
			delete(l.byKey, k)
		}
	}
	l.lastSweep = now
}

// ClientIP resolves the rate-limit key's IP. NOTE: this trusts the first
// X-Forwarded-For hop, which a client can spoof to evade the per-IP cap. The
// platform fix (overwrite XFF to the true peer at the gateway edge) is tracked
// in D-AUTH-RATELIMIT-XFF-AND-UNBOUNDED-MAP — only the unbounded-map half is
// fixed here (see sweep above).
func ClientIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		parts := strings.Split(xff, ",")
		return strings.TrimSpace(parts[0])
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

func (l *Limiter) Allow(key string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	now := time.Now()
	l.sweep(now)
	e, ok := l.byKey[key]
	if !ok || now.Sub(e.window) >= l.window {
		l.byKey[key] = &entry{count: 1, window: now}
		return true
	}
	if e.count >= l.max {
		return false
	}
	e.count++
	return true
}

func Middleware(l *Limiter, routeKey string, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key := routeKey + ":" + ClientIP(r)
		if !l.Allow(key) {
			writeLimited(w, l)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// AuthRateLimitMiddleware is the credential-route limiter (#261). A bare per-IP key
// made everyone behind one NAT share a single budget: the 61st person to open the app
// in a minute got a 429 without doing anything wrong — indistinguishable, from their
// side, from an outage. The credentials routes are keyed in TWO tiers:
//
//   - per (route, IP, account): the budget a human consumes. `accountL` runs at
//     RATE_LIMIT_MAX_REQUESTS per account, so 60 different people are not an attack.
//   - per (route, IP): `ipL` runs at RATE_LIMIT_IP_MAX_REQUESTS (default 3× the
//     account cap) and stays the credential-stuffing guard — one IP spraying many
//     accounts trips the floor long before any single account budget matters.
//
// The account identifier is read from the JSON body (email on these routes) and the
// body is restored for the handler. An unparseable body keys on the IP tier only.
// The 429 response shape and Retry-After are byte-identical to Middleware.
func AuthRateLimitMiddleware(accountL, ipL *Limiter, routeKey string, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ip := ClientIP(r)
		account := accountFromLoginBody(r)
		if !ipL.Allow(routeKey + ":ip:" + ip) {
			writeLimited(w, ipL)
			return
		}
		if !accountL.Allow(routeKey + ":acct:" + ip + ":" + account) {
			writeLimited(w, accountL)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// maxProbeBytes bounds how much of the body the account probe buffers. The
// probe only needs the (early) email field; the handler must still see the
// complete body, so anything past the window stays on the original stream and
// is replayed after the buffered prefix (see accountFromLoginBody).
const maxProbeBytes = 8192

// accountFromLoginBody extracts a stable account identifier from a credentials-route
// JSON body, consuming and restoring the body so the handler reads it unchanged.
func accountFromLoginBody(r *http.Request) string {
	var account string
	if r.Body != nil {
		// Read at most maxProbeBytes+1: the extra byte tells the probe the
		// body continues, while the unread tail stays on r.Body and is
		// replayed verbatim through the MultiReader below — a credentials
		// object longer than the probe window still reaches the handler
		// intact instead of failing with unexpected EOF.
		raw, err := io.ReadAll(io.LimitReader(r.Body, maxProbeBytes+1))
		if err == nil {
			var probe struct {
				Email string `json:"email"`
			}
			// Decode exactly like the handlers: login/register read a single
			// value with json.Decoder, which accepts the first JSON object
			// and ignores trailing data. Probing with Unmarshal instead
			// rejected trailing data, so `{"email":"victim@…"} {}` keyed on
			// the empty-account bucket while the handler acted on the
			// victim's account — a second full budget per target. Decoding
			// the same way keeps the limiter bucket and the handler's
			// account identical.
			if json.NewDecoder(bytes.NewReader(raw)).Decode(&probe) == nil {
				account = strings.ToLower(strings.TrimSpace(probe.Email))
			}
		}
		// Do NOT close the original body: its unread tail is still needed
		// below. The server closes it after the handler returns.
		r.Body = io.NopCloser(io.MultiReader(bytes.NewReader(raw), r.Body))
	}
	return account
}

func writeLimited(w http.ResponseWriter, l *Limiter) {
	w.Header().Set("Retry-After", strconv.Itoa(int(l.window.Seconds())))
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusTooManyRequests)
	_, _ = w.Write([]byte(`{"code":"AUTH_RATE_LIMITED","message":"Too many requests"}`))
}
