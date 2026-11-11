package ratelimit

import (
	"context"
	"errors"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

var ErrGovernorTimeout = errors.New("governor: acquire timeout")

// GovernorConfig controls renewable lease lifetime, crash recovery, and admission wait.
type GovernorConfig struct {
	Lease          time.Duration
	AcquireTimeout time.Duration
	PollInterval   time.Duration
	ReleaseTimeout time.Duration
}

var acquireScript = redis.NewScript(`
local key = KEYS[1]
local maxN = tonumber(ARGV[1])
local token = ARGV[2]
local leaseMs = tonumber(ARGV[3])
local now = redis.call('TIME')
local nowMs = tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000)
redis.call('ZREMRANGEBYSCORE', key, 0, nowMs)
if redis.call('ZCARD', key) >= maxN then return 0 end
redis.call('ZADD', key, nowMs + leaseMs, token)
redis.call('PEXPIRE', key, leaseMs)
return 1
`)

var renewScript = redis.NewScript(`
local key = KEYS[1]
local token = ARGV[1]
local leaseMs = tonumber(ARGV[2])
local now = redis.call('TIME')
local nowMs = tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000)
local expiry = redis.call('ZSCORE', key, token)
if not expiry or tonumber(expiry) <= nowMs then
  redis.call('ZREM', key, token)
  return 0
end
redis.call('ZADD', key, nowMs + leaseMs, token)
redis.call('PEXPIRE', key, leaseMs)
return 1
`)

var releaseScript = redis.NewScript(`return redis.call('ZREM', KEYS[1], ARGV[1])`)

type Governor struct {
	rdb redis.Scripter
	cfg GovernorConfig
}

func NewGovernor(rdb redis.Scripter, cfg GovernorConfig) *Governor {
	if cfg.Lease <= 0 {
		cfg.Lease = 5 * time.Minute
	}
	if cfg.AcquireTimeout <= 0 {
		cfg.AcquireTimeout = 30 * time.Second
	}
	if cfg.PollInterval <= 0 {
		cfg.PollInterval = 50 * time.Millisecond
	}
	if cfg.ReleaseTimeout <= 0 {
		cfg.ReleaseTimeout = 2 * time.Second
	}
	return &Governor{rdb: rdb, cfg: cfg}
}

func concKey(key string) string { return "gov:conc:" + key }

// Acquire takes a renewable distributed permit. Capped calls fail closed when
// Redis cannot confirm admission or a lease renewal.
func (g *Governor) Acquire(waitCtx, callCtx context.Context, class string, limit int) (ProviderPermit, error) {
	return g.acquireWithScripts(waitCtx, callCtx, class, limit)
}

func (g *Governor) acquireWithScripts(waitCtx, callCtx context.Context, class string, limit int) (ProviderPermit, error) {
	if g == nil || g.rdb == nil {
		return nil, ErrGovernorUnavailable
	}
	runner := g.rdb
	if callCtx == nil {
		callCtx = waitCtx
	}
	if limit <= 0 {
		return newNoopPermit(callCtx), nil
	}
	key, token := concKey(class), uuid.NewString()
	leaseMs := g.cfg.Lease.Milliseconds()
	if leaseMs <= 0 {
		return nil, ErrGovernorUnavailable
	}
	acquireCtx, cancelAcquire := context.WithTimeout(waitCtx, g.cfg.AcquireTimeout)
	defer cancelAcquire()
	deadline, _ := acquireCtx.Deadline()
	for {
		if err := acquireCtx.Err(); err != nil {
			if waitCtx.Err() != nil {
				return nil, waitCtx.Err()
			}
			return nil, ErrGovernorTimeout
		}
		got, err := acquireScript.Run(acquireCtx, runner, []string{key}, limit, token, leaseMs).Int()
		if err != nil {
			if waitCtx.Err() != nil {
				return nil, waitCtx.Err()
			}
			if !time.Now().Before(deadline) {
				return nil, ErrGovernorTimeout
			}
			return nil, errors.Join(ErrGovernorUnavailable, err)
		}
		if got == 1 {
			if !time.Now().Before(deadline) || waitCtx.Err() != nil {
				rctx, rcancel := context.WithTimeout(context.Background(), g.cfg.ReleaseTimeout)
				_ = releaseScript.Run(rctx, runner, []string{key}, token).Err()
				rcancel()
				if waitCtx.Err() != nil {
					return nil, waitCtx.Err()
				}
				return nil, ErrGovernorTimeout
			}
			return g.renewablePermit(callCtx, key, token, leaseMs), nil
		}
		select {
		case <-acquireCtx.Done():
			if waitCtx.Err() != nil {
				return nil, waitCtx.Err()
			}
			return nil, ErrGovernorTimeout
		case <-time.After(g.cfg.PollInterval):
		}
	}
}

func (g *Governor) renewablePermit(callCtx context.Context, key, token string, leaseMs int64) ProviderPermit {
	return g.renewablePermitWithRunner(callCtx, key, token, leaseMs, g.rdb)
}

func (g *Governor) renewablePermitWithRunner(callCtx context.Context, key, token string, leaseMs int64, runner redis.Scripter) ProviderPermit {
	permitCtx, cancel := context.WithCancelCause(callCtx)
	stop, stopped := make(chan struct{}), make(chan struct{})
	interval := g.cfg.Lease / 3
	if interval <= 0 {
		interval = time.Millisecond
	}
	go func() {
		defer close(stopped)
		ticker := time.NewTicker(interval)
		defer ticker.Stop()
		for {
			select {
			case <-stop:
				return
			case <-permitCtx.Done():
				return
			case <-ticker.C:
				rctx, rcancel := context.WithTimeout(permitCtx, g.cfg.ReleaseTimeout)
				renewed, err := renewScript.Run(rctx, runner, []string{key}, token, leaseMs).Int()
				rcancel()
				if err != nil || renewed != 1 {
					cancel(ErrLeaseLost)
					return
				}
			}
		}
	}()
	var once sync.Once
	return newPermit(permitCtx, cancel, func() {
		once.Do(func() {
			close(stop)
			<-stopped
			rctx, rcancel := context.WithTimeout(context.Background(), g.cfg.ReleaseTimeout)
			defer rcancel()
			_ = releaseScript.Run(rctx, runner, []string{key}, token).Err()
		})
	})
}
