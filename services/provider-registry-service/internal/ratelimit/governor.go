package ratelimit

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// ErrGovernorTimeout — couldn't acquire a concurrency slot within the wait
// budget. The jobs worker treats this like a transient error (retryable).
var ErrGovernorTimeout = errors.New("governor: acquire timeout")

// GovernorConfig — tunables (from service config).
//
// D-PROVIDER-CONCURRENCY-CONFIG: the concurrency cap is no longer a per-KIND
// constant (the old local→1 / cloud→cloudMax split was an anti-pattern — capacity
// is a property of a credential's backend, not its kind). The cap now travels
// with each Acquire call as the credential's max_concurrency; this struct only
// carries the lease/timeout tunables shared by every key.
type GovernorConfig struct {
	Lease          time.Duration // per-acquisition lease TTL (> max call duration)
	AcquireTimeout time.Duration // max wait for a slot before ErrGovernorTimeout
	PollInterval   time.Duration // re-check cadence while waiting
}

// acquireScript — atomic prune-stale + count + add. A sorted set per kind holds
// live acquisition tokens scored by lease-expiry (epoch-ms); stale leases
// (crashed workers) are pruned by score before counting, so a slot can never be
// permanently wedged. Returns 1 if a slot was taken, 0 if at capacity.
var acquireScript = redis.NewScript(`
local key = KEYS[1]
local now = tonumber(ARGV[1])
local leaseExpiry = tonumber(ARGV[2])
local maxN = tonumber(ARGV[3])
local token = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now)
local n = redis.call('ZCARD', key)
if n < maxN then
  redis.call('ZADD', key, leaseExpiry, token)
  return 1
end
return 0
`)

// Governor is the Redis-backed per-credential concurrency limiter.
type Governor struct {
	rdb *redis.Client
	cfg GovernorConfig
}

func NewGovernor(rdb *redis.Client, cfg GovernorConfig) *Governor {
	if cfg.PollInterval <= 0 {
		cfg.PollInterval = 50 * time.Millisecond
	}
	return &Governor{rdb: rdb, cfg: cfg}
}

func concKey(key string) string { return "gov:conc:" + key }

// Acquire takes a concurrency slot for credential-class `concClass`, capped at
// `limit`, waiting up to AcquireTimeout. limit ≤ 0 means UNLIMITED — the call
// passes through immediately without touching Redis (request-as-demand: the
// backend infra is the only limiter). Returns a release func (always non-nil;
// safe to call once) or ErrGovernorTimeout.
func (g *Governor) Acquire(ctx context.Context, concClass string, limit int) (func(), error) {
	if limit <= 0 {
		return func() {}, nil // unlimited — no gate
	}
	maxN := limit
	token := uuid.NewString()
	key := concKey(concClass)
	deadline := time.Now().Add(g.cfg.AcquireTimeout)

	for {
		now := time.Now()
		leaseExpiry := now.Add(g.cfg.Lease).UnixMilli()
		got, err := acquireScript.Run(
			ctx, g.rdb, []string{key},
			now.UnixMilli(), leaseExpiry, maxN, token,
		).Int()
		if err != nil {
			// FAIL-OPEN: a governor must never be a single point of failure. If
			// Redis is unreachable, allow the call ungoverned (degraded) rather
			// than fail every provider call. (The breaker likewise fails-open.)
			return func() {}, nil
		}
		if got == 1 {
			released := false
			return func() {
				if released {
					return
				}
				released = true
				_ = g.rdb.ZRem(context.Background(), key, token).Err()
			}, nil
		}
		if time.Now().After(deadline) {
			return func() {}, ErrGovernorTimeout
		}
		select {
		case <-ctx.Done():
			return func() {}, ctx.Err()
		case <-time.After(g.cfg.PollInterval):
		}
	}
}
