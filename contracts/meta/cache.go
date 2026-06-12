package meta

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

// cache.go — L1.F.1 Meta-side Redis cache library.
//
// ## Purpose (C03 §12O.6, Q-L1F-1)
//
// Meta reads (RealityRouting, EntityStatus, SensitivePaths) are
// hot-path: every command resolves a reality_id → routing record.
// Hitting Postgres on every command would saturate pgbouncer's backend
// pool long before the 5K virtual cap. So we cache reads in Redis
// (shared Sentinel cluster per Q-L1F-1: V1 single cluster; per-AZ V3+).
//
// ## Invalidation
//
// Event-driven primary (Q-L5-1): when MetaWrite() emits
// `reality.status.changed` or similar `xreality.*` events, the cache
// invalidator listens on the Redis Stream and `DEL`s the affected key.
// 60s TTL is the fallback: if the invalidator falls behind, stale
// reads expire on their own.
//
// ## What this file ships in cycle 5
//
// - `Cache` interface — abstract over Redis vs in-memory (test fake)
// - `KeyRegistry` — loaded from `contracts/cache/keys.yaml` (L1.F.5)
// - `Key`         — strongly-typed cache key with TTL contract
// - `InMemoryCache` — test fake; production Redis impl ships cycle 6+
//
// The actual Redis connection logic is intentionally deferred to a later
// cycle alongside the Redis sentinel sidecar config (cycle 7 — L1.J
// degraded-mode handlers also use the same connection).

// CacheValue is the opaque bytes stored under a key. We deliberately
// don't expose JSON / proto codec here — callers serialize themselves
// so the library stays codec-agnostic.
type CacheValue []byte

// Cache is the read/write surface every cache adapter implements.
type Cache interface {
	// Get returns the value at key. The bool indicates hit/miss; nil
	// error + false = clean miss.
	Get(ctx context.Context, key string) (CacheValue, bool, error)

	// Set stores value at key with the supplied TTL. TTL <= 0 means
	// "do not expire" — but callers should not use that; every cached
	// key MUST have a TTL per the 60s fallback rule.
	Set(ctx context.Context, key string, value CacheValue, ttl time.Duration) error

	// Del removes a single key. Idempotent: deleting a missing key is OK.
	Del(ctx context.Context, key string) error

	// DelByPrefix removes every key whose name starts with prefix.
	// Used by the event-driven invalidator when an `xreality.*` event
	// signals that a whole reality's cached state needs to drop.
	DelByPrefix(ctx context.Context, prefix string) (int, error)
}

// KeyKind enumerates the cache-key namespaces declared in
// contracts/cache/keys.yaml. Adding a new namespace requires:
//   1. New variant here
//   2. New entry in contracts/cache/keys.yaml
//   3. KeyRegistry test coverage
type KeyKind string

const (
	// KindRealityRouting caches the `RealityRouting` row.
	KindRealityRouting KeyKind = "reality_routing"
	// KindEntityStatus caches per-reality entity status reads.
	KindEntityStatus KeyKind = "entity_status"
	// KindSensitivePaths caches the parsed sensitive-paths registry.
	KindSensitivePaths KeyKind = "sensitive_paths"
	// KindCanonProjection caches per-reality canon snapshot reads
	// (lands cycle 23; placeholder here so the registry shape is stable).
	KindCanonProjection KeyKind = "canon_projection"
)

// IsValid reports whether k is one of the enumerated kinds.
func (k KeyKind) IsValid() bool {
	switch k {
	case KindRealityRouting, KindEntityStatus, KindSensitivePaths, KindCanonProjection:
		return true
	}
	return false
}

// Key is a strongly-typed cache key. The wire format is
// `lw:<kind>:<scope>` so a Redis `KEYS` scan (or our DelByPrefix) can
// match cleanly.
type Key struct {
	Kind  KeyKind
	Scope string // typically reality_id, but could be "global" for sensitive_paths
}

// String returns the wire format.
func (k Key) String() string {
	return fmt.Sprintf("lw:%s:%s", k.Kind, k.Scope)
}

// KeyEntry is one row of the keys.yaml registry.
type KeyEntry struct {
	Kind                 KeyKind
	TTL                  time.Duration
	InvalidationTrigger  string // event name that invalidates, "" = TTL-only
	OwnerService         string // for CODEOWNERS routing
	SensitivePathID      string // optional cross-link to sensitive-read paths
}

// KeyRegistry is the parsed contracts/cache/keys.yaml. Mainly used to
// enforce: every Get/Set call uses a KIND that's registered.
type KeyRegistry struct {
	entries map[KeyKind]KeyEntry
}

