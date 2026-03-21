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
	mu       sync.Mutex
	byKey    map[string]*entry
	window   time.Duration
	max      int
}

func New(window time.Duration, max int) *Limiter {
	return &Limiter{
		byKey:  make(map[string]*entry),
		window: window,
		max:    max,
	}
}

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
