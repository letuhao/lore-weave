package ratelimit

import (
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
			w.Header().Set("Retry-After", strconv.Itoa(int(l.window.Seconds())))
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusTooManyRequests)
			_, _ = w.Write([]byte(`{"code":"AUTH_RATE_LIMITED","message":"Too many requests"}`))
			return
		}
		next.ServeHTTP(w, r)
	})
}
