// Package ratelimit — Auto-Draft Factory S3a (G5). Per-provider-kind
// concurrency governor + circuit-breaker for the jobs-worker provider-call
// path. Protects against the "#1 overnight risk": a provider outage at 2 a.m.
// failing thousands of chapters with no auto-pause, and an unbounded fan-out
// hammering a single local GPU.
//
// The breaker DECISION logic (`decideAllow` / `decideRecord`) is pure and
// exhaustively unit-tested; the Redis I/O is a thin wrapper. A circuit-breaker
// is a heuristic safety mechanism, not a correctness gate, so the small races
// in the (non-Lua) Redis path are acceptable — a slightly-late open or an extra
// half-open probe never corrupts state.
package ratelimit

import (
	"context"
	"strconv"
	"time"

	"github.com/redis/go-redis/v9"
)

// Breaker states.
const (
	StateClosed   = "closed"
	StateOpen     = "open"
	StateHalfOpen = "half_open"
)

// BreakerConfig — tunables (from service config).
type BreakerConfig struct {
	Threshold  int           // consecutive/windowed failures that trip the breaker
	Window     time.Duration // failure-count decay window
	Cooldown   time.Duration // open → half-open wait
}

// decideAllow — pure: given the current state and when it opened, decide whether
// a call is allowed NOW and the effective state to persist. open → half_open
// once the cooldown elapses (a probe is then allowed).
func decideAllow(state string, openedAtMs, nowMs int64, cooldown time.Duration) (effState string, allow bool) {
	switch state {
	case StateOpen:
		if nowMs-openedAtMs >= cooldown.Milliseconds() {
			return StateHalfOpen, true // cooldown elapsed → allow one probe
		}
		return StateOpen, false
	case StateHalfOpen:
		return StateHalfOpen, true
	default: // closed / unknown
		return StateClosed, true
	}
}

// decideRecord — pure: given the state + windowed failure count, fold in a call
// outcome. Success closes (resets). Failure increments; a half-open probe
// failure re-opens immediately, otherwise the breaker opens once the threshold
// is reached. `nowMs` stamps the open time.
func decideRecord(state string, failures, threshold int, success bool, nowMs int64) (newState string, newFailures int, openedAtMs int64) {
	if success {
		return StateClosed, 0, 0
	}
	nf := failures + 1
	if state == StateHalfOpen {
		return StateOpen, nf, nowMs // probe failed → straight back to open
	}
	if nf >= threshold {
		return StateOpen, nf, nowMs
	}
	return StateClosed, nf, 0
}

// Breaker is the Redis-backed per-provider-kind circuit-breaker.
type Breaker struct {
	rdb *redis.Client
	cfg BreakerConfig
}

func NewBreaker(rdb *redis.Client, cfg BreakerConfig) *Breaker {
	return &Breaker{rdb: rdb, cfg: cfg}
}

func stateKey(kind string) string     { return "breaker:" + kind + ":state" }
func openedAtKey(kind string) string  { return "breaker:" + kind + ":opened_at" }
func failuresKey(kind string) string  { return "breaker:" + kind + ":failures" }

// Allow reports whether a call to `kind` may proceed. Persists an open→half_open
// transition when the cooldown elapses so exactly the probe semantics hold.
func (b *Breaker) Allow(ctx context.Context, kind string) (bool, error) {
	state, openedAt := b.read(ctx, kind)
	now := time.Now().UnixMilli()
	effState, allow := decideAllow(state, openedAt, now, b.cfg.Cooldown)
	if effState != state {
		_ = b.rdb.Set(ctx, stateKey(kind), effState, 0).Err()
	}
	return allow, nil
}

// Record folds a call outcome into the breaker. `success` should be false ONLY
// for transient/upstream failures the caller wants to count (a 400 must pass
// success=true so a user's bad request never trips the breaker).
func (b *Breaker) Record(ctx context.Context, kind string, success bool) {
	state, _ := b.read(ctx, kind)
	failures := 0
	if v, err := b.rdb.Get(ctx, failuresKey(kind)).Int(); err == nil {
		failures = v
	}
	now := time.Now().UnixMilli()
	newState, newFailures, openedAt := decideRecord(state, failures, b.cfg.Threshold, success, now)

	_ = b.rdb.Set(ctx, stateKey(kind), newState, 0).Err()
	if newFailures == 0 {
		_ = b.rdb.Del(ctx, failuresKey(kind)).Err()
	} else {
		// Windowed: the failure count decays if no new failures arrive.
		_ = b.rdb.Set(ctx, failuresKey(kind), newFailures, b.cfg.Window).Err()
	}
	if newState == StateOpen {
		_ = b.rdb.Set(ctx, openedAtKey(kind), strconv.FormatInt(openedAt, 10), 0).Err()
	} else if newState == StateClosed {
		_ = b.rdb.Del(ctx, openedAtKey(kind)).Err()
	}
}

func (b *Breaker) read(ctx context.Context, kind string) (state string, openedAtMs int64) {
	state, err := b.rdb.Get(ctx, stateKey(kind)).Result()
	if err != nil || state == "" {
		state = StateClosed
	}
	if v, err := b.rdb.Get(ctx, openedAtKey(kind)).Int64(); err == nil {
		openedAtMs = v
	}
	return state, openedAtMs
}