// NewKeyRegistry constructs from a parsed slice. Returns an error if
// any kind is invalid or duplicated.
func NewKeyRegistry(entries []KeyEntry) (*KeyRegistry, error) {
	r := &KeyRegistry{entries: make(map[KeyKind]KeyEntry, len(entries))}
	for i, e := range entries {
		if !e.Kind.IsValid() {
			return nil, fmt.Errorf("%w: entry %d: kind %q not enumerated",
				ErrCacheRegistryInvalid, i, e.Kind)
		}
		if _, dup := r.entries[e.Kind]; dup {
			return nil, fmt.Errorf("%w: kind %q duplicated",
				ErrCacheRegistryInvalid, e.Kind)
		}
		if e.TTL <= 0 {
			return nil, fmt.Errorf("%w: kind %q TTL %s must be > 0 (60s fallback rule)",
				ErrCacheRegistryInvalid, e.Kind, e.TTL)
		}
		if e.TTL > 24*time.Hour {
			return nil, fmt.Errorf("%w: kind %q TTL %s exceeds 24h (use event-driven instead)",
				ErrCacheRegistryInvalid, e.Kind, e.TTL)
		}
		r.entries[e.Kind] = e
	}
	return r, nil
}

// Lookup returns the registered entry for a kind, or ErrCacheKindUnregistered.
func (r *KeyRegistry) Lookup(kind KeyKind) (KeyEntry, error) {
	e, ok := r.entries[kind]
	if !ok {
		return KeyEntry{}, fmt.Errorf("%w: %q", ErrCacheKindUnregistered, kind)
	}
	return e, nil
}

// Kinds returns the set of registered kinds. Useful for verify lints.
func (r *KeyRegistry) Kinds() []KeyKind {
	out := make([]KeyKind, 0, len(r.entries))
	for k := range r.entries {
		out = append(out, k)
	}
	return out
}

// ── Errors (mirror to errors.go style) ────────────────────────────────

var (
	// ErrCacheRegistryInvalid is returned by NewKeyRegistry when the
	// supplied entries fail validation (bad kind, dup, bad TTL).
	ErrCacheRegistryInvalid = errors.New("meta: cache key registry invalid")

	// ErrCacheKindUnregistered is returned by Cache wrappers when a
	// caller tries to Get/Set a kind that's not in the registry.
	ErrCacheKindUnregistered = errors.New("meta: cache kind not registered")
)

// ── InMemoryCache — test fake (production Redis impl ships cycle 6) ──

// InMemoryCache is a goroutine-safe in-memory implementation of Cache.
// Used by tests so they don't need a live Redis. Production code should
// use the Redis adapter (ships alongside the Sentinel sidecar config).
type InMemoryCache struct {
	mu    sync.RWMutex
	data  map[string]inMemEntry
	clock func() time.Time // injected for deterministic tests
}

type inMemEntry struct {
	value      CacheValue
	expiresAt  time.Time
}

// NewInMemoryCache constructs an empty cache that uses time.Now for TTL.
func NewInMemoryCache() *InMemoryCache {
	return &InMemoryCache{data: make(map[string]inMemEntry), clock: time.Now}
}

// WithClock returns a cache with a custom clock. Useful for tests.
func (c *InMemoryCache) WithClock(clock func() time.Time) *InMemoryCache {
	c.clock = clock
	return c
}

// Get implements Cache.
func (c *InMemoryCache) Get(_ context.Context, key string) (CacheValue, bool, error) {
	c.mu.RLock()
	e, ok := c.data[key]
	c.mu.RUnlock()
	if !ok {
		return nil, false, nil
	}
	if c.clock().After(e.expiresAt) {
		// Lazy expiry — caller might re-Get racing another writer; that's fine.
		c.mu.Lock()
		delete(c.data, key)
		c.mu.Unlock()
		return nil, false, nil
	}
	return e.value, true, nil
}

// Set implements Cache.
func (c *InMemoryCache) Set(_ context.Context, key string, value CacheValue, ttl time.Duration) error {
	if ttl <= 0 {
		return fmt.Errorf("%w: ttl must be > 0", ErrCacheRegistryInvalid)
	}
	c.mu.Lock()
	c.data[key] = inMemEntry{value: value, expiresAt: c.clock().Add(ttl)}
	c.mu.Unlock()
	return nil
}

// Del implements Cache.
func (c *InMemoryCache) Del(_ context.Context, key string) error {
	c.mu.Lock()
	delete(c.data, key)
	c.mu.Unlock()
	return nil
}

// DelByPrefix implements Cache.
func (c *InMemoryCache) DelByPrefix(_ context.Context, prefix string) (int, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	deleted := 0
	for k := range c.data {
		if len(k) >= len(prefix) && k[:len(prefix)] == prefix {
			delete(c.data, k)
			deleted++
		}
	}
	return deleted, nil
}
