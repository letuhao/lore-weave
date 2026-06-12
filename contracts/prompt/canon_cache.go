// Package prompt — L5.E canon cache.
//
// RAID cycle 25 DPS 1. Hot-read cache for per-reality canon entries (L5.D
// `canon_projection`). Used by the `[WORLD_CANON]` prompt assembly hot path
// (cycle 21 L4.D) so prompt builders do not round-trip to per-reality
// Postgres on every turn.
//
// # Invalidation strategy — Q-L5-1 LOCKED
//
// **Event-driven invalidation is PRIMARY.** The cycle-24 L5.B canon_writer
// emits an in-process `Invalidate(realityID, canonEntryID)` signal after
// every successful UPSERT into `canon_projection`. The 60s TTL exists ONLY
// as a fallback for crash-recovery / lost-signal scenarios; steady-state
// hits should refresh from event-driven invalidation, never TTL.
//
// Hit-rate invariant (L5.E.4 acceptance): ≥ 90% in steady-state prompt
// assembly load. The metric `lw_canon_cache_hit_rate{reality_id}` (L5.E.5)
// is registered in `contracts/observability/inventory.yaml`.
//
// # Per-reality isolation (cache-key shape)
//
// Cache key: `canon:<reality_id>:<book_id>:<attribute_path>`
//
// The reality_id PREFIX is mandatory. Two realities of the same book have
// DIFFERENT cached entries even for identical (book_id, attribute_path)
// because L3 events may override L2_seeded canon per-reality. Sharing a
// cache row across realities would leak overrides across reality
// boundaries — a P0 invariant violation.
//
// # Cacheable-attribute whitelist
//
// Per S09 §12Y.4 [WORLD_CANON] discipline: only canon attributes intended
// for the prompt hot path are cacheable. Free-text body fields (e.g.
// chapter prose, raw lore excerpts) are NOT cached — they belong in the
// PromptContext.History / Memory paths, not the canon cache. The whitelist
// is `attribute_path` PREFIX-based:
//
//   - "world.*"        — world-level facts (climate, geography axioms)
//   - "faction.*"      — faction descriptors (allegiance, banner color)
//   - "character.*"    — author-canonical character traits (NOT live state)
//   - "rule.*"         — gameplay rules / mechanics canon
//   - "lore.*"         — short-form lore tags (NOT prose body)
//
// Anything outside the whitelist returns ErrAttributeNotCacheable; the
// caller falls back to a direct read. This is a defense-in-depth check —
// the cache layer enforces it even if a buggy caller tries to cache a
// disallowed path.
//
// # LOCKED Q-IDs honored
//
//   - Q-L5-1  : event-driven invalidate primary; TTL fallback only
//   - Q-L1A-2 : canon SSOT in glossary DB; per-reality canon_projection is
//               the cache layer this serves
//   - Q-L5-3  : canon_layer column carried through cache value verbatim
//
// # Cross-cycle wiring
//
//   - Cycle 5 (L1.F)  : Redis Sentinel pool — production `Backend` impl
//                        wraps a sentinel-fronted *redis.Client. Tests
//                        inject FakeBackend (in-process map).
//   - Cycle 23 (L5.D) : per-reality canon_projection table — cache misses
//                        fall through to a `Reader.ReadCanon` call that
//                        production wires to the canon_projection SELECT.
//   - Cycle 24 (L5.B) : canon_writer calls `Invalidate` AFTER its UPSERT
//                        succeeds. Wiring lands in the cycle 25+ runtime
//                        bind step (deferred to D-CANON-CACHE-WIRE).
package prompt

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
)

// ─────────────────────────────────────────────────────────────────────────
// Whitelist (Q-L5-1 hot-path discipline).
// ─────────────────────────────────────────────────────────────────────────

// cacheableAttributePrefixes is the whitelist of attribute_path prefixes
// permitted in the canon cache. See package doc for rationale.
var cacheableAttributePrefixes = []string{
	"world.",
	"faction.",
	"character.",
	"rule.",
	"lore.",
}

// IsAttributeCacheable returns true if attributePath starts with one of
// the whitelisted prefixes. Exported so callers (e.g. canon_reader) can
// pre-check before calling Get/Set.
func IsAttributeCacheable(attributePath string) bool {
	for _, prefix := range cacheableAttributePrefixes {
		if strings.HasPrefix(attributePath, prefix) {
			return true
		}
	}
	return false
}

