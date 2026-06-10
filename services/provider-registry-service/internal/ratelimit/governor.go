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

// localKinds run on a single local GPU and MUST be serialized (max 1). Cloud
// kinds share a per-kind concurrency cap. Keeping this a small set (vs a config
// list) is deliberate — adding a provider kind is a code change anyway.
var localKinds = map[string]bool{"ollama": true, "lm_studio": true}

// maxFor — pure: the concurrency cap for a provider kind. Local kinds are
// serialized to 1 (the single GPU); everything else gets cloudMax.
func maxFor(kind string, cloudMax int) int {
	if localKinds[kind] {
		return 1
	}
	return cloudMax
}

// GovernorConfig — tunables (from service config).
type GovernorConfig struct {
	CloudMax       int           // concurrency cap for cloud provider kinds
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

// Governor is the Redis-backed per-provider-kind concurrency limiter.
type Governor struct {
	rdb *redis.Client
	cfg GovernorConfig
}

func NewGovernor(rdb *redis.Client, cfg GovernorConfig) *Governor {
	if cfg.PollInterval <= 0 {
		cfg.PollInterval = 50 * time.Millisecond
	}
	// Clamp: a misconfigured CloudMax<1 would make every cloud call un-acquirable
	// (ZCARD < 0 is never true) → all cloud jobs time out. Floor at 1.
	if cfg.CloudMax < 1 {
		cfg.CloudMax = 1
	}
	return &Governor{rdb: rdb, cfg: cfg}
}

func concKey(kind string) string { return "gov:conc:" + kind }

// Acquire takes a concurrency slot for `kind`, waiting up to AcquireTimeout.
// Returns a release func (always non-nil; safe to call once) or ErrGovernorTimeout.
func (g *Governor) Acquire(ctx context.Context, kind string) (func(), error) {
	maxN := maxFor(kind, g.cfg.CloudMax)
	token := uuid.NewString()
	key := concKey(kind)
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
