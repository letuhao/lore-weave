package meta

import (
	"context"
	"errors"
	"testing"
	"time"
)

// cache_test.go — L1.F.1 cache library tests.

func TestKeyKind_IsValid(t *testing.T) {
	for _, kind := range []KeyKind{KindRealityRouting, KindEntityStatus, KindSensitivePaths, KindCanonProjection} {
		if !kind.IsValid() {
			t.Fatalf("kind %q should be valid", kind)
		}
	}
	if KeyKind("bogus").IsValid() {
		t.Fatalf("'bogus' should not be valid")
	}
}

func TestKey_StringFormat(t *testing.T) {
	k := Key{Kind: KindRealityRouting, Scope: "abcd-1234"}
	if got, want := k.String(), "lw:reality_routing:abcd-1234"; got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestKeyRegistry_HappyPath(t *testing.T) {
	r, err := NewKeyRegistry([]KeyEntry{
		{Kind: KindRealityRouting, TTL: 30 * time.Second, InvalidationTrigger: "reality.status.changed", OwnerService: "world-service"},
		{Kind: KindEntityStatus, TTL: 60 * time.Second, OwnerService: "world-service"},
	})
	if err != nil {
		t.Fatalf("registry: %v", err)
	}
	got, err := r.Lookup(KindRealityRouting)
	if err != nil {
		t.Fatalf("lookup: %v", err)
	}
	if got.TTL != 30*time.Second {
		t.Fatalf("TTL: got %s, want 30s", got.TTL)
	}
}

func TestKeyRegistry_RejectsBadKind(t *testing.T) {
	_, err := NewKeyRegistry([]KeyEntry{{Kind: "bogus", TTL: 30 * time.Second}})
	if !errors.Is(err, ErrCacheRegistryInvalid) {
		t.Fatalf("want ErrCacheRegistryInvalid, got %v", err)
	}
}

func TestKeyRegistry_RejectsDuplicateKind(t *testing.T) {
	_, err := NewKeyRegistry([]KeyEntry{
		{Kind: KindRealityRouting, TTL: 30 * time.Second},
		{Kind: KindRealityRouting, TTL: 60 * time.Second},
	})
	if !errors.Is(err, ErrCacheRegistryInvalid) {
		t.Fatalf("want ErrCacheRegistryInvalid (dup), got %v", err)
	}
}

func TestKeyRegistry_RejectsZeroTTL_60sFallbackRule(t *testing.T) {
	_, err := NewKeyRegistry([]KeyEntry{{Kind: KindRealityRouting, TTL: 0}})
	if !errors.Is(err, ErrCacheRegistryInvalid) {
		t.Fatalf("want ErrCacheRegistryInvalid (zero TTL), got %v", err)
	}
}

func TestKeyRegistry_RejectsTTLOver24h(t *testing.T) {
	_, err := NewKeyRegistry([]KeyEntry{{Kind: KindRealityRouting, TTL: 25 * time.Hour}})
	if !errors.Is(err, ErrCacheRegistryInvalid) {
		t.Fatalf("want ErrCacheRegistryInvalid (TTL>24h), got %v", err)
	}
}

func TestKeyRegistry_Lookup_Unregistered(t *testing.T) {
	r, err := NewKeyRegistry(nil)
	if err != nil {
		t.Fatalf("empty registry: %v", err)
	}
	_, err = r.Lookup(KindRealityRouting)
	if !errors.Is(err, ErrCacheKindUnregistered) {
		t.Fatalf("want ErrCacheKindUnregistered, got %v", err)
	}
}

// ── InMemoryCache invariant tests ────────────────────────────────────

func TestInMemoryCache_RoundTrip(t *testing.T) {
	c := NewInMemoryCache()
	ctx := context.Background()
	if err := c.Set(ctx, "k", CacheValue("v"), time.Minute); err != nil {
		t.Fatalf("set: %v", err)
	}
	v, hit, err := c.Get(ctx, "k")
	if err != nil || !hit || string(v) != "v" {
		t.Fatalf("get: hit=%v v=%q err=%v", hit, v, err)
	}
}

func TestInMemoryCache_Miss(t *testing.T) {
	c := NewInMemoryCache()
	_, hit, err := c.Get(context.Background(), "missing")
	if err != nil || hit {
		t.Fatalf("got hit=%v err=%v, want clean miss", hit, err)
	}
}

func TestInMemoryCache_ExpiresAfterTTL(t *testing.T) {
	// Inject a clock we control.
	now := time.Now()
	clock := func() time.Time { return now }
	c := NewInMemoryCache().WithClock(clock)
	ctx := context.Background()
	if err := c.Set(ctx, "k", CacheValue("v"), 100*time.Millisecond); err != nil {
		t.Fatalf("set: %v", err)
	}
	// Within TTL — hit
	_, hit, _ := c.Get(ctx, "k")
	if !hit {
		t.Fatalf("expected hit within TTL")
	}
	// Advance clock past TTL — miss
	now = now.Add(200 * time.Millisecond)
	_, hit, _ = c.Get(ctx, "k")
	if hit {
		t.Fatalf("expected miss after TTL")
	}
}

func TestInMemoryCache_Del(t *testing.T) {
	c := NewInMemoryCache()
	ctx := context.Background()
	_ = c.Set(ctx, "k", CacheValue("v"), time.Minute)
	_ = c.Del(ctx, "k")
	_, hit, _ := c.Get(ctx, "k")
	if hit {
		t.Fatalf("expected miss after del")
	}
	// Idempotent: delete again, no error.
	if err := c.Del(ctx, "k"); err != nil {
		t.Fatalf("re-del: %v", err)
	}
}

func TestInMemoryCache_DelByPrefix(t *testing.T) {
	c := NewInMemoryCache()
	ctx := context.Background()
	_ = c.Set(ctx, "lw:reality_routing:r1", CacheValue("a"), time.Minute)
	_ = c.Set(ctx, "lw:reality_routing:r2", CacheValue("b"), time.Minute)
	_ = c.Set(ctx, "lw:entity_status:r1", CacheValue("c"), time.Minute)

	deleted, err := c.DelByPrefix(ctx, "lw:reality_routing:")
	if err != nil {
		t.Fatalf("del prefix: %v", err)
	}
	if deleted != 2 {
		t.Fatalf("expected 2 deletes, got %d", deleted)
	}
	// Untouched key still present
	_, hit, _ := c.Get(ctx, "lw:entity_status:r1")
	if !hit {
		t.Fatalf("unrelated key dropped — prefix logic too broad")
	}
}

func TestInMemoryCache_SetRejectsZeroTTL(t *testing.T) {
	c := NewInMemoryCache()
	if err := c.Set(context.Background(), "k", CacheValue("v"), 0); err == nil {
		t.Fatalf("want error on zero TTL set")
	}
}