// ErrAttributeNotCacheable is returned by Get/Set when attributePath is
// outside the whitelist. Callers should fall through to direct read.
var ErrAttributeNotCacheable = errors.New("canon_cache: attribute path not in cacheable whitelist")

// ErrCacheMiss is returned by Get when the key is absent or expired.
// Distinct from ErrAttributeNotCacheable so callers can route correctly:
// miss → fall through to Reader; not-cacheable → skip cache entirely.
var ErrCacheMiss = errors.New("canon_cache: miss")

// ─────────────────────────────────────────────────────────────────────────
// Cache entry + TTL.
// ─────────────────────────────────────────────────────────────────────────

// DefaultTTL is the Q-L5-1 fallback TTL (60s). Production may override
// via Config.TTL but the documented contract is 60s.
const DefaultTTL = 60 * time.Second

// CacheEntry is one (reality, book, attribute) → canon value mapping.
// Mirrors a single canon_projection row's read-side projection.
type CacheEntry struct {
	RealityID     uuid.UUID
	CanonEntryID  uuid.UUID
	BookID        uuid.UUID
	AttributePath string
	// Value is the canonical JSON-encoded canon value (opaque to the
	// cache — caller decodes per attribute schema).
	Value []byte
	// CanonLayer carries Q-L5-3 enum ("L1_axiom" | "L2_seeded").
	CanonLayer string
	// LastSyncedAt is the canon_projection.last_synced_at column —
	// Q-L5-1 cache-staleness probe key.
	LastSyncedAt time.Time
	// ExpiresAt is the Q-L5-1 fallback TTL deadline. Get treats entries
	// with ExpiresAt <= now() as miss.
	ExpiresAt time.Time
}

// CacheKey returns the canonical key string for this entry. Mirrors
// `BuildKey` so writers and readers agree on the shape.
func (e CacheEntry) CacheKey() string {
	return BuildKey(e.RealityID, e.BookID, e.AttributePath)
}

// BuildKey assembles the canonical cache key. Per package doc, the
// reality_id PREFIX is mandatory for per-reality isolation.
func BuildKey(realityID, bookID uuid.UUID, attributePath string) string {
	return fmt.Sprintf("canon:%s:%s:%s", realityID, bookID, attributePath)
}

// ─────────────────────────────────────────────────────────────────────────
// Backend interface — production binds Redis Sentinel (cycle 5 L1.F);
// tests inject FakeBackend (in-process map).
// ─────────────────────────────────────────────────────────────────────────

// Backend abstracts the underlying KV store. Production wraps
// go-redis/v9's redis.Client behind this interface so the cache logic
// stays storage-agnostic.
//
// All methods take ctx so a slow Redis is observable + cancellable.
type Backend interface {
	// GetRaw returns the raw stored bytes for key, or ErrCacheMiss if
	// the key is absent / expired.
	GetRaw(ctx context.Context, key string) ([]byte, error)

	// SetRaw stores raw bytes at key with the given TTL. TTL > 0 is
	// the Q-L5-1 fallback safety net.
	SetRaw(ctx context.Context, key string, value []byte, ttl time.Duration) error

	// Delete removes one or more keys. Event-driven invalidation uses
	// this; returns the number actually deleted.
	Delete(ctx context.Context, keys ...string) (int, error)

	// Scan returns keys matching the prefix (used by reality-scoped or
	// canon_entry-scoped invalidation). Implementations SHOULD bound
	// the scan (e.g. SCAN with COUNT) — see FakeBackend for the test
	// contract.
	Scan(ctx context.Context, prefix string) ([]string, error)
}

// ─────────────────────────────────────────────────────────────────────────
// Cache.
// ─────────────────────────────────────────────────────────────────────────

// Cache is the L5.E canon cache. Threadsafe. One instance per process.
type Cache struct {
	backend Backend
	codec   Codec
	ttl     time.Duration
	clock   Clock
	metrics MetricsSink
}

