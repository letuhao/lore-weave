package ratelimit

import (
	"context"
	"errors"
	"log/slog"
	"net/url"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

// ErrModelLeaseTimeout — waited the whole budget for another model to finish on this endpoint.
// The caller treats it like a governor timeout: retryable, never a provider-health failure.
var ErrModelLeaseTimeout = errors.New("model lease: timed out waiting for another model to finish on this endpoint")

// ModelLeaseConfig — tunables (from service config).
type ModelLeaseConfig struct {
	Lease        time.Duration // holder lease TTL (> the longest single call); a crashed holder frees itself
	WaitTimeout  time.Duration // max wait for another model to finish before ErrModelLeaseTimeout
	AgingBound   time.Duration // once another model's oldest waiter has waited this long, new same-model calls queue too
	PollInterval time.Duration // re-check cadence while waiting (also the waiter heartbeat)
}

// ModelLease sequences requests for DIFFERENT models on ONE endpoint (#286).
//
// A local server that holds one model at a time (LM Studio on one GPU) aborts both loads when two
// callers ask it for different models at the same moment ("Engine protocol startup was
// aborted"). This lease lets any number of calls for the model currently held run together, and
// makes a call for another model WAIT until they finish. It never loads or unloads a model: it
// only orders requests, which is where upstream reports say the fix belongs.
//
// It is used only for a credential whose owner opted in (serve_one_model_at_a_time). The key is
// the normalised endpoint, not the credential: two accounts with separate credentials pointing at
// the same box collide on the same GPU, which is exactly what run 4 of the v0.1.0 plan showed.
type ModelLease struct {
	rdb *redis.Client
	cfg ModelLeaseConfig
}

func NewModelLease(rdb *redis.Client, cfg ModelLeaseConfig) *ModelLease {
	if cfg.PollInterval <= 0 {
		cfg.PollInterval = 100 * time.Millisecond
	}
	if cfg.Lease <= 0 {
		cfg.Lease = 15 * time.Minute
	}
	if cfg.WaitTimeout <= 0 {
		cfg.WaitTimeout = 10 * time.Minute
	}
	if cfg.AgingBound <= 0 {
		cfg.AgingBound = 2 * time.Minute
	}
	return &ModelLease{rdb: rdb, cfg: cfg}
}

// NormalizeEndpoint returns the lease key for an endpoint: scheme + lowercased host + port, with
// the default port made explicit and any path dropped. Conservative on purpose — two spellings are
// merged only when they are the same URL; `host.docker.internal` and `127.0.0.1` stay distinct.
func NormalizeEndpoint(raw string) string {
	u, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || u.Host == "" {
		return strings.ToLower(strings.TrimRight(strings.TrimSpace(raw), "/"))
	}
	scheme := strings.ToLower(u.Scheme)
	host := strings.ToLower(u.Hostname())
	port := u.Port()
	if port == "" {
		if scheme == "https" {
			port = "443"
		} else {
			port = "80"
		}
	}
	return scheme + "://" + host + ":" + port
}

func leaseKeys(endpoint string) []string {
	base := "lease:model:" + NormalizeEndpoint(endpoint)
	return []string{base + ":holder", base + ":tok", base + ":wait", base + ":waitmodel", base + ":seen"}
}

// leaseScript — one atomic decision. KEYS: holder (string: model held), tok (zset token→lease
// expiry), wait (zset token→enqueue ms), waitmodel (hash token→model), seen (hash token→last poll
// ms). ARGV: now, leaseExpiry, model, token, agingMs, staleWaiterMs.
// Returns 1 = granted, 0 = wait.
var leaseScript = redis.NewScript(`
local holderK, tokK, waitK, wmK, seenK = KEYS[1], KEYS[2], KEYS[3], KEYS[4], KEYS[5]
local now = tonumber(ARGV[1])
local leaseExpiry = tonumber(ARGV[2])
local model = ARGV[3]
local token = ARGV[4]
local agingMs = tonumber(ARGV[5])
local staleMs = tonumber(ARGV[6])

-- crashed holders free themselves
redis.call('ZREMRANGEBYSCORE', tokK, 0, now)
if redis.call('ZCARD', tokK) == 0 then redis.call('DEL', holderK) end
-- waiters that stopped polling (a cancelled request) leave the queue
local seen = redis.call('HGETALL', seenK)
for i = 1, #seen, 2 do
  if tonumber(seen[i+1]) < now - staleMs then
    redis.call('ZREM', waitK, seen[i]); redis.call('HDEL', wmK, seen[i]); redis.call('HDEL', seenK, seen[i])
  end
end

local function grant()
  redis.call('SET', holderK, model)
  redis.call('ZADD', tokK, leaseExpiry, token)
  redis.call('ZREM', waitK, token); redis.call('HDEL', wmK, token); redis.call('HDEL', seenK, token)
  return 1
end
local function wait()
  redis.call('ZADD', waitK, 'NX', now, token)
  redis.call('HSET', wmK, token, model)
  redis.call('HSET', seenK, token, now)
  return 0
end

-- the oldest waiter asking for a model OTHER than the held one (it is what aging protects)
local holder = redis.call('GET', holderK)
local oldestOther, oldestOtherAt = nil, nil
local waiters = redis.call('ZRANGE', waitK, 0, -1, 'WITHSCORES')
for i = 1, #waiters, 2 do
  local m = redis.call('HGET', wmK, waiters[i])
  if m and m ~= holder then oldestOther = m; oldestOtherAt = tonumber(waiters[i+1]); break end
end

if not holder then
  -- free: the oldest waiter's model goes next (FIFO); anyone asking for that model may enter
  if #waiters == 0 then return grant() end
  local firstModel = redis.call('HGET', wmK, waiters[1])
  if firstModel == false or firstModel == model then return grant() end
  return wait()
end

if holder == model then
  -- same model: share the lease, unless another model has waited past the aging bound
  if oldestOtherAt and (now - oldestOtherAt) >= agingMs then return wait() end
  return grant()
end

return wait()
`)

// Acquire takes the endpoint's model lease for `model`, waiting while another model holds it.
// Returns a release func (always non-nil; safe to call once), ErrModelLeaseTimeout, or ctx.Err().
// Fails OPEN on a Redis error, like the governor: the lease must never become the outage.
func (l *ModelLease) Acquire(ctx context.Context, endpoint, model string) (func(), error) {
	keys := leaseKeys(endpoint)
	token := uuid.NewString()
	start := time.Now()
	deadline := start.Add(l.cfg.WaitTimeout)
	staleMs := (3 * l.cfg.PollInterval).Milliseconds() + 1000
	waited := false
	for {
		now := time.Now()
		got, err := leaseScript.Run(ctx, l.rdb, keys,
			now.UnixMilli(), now.Add(l.cfg.Lease).UnixMilli(), model, token,
			l.cfg.AgingBound.Milliseconds(), staleMs).Int()
		if err != nil {
			if ctx.Err() != nil {
				return func() {}, ctx.Err()
			}
			slog.Warn("model lease: redis unavailable — calling ungoverned", "endpoint", NormalizeEndpoint(endpoint), "err", err)
			return func() {}, nil
		}
		if got == 1 {
			slog.Info("model lease: granted", "endpoint", NormalizeEndpoint(endpoint), "model", model,
				"waited_ms", time.Since(start).Milliseconds())
			released := false
			return func() {
				if released {
					return
				}
				released = true
				bg := context.Background()
				_ = l.rdb.ZRem(bg, keys[1], token).Err()
				if n, err := l.rdb.ZCard(bg, keys[1]).Result(); err == nil && n == 0 {
					_ = l.rdb.Del(bg, keys[0]).Err()
				}
				slog.Debug("model lease: released", "endpoint", NormalizeEndpoint(endpoint), "model", model)
			}, nil
		}
		if !waited {
			waited = true
			slog.Info("model lease: waiting for another model to finish", "endpoint", NormalizeEndpoint(endpoint), "model", model)
		}
		if time.Now().After(deadline) {
			l.leave(keys, token)
			return func() {}, ErrModelLeaseTimeout
		}
		select {
		case <-ctx.Done():
			l.leave(keys, token)
			return func() {}, ctx.Err()
		case <-time.After(l.cfg.PollInterval):
		}
	}
}

func (l *ModelLease) leave(keys []string, token string) {
	bg := context.Background()
	_ = l.rdb.ZRem(bg, keys[2], token).Err()
	_ = l.rdb.HDel(bg, keys[3], token).Err()
	_ = l.rdb.HDel(bg, keys[4], token).Err()
}
