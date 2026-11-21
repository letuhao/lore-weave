package ratelimit

import (
	"context"
	"errors"
	"fmt"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

type scriptedRedis struct {
	mu         sync.Mutex
	runAcquire func(context.Context) (int64, error)
	runRenew   func(context.Context) (int64, error)
	releases   int
}

var _ redis.Scripter = (*scriptedRedis)(nil)

func (r *scriptedRedis) EvalSha(ctx context.Context, hash string, keys []string, args ...interface{}) *redis.Cmd {
	var result int64
	var err error
	switch hash {
	case acquireScript.Hash():
		result, err = r.runAcquire(ctx)
	case renewScript.Hash():
		result, err = r.runRenew(ctx)
	case releaseScript.Hash():
		r.mu.Lock()
		r.releases++
		r.mu.Unlock()
		result = 1
	default:
		err = fmt.Errorf("unexpected script hash %q", hash)
	}
	cmd := redis.NewCmdResult(result, err)
	return cmd
}

func (r *scriptedRedis) Eval(context.Context, string, []string, ...interface{}) *redis.Cmd {
	return redis.NewCmdResult(int64(0), errors.New("unexpected EVAL"))
}
func (r *scriptedRedis) EvalRO(context.Context, string, []string, ...interface{}) *redis.Cmd {
	return redis.NewCmdResult(int64(0), errors.New("unexpected EVAL_RO"))
}
func (r *scriptedRedis) EvalShaRO(context.Context, string, []string, ...interface{}) *redis.Cmd {
	return redis.NewCmdResult(int64(0), errors.New("unexpected EVALSHA_RO"))
}
func (r *scriptedRedis) ScriptExists(context.Context, ...string) *redis.BoolSliceCmd {
	return redis.NewBoolSliceResult(nil, errors.New("unexpected SCRIPT EXISTS"))
}
func (r *scriptedRedis) ScriptLoad(context.Context, string) *redis.StringCmd {
	return redis.NewStringResult("", errors.New("unexpected SCRIPT LOAD"))
}

func TestGovernorAcquireFailsClosedOnRedisError(t *testing.T) {
	fake := &scriptedRedis{runAcquire: func(context.Context) (int64, error) {
		return 0, errors.New("redis unavailable")
	}}
	g := NewGovernor(fake, GovernorConfig{Lease: time.Second, AcquireTimeout: time.Second})
	_, err := g.Acquire(context.Background(), context.Background(), "credential", 1)
	if !errors.Is(err, ErrGovernorUnavailable) {
		t.Fatalf("Acquire error=%v, want ErrGovernorUnavailable", err)
	}
}

func TestGovernorPermitRenewsAndReleases(t *testing.T) {
	var renewals int
	fake := &scriptedRedis{
		runAcquire: func(context.Context) (int64, error) { return 1, nil },
		runRenew: func(ctx context.Context) (int64, error) {
			if ctx.Err() != nil {
				return 0, ctx.Err()
			}
			renewals++
			return 1, nil
		},
	}
	g := NewGovernor(fake, GovernorConfig{Lease: 30 * time.Millisecond, AcquireTimeout: time.Second, ReleaseTimeout: time.Second})
	permit, err := g.Acquire(context.Background(), context.Background(), "credential", 1)
	if err != nil {
		t.Fatalf("Acquire: %v", err)
	}
	select {
	case <-time.After(80 * time.Millisecond):
	case <-permit.Context().Done():
		t.Fatalf("permit canceled before lease renewal: %v", context.Cause(permit.Context()))
	}
	permit.Release()
	fake.mu.Lock()
	gotRenewals, releases := renewals, fake.releases
	fake.mu.Unlock()
	if gotRenewals == 0 || releases != 1 {
		t.Fatalf("renewals=%d releases=%d want at least one renewal and one release", gotRenewals, releases)
	}
}

func TestGovernorAcquireTimeoutBoundsBlockedRedisCall(t *testing.T) {
	fake := &scriptedRedis{runAcquire: func(ctx context.Context) (int64, error) {
		<-ctx.Done()
		return 0, ctx.Err()
	}}
	g := NewGovernor(fake, GovernorConfig{Lease: time.Second, AcquireTimeout: 10 * time.Millisecond})
	started := time.Now()
	_, err := g.Acquire(context.Background(), context.Background(), "credential", 1)
	if !errors.Is(err, ErrGovernorTimeout) {
		t.Fatalf("Acquire error=%v, want ErrGovernorTimeout", err)
	}
	if time.Since(started) > time.Second {
		t.Fatal("Acquire exceeded its bounded timeout")
	}
}

func TestGovernorRedisIntegration(t *testing.T) {
	addr := os.Getenv("TEST_PROVIDER_REDIS_URL")
	if addr == "" {
		t.Skip("TEST_PROVIDER_REDIS_URL unset; skipping local Redis integration")
	}
	opt, err := redis.ParseURL(addr)
	if err != nil {
		t.Fatalf("parse TEST_PROVIDER_REDIS_URL: %v", err)
	}
	rdb := redis.NewClient(opt)
	defer rdb.Close()
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Fatalf("connect to explicitly configured test Redis: %v", err)
	}

	class := "test:" + uuid.NewString()
	cfg := GovernorConfig{Lease: 150 * time.Millisecond, AcquireTimeout: time.Second, PollInterval: 2 * time.Millisecond, ReleaseTimeout: time.Second}
	g1, g2 := NewGovernor(rdb, cfg), NewGovernor(rdb, cfg)
	p1, err := g1.Acquire(context.Background(), context.Background(), class, 1)
	if err != nil {
		t.Fatalf("first acquire: %v", err)
	}
	defer p1.Release()
	if _, err := g2.Acquire(context.Background(), context.Background(), class, 1); !errors.Is(err, ErrGovernorTimeout) {
		t.Fatalf("second acquire while cap occupied: %v", err)
	}
	select {
	case <-time.After(400 * time.Millisecond):
	case <-p1.Context().Done():
		t.Fatalf("renewed lease lost: %v", context.Cause(p1.Context()))
	}
	p1.Release()
	p2, err := g2.Acquire(context.Background(), context.Background(), class, 1)
	if err != nil {
		t.Fatalf("acquire after release: %v", err)
	}
	p2.Release()
}

func TestLocalPermitPreservesCallDeadline(t *testing.T) {
	g := NewLocalGovernor()
	callCtx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	permit, err := g.Acquire(context.Background(), callCtx, "credential", 1)
	if err != nil {
		t.Fatal(err)
	}
	got, ok := permit.Context().Deadline()
	want, wantOK := callCtx.Deadline()
	if !ok || !wantOK || !got.Equal(want) {
		t.Fatalf("permit deadline=%v,%v call deadline=%v,%v", got, ok, want, wantOK)
	}
	permit.Release()
}