// Config bundles dependencies.
type Config struct {
	// Backend is required (Redis in prod, FakeBackend in tests).
	Backend Backend
	// Codec marshals CacheEntry to bytes for Backend storage. Defaults
	// to JSONCodec.
	Codec Codec
	// TTL overrides DefaultTTL (Q-L5-1 fallback). Zero = DefaultTTL.
	TTL time.Duration
	// Clock is optional (defaults to real wall-clock).
	Clock Clock
	// Metrics is optional (defaults to NoOpMetrics).
	Metrics MetricsSink
}

// New constructs a Cache. Backend is required; everything else has a
// safe default.
func New(cfg Config) (*Cache, error) {
	if cfg.Backend == nil {
		return nil, errors.New("canon_cache: Backend nil")
	}
	codec := cfg.Codec
	if codec == nil {
		codec = JSONCodec{}
	}
	ttl := cfg.TTL
	if ttl <= 0 {
		ttl = DefaultTTL
	}
	clk := cfg.Clock
	if clk == nil {
		clk = realClock{}
	}
	met := cfg.Metrics
	if met == nil {
		met = NoOpMetrics{}
	}
	return &Cache{backend: cfg.Backend, codec: codec, ttl: ttl, clock: clk, metrics: met}, nil
}

// Get returns the cached CacheEntry for (realityID, bookID, attributePath)
// or ErrCacheMiss / ErrAttributeNotCacheable. On hit, emits a
// CacheHit metric labelled by realityID.
func (c *Cache) Get(ctx context.Context, realityID, bookID uuid.UUID, attributePath string) (CacheEntry, error) {
	if !IsAttributeCacheable(attributePath) {
		return CacheEntry{}, ErrAttributeNotCacheable
	}
	key := BuildKey(realityID, bookID, attributePath)
	raw, err := c.backend.GetRaw(ctx, key)
	if err != nil {
		if errors.Is(err, ErrCacheMiss) {
			c.metrics.IncMiss(realityID)
			return CacheEntry{}, ErrCacheMiss
		}
		c.metrics.IncMiss(realityID)
		return CacheEntry{}, fmt.Errorf("canon_cache: backend Get: %w", err)
	}
	entry, err := c.codec.Decode(raw)
	if err != nil {
		// Bad cached blob = miss + emit corruption metric. Caller
		// recovers via cache-aside fall-through.
		c.metrics.IncMiss(realityID)
		return CacheEntry{}, fmt.Errorf("canon_cache: decode: %w", err)
	}
	// Q-L5-1 fallback TTL check — even if backend honors TTL natively
	// (Redis EXPIRE), defense-in-depth verifies here vs. clock-skew.
	if !entry.ExpiresAt.IsZero() && !entry.ExpiresAt.After(c.clock.Now()) {
		c.metrics.IncMiss(realityID)
		_, _ = c.backend.Delete(ctx, key) // best-effort cleanup
		return CacheEntry{}, ErrCacheMiss
	}
	c.metrics.IncHit(realityID)
	return entry, nil
}

// Set stores entry under its canonical key with the Q-L5-1 fallback TTL.
// Returns ErrAttributeNotCacheable if entry.AttributePath is outside the
// whitelist (defense vs. buggy callers).
//
// The stored entry.ExpiresAt is overwritten to (now + TTL) — callers
// MUST NOT pre-set it.
func (c *Cache) Set(ctx context.Context, entry CacheEntry) error {
	if !IsAttributeCacheable(entry.AttributePath) {
		return ErrAttributeNotCacheable
	}
	entry.ExpiresAt = c.clock.Now().Add(c.ttl)
	raw, err := c.codec.Encode(entry)
	if err != nil {
		return fmt.Errorf("canon_cache: encode: %w", err)
	}
	if err := c.backend.SetRaw(ctx, entry.CacheKey(), raw, c.ttl); err != nil {
		return fmt.Errorf("canon_cache: backend Set: %w", err)
	}
	return nil
}

// Invalidate is the Q-L5-1 PRIMARY invalidation path. Called by the
// cycle-24 canon_writer after every successful UPSERT into
// canon_projection.
//
// Semantics:
//   - Targets a SPECIFIC (realityID, canonEntryID) pair — scans
//     canon:<realityID>:* and deletes any entry whose canonical
//     canon_entry_id matches.
//   - Idempotent — calling twice is a no-op (Delete returns 0 the
//     second time).
//   - Returns the count of deleted keys for observability.
//
// On Scan/Delete failure, returns the wrapped error; canon_writer
// surfaces this in its audit row but does NOT NACK the source event
// (cache invalidation is best-effort — the Q-L5-1 fallback TTL ensures
// eventual freshness).
func (c *Cache) Invalidate(ctx context.Context, realityID, canonEntryID uuid.UUID) (int, error) {
	prefix := fmt.Sprintf("canon:%s:", realityID)
	keys, err := c.backend.Scan(ctx, prefix)
	if err != nil {
		return 0, fmt.Errorf("canon_cache: invalidate scan reality=%s: %w", realityID, err)
	}
	if len(keys) == 0 {
		return 0, nil
	}
	// Filter by canon_entry_id — we must decode each entry to check.
	// In high-cardinality realities this can be expensive; production
	// MAY add a secondary index (canon:idx:<canon_entry_id>) — see
	// D-CANON-CACHE-IDX deferred row.
	matched := make([]string, 0, len(keys))
	for _, key := range keys {
		raw, err := c.backend.GetRaw(ctx, key)
		if err != nil {
			// Best-effort: skip entries we cannot read.
			continue
		}
		entry, err := c.codec.Decode(raw)
		if err != nil {
			// Corruption — invalidate aggressively.
			matched = append(matched, key)
			continue
		}
		if entry.CanonEntryID == canonEntryID {
			matched = append(matched, key)
		}
	}
	if len(matched) == 0 {
		return 0, nil
	}
	deleted, err := c.backend.Delete(ctx, matched...)
	if err != nil {
		return deleted, fmt.Errorf("canon_cache: invalidate delete reality=%s entry=%s: %w", realityID, canonEntryID, err)
	}
	c.metrics.AddInvalidations(realityID, deleted)
	return deleted, nil
}

// InvalidateReality drops ALL cache entries for a reality. Used during
// reality lifecycle transitions (e.g. seeding → active reseed) or
// catastrophic divergence recovery. Returns the count deleted.
func (c *Cache) InvalidateReality(ctx context.Context, realityID uuid.UUID) (int, error) {
	prefix := fmt.Sprintf("canon:%s:", realityID)
	keys, err := c.backend.Scan(ctx, prefix)
	if err != nil {
		return 0, fmt.Errorf("canon_cache: invalidate-reality scan: %w", err)
	}
	if len(keys) == 0 {
		return 0, nil
	}
	deleted, err := c.backend.Delete(ctx, keys...)
	if err != nil {
		return deleted, fmt.Errorf("canon_cache: invalidate-reality delete: %w", err)
	}
	c.metrics.AddInvalidations(realityID, deleted)
	return deleted, nil
}

// ─────────────────────────────────────────────────────────────────────────
// Codec — pluggable serialization.
// ─────────────────────────────────────────────────────────────────────────

// Codec serializes CacheEntry for Backend storage.
type Codec interface {
	Encode(entry CacheEntry) ([]byte, error)
	Decode(raw []byte) (CacheEntry, error)
}

// JSONCodec is the default Codec. Production may swap to a faster
// MessagePack/protobuf impl without touching Cache logic.
type JSONCodec struct{}

// Encode serializes to the canonical JSON encoding used on the wire.
func (JSONCodec) Encode(entry CacheEntry) ([]byte, error) {
	return jsonMarshalEntry(entry)
}

// Decode parses the canonical JSON encoding.
func (JSONCodec) Decode(raw []byte) (CacheEntry, error) {
	return jsonUnmarshalEntry(raw)
}

// ─────────────────────────────────────────────────────────────────────────
// MetricsSink — production binds Prometheus; tests inject FakeMetrics.
// ─────────────────────────────────────────────────────────────────────────

// MetricsSink emits cache observability per L5.E.5 inventory entry
// (`lw_canon_cache_hit_rate{reality_id}`).
type MetricsSink interface {
	IncHit(realityID uuid.UUID)
	IncMiss(realityID uuid.UUID)
	AddInvalidations(realityID uuid.UUID, n int)
}

// NoOpMetrics is the default. Production binds the Prometheus impl.
type NoOpMetrics struct{}

func (NoOpMetrics) IncHit(uuid.UUID)                        {}
func (NoOpMetrics) IncMiss(uuid.UUID)                       {}
func (NoOpMetrics) AddInvalidations(uuid.UUID, int)         {}

// ─────────────────────────────────────────────────────────────────────────
// Clock.
// ─────────────────────────────────────────────────────────────────────────

// Clock lets tests inject a deterministic time source.
type Clock interface {
	Now() time.Time
}

type realClock struct{}

func (realClock) Now() time.Time { return time.Now().UTC() }

// ─────────────────────────────────────────────────────────────────────────
// FakeBackend — in-process map. Test-only export so canon_reader tests
// can share infra with cache tests.
// ─────────────────────────────────────────────────────────────────────────

// FakeBackend is an in-process Backend. Threadsafe. Used by
// canon_cache_test.go and canon_reader_test.go.
type FakeBackend struct {
	mu      sync.Mutex
	store   map[string][]byte
	expires map[string]time.Time
	clock   Clock
}

// NewFakeBackend constructs an in-memory backend. clock is required so
// tests can advance time for TTL testing.
func NewFakeBackend(clock Clock) *FakeBackend {
	if clock == nil {
		clock = realClock{}
	}
	return &FakeBackend{
		store:   make(map[string][]byte),
		expires: make(map[string]time.Time),
		clock:   clock,
	}
}

// GetRaw implements Backend.
func (f *FakeBackend) GetRaw(_ context.Context, key string) ([]byte, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if exp, ok := f.expires[key]; ok && !exp.After(f.clock.Now()) {
		delete(f.store, key)
		delete(f.expires, key)
		return nil, ErrCacheMiss
	}
	v, ok := f.store[key]
	if !ok {
		return nil, ErrCacheMiss
	}
	out := make([]byte, len(v))
	copy(out, v)
	return out, nil
}

// SetRaw implements Backend.
func (f *FakeBackend) SetRaw(_ context.Context, key string, value []byte, ttl time.Duration) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	stored := make([]byte, len(value))
	copy(stored, value)
	f.store[key] = stored
	if ttl > 0 {
		f.expires[key] = f.clock.Now().Add(ttl)
	}
	return nil
}

// Delete implements Backend.
func (f *FakeBackend) Delete(_ context.Context, keys ...string) (int, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	deleted := 0
	for _, k := range keys {
		if _, ok := f.store[k]; ok {
			delete(f.store, k)
			delete(f.expires, k)
			deleted++
		}
	}
	return deleted, nil
}

// Scan implements Backend. Returns a snapshot — safe for concurrent
// iteration / mutation.
func (f *FakeBackend) Scan(_ context.Context, prefix string) ([]string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	out := make([]string, 0)
	for k := range f.store {
		if strings.HasPrefix(k, prefix) {
			out = append(out, k)
		}
	}
	return out, nil
}

// Size returns the entry count (test helper).
func (f *FakeBackend) Size() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return len(f.store)
}

// FixedClock is a Clock that returns a settable time. Test helper.
type FixedClock struct {
	mu  sync.Mutex
	now time.Time
}

// NewFixedClock constructs a FixedClock at t.
func NewFixedClock(t time.Time) *FixedClock { return &FixedClock{now: t} }

// Now implements Clock.
func (f *FixedClock) Now() time.Time {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.now
}

// Advance moves the clock forward by d (test helper).
func (f *FixedClock) Advance(d time.Duration) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.now = f.now.Add(d)
}

// FakeMetrics is an in-memory MetricsSink for tests.
type FakeMetrics struct {
	mu            sync.Mutex
	Hits          map[uuid.UUID]int
	Misses        map[uuid.UUID]int
	Invalidations map[uuid.UUID]int
}

// NewFakeMetrics constructs an empty FakeMetrics.
func NewFakeMetrics() *FakeMetrics {
	return &FakeMetrics{
		Hits:          map[uuid.UUID]int{},
		Misses:        map[uuid.UUID]int{},
		Invalidations: map[uuid.UUID]int{},
	}
}

// IncHit implements MetricsSink.
func (f *FakeMetrics) IncHit(realityID uuid.UUID) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.Hits[realityID]++
}

// IncMiss implements MetricsSink.
func (f *FakeMetrics) IncMiss(realityID uuid.UUID) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.Misses[realityID]++
}

// AddInvalidations implements MetricsSink.
func (f *FakeMetrics) AddInvalidations(realityID uuid.UUID, n int) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.Invalidations[realityID] += n
}
