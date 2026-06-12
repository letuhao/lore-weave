package capacity

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"sync/atomic"
	"time"
)

// L6.G.3 — Capacity override handler.
//
// Per S5 Tier 2 (capacity override discipline), an operator can grant
// a 24h override that allows a service deployment to exceed its
// budgets.yaml entry. The handler:
//
//   1. Loads active overrides from the meta-DB `capacity_budget_overrides`
//      audit table via the OverrideStore interface (cycle 30 ships the
//      contract + in-memory impl; the SQL writer lands in cycle 31+ L7
//      when the audit table migration ships).
//   2. Caches active overrides for 60s to avoid hammering meta-DB per
//      pod-admission-decision (deploy rate × override-check would be a
//      hot path during incidents — see Q-L6G-1 K8s context).
//   3. Auto-expires overrides at the 24h mark (granted_at + 24h < now).
//   4. Surfaces stats for the admission webhook to emit
//      `lw_capacity_admission_decisions_total{decision="allow_via_override"}`.

// OverrideAction is the override-record action.
type OverrideAction string

const (
	// OverrideAllow is the only V1 action — grants the service a 24h
	// budget exemption. Cycle-31+ may add OverrideRevoke for forced
	// expiration before the 24h mark.
	OverrideAllow OverrideAction = "allow"
)

// Override is one row from `capacity_budget_overrides`.
type Override struct {
	ServiceName string
	GrantedBy   string         // SRE who issued the override
	GrantedAt   time.Time      // UTC
	ExpiresAt   time.Time      // GrantedAt + 24h
	Reason      string         // human-readable; required (>= 16 chars)
	Action      OverrideAction // V1: always OverrideAllow
}

// Errors.
var (
	// ErrOverrideExpired is informational; lookup returns ok=false for
	// expired overrides, but tests can also assert with errors.Is.
	ErrOverrideExpired = errors.New("capacity: override expired")
	// ErrOverrideMissing means no override was found for the service.
	ErrOverrideMissing = errors.New("capacity: no override for service")
	// ErrInvalidOverride flags rows that fail Validate() (used on insert).
	ErrInvalidOverride = errors.New("capacity: invalid override row")
)

// minOverrideReasonLen is the minimum length for a Reason field. The
// override is a "break-glass" path; SRE must justify in the audit trail.
const minOverrideReasonLen = 16

// overrideTTL is the canonical 24h cap (S5 Tier 2). Cycle-30 hardcodes
// this; cycle-31+ may make it configurable per service class.
const overrideTTL = 24 * time.Hour

// Validate ensures the row meets foundational invariants. Called by
// OverrideStore implementations on insert; admission webhook callers
// rely on the store enforcing this.
func (o Override) Validate() error {
	if o.ServiceName == "" {
		return fmt.Errorf("%w: service_name empty", ErrInvalidOverride)
	}
	if o.GrantedBy == "" {
		return fmt.Errorf("%w: granted_by empty", ErrInvalidOverride)
	}
	if len(o.Reason) < minOverrideReasonLen {
		return fmt.Errorf("%w: reason too short (>= %d chars required)", ErrInvalidOverride, minOverrideReasonLen)
	}
	if o.Action != OverrideAllow {
		return fmt.Errorf("%w: action=%q V1 only supports %q", ErrInvalidOverride, o.Action, OverrideAllow)
	}
	if o.ExpiresAt.IsZero() || o.ExpiresAt.Before(o.GrantedAt) {
		return fmt.Errorf("%w: expires_at must be after granted_at", ErrInvalidOverride)
	}
	if o.ExpiresAt.Sub(o.GrantedAt) > overrideTTL+time.Minute {
		return fmt.Errorf("%w: ttl %s exceeds 24h cap", ErrInvalidOverride, o.ExpiresAt.Sub(o.GrantedAt))
	}
	return nil
}

// IsActive returns true if the override is currently in effect (now
// in [GrantedAt, ExpiresAt)). Pure function — callers can pass
// time.Now() or a frozen clock for testing.
func (o Override) IsActive(now time.Time) bool {
	return !now.Before(o.GrantedAt) && now.Before(o.ExpiresAt)
}

// OverrideStore is the persistence contract. Production wires the
// cycle-31+ SQL implementation; cycle-30 tests + the K8s webhook unit
// tests use InMemOverrideStore.
//
// Implementations MUST:
//   * Return only active (non-expired) overrides from List().
//   * Be safe for concurrent reads.
type OverrideStore interface {
	List(ctx context.Context, now time.Time) ([]Override, error)
}

// OverrideHandler is the runtime override surface used by the
// admission webhook. Construct once at boot via NewOverrideHandler.
//
// The handler caches active overrides for `cacheTTL` (default 60s) to
// keep per-pod-admission decisions O(1). On cache miss it queries the
// store; on cache hit it iterates the snapshot.
type OverrideHandler struct {
	store    OverrideStore
	cacheTTL time.Duration
	now      func() time.Time

	mu        sync.RWMutex
	cache     map[string]Override // service_name → override (active only)
	fetchedAt time.Time

	hits     atomic.Uint64
	misses   atomic.Uint64
	storeErr atomic.Uint64
}

// HandlerOption tunes the override handler.
type HandlerOption func(*OverrideHandler)

// WithCacheTTL overrides the default 60s cache TTL.
func WithCacheTTL(d time.Duration) HandlerOption {
	return func(h *OverrideHandler) {
		if d > 0 {
			h.cacheTTL = d
		}
	}
}

// WithClock overrides the now() clock — used by tests to control
// override expiration timing.
func WithClock(f func() time.Time) HandlerOption {
	return func(h *OverrideHandler) {
		if f != nil {
			h.now = f
		}
	}
}

// NewOverrideHandler constructs a handler. Defaults: cacheTTL=60s,
// clock=time.Now.
func NewOverrideHandler(store OverrideStore, opts ...HandlerOption) *OverrideHandler {
	h := &OverrideHandler{
		store:    store,
		cacheTTL: 60 * time.Second,
		now:      func() time.Time { return time.Now().UTC() },
		cache:    make(map[string]Override),
	}
	for _, opt := range opts {
		opt(h)
	}
	return h
}

// IsAllowed returns (true, override) if the service has an active
// override at `now`. Otherwise returns (false, zero-Override).
//
// Cache discipline:
//   * If `now - fetchedAt < cacheTTL` → return from cache snapshot.
//   * Else → fetch from store, rebuild cache, return result.
//
// On store error, the handler returns (false, zero) and increments the
// storeErr counter — the admission webhook MUST treat that as "no
// override" (fail-closed: a flaky store should not auto-grant
// exemptions).
func (h *OverrideHandler) IsAllowed(ctx context.Context, service string) (bool, Override) {
	now := h.now()

	h.mu.RLock()
	stale := now.Sub(h.fetchedAt) >= h.cacheTTL || h.fetchedAt.IsZero()
	if !stale {
		o, ok := h.cache[service]
		h.mu.RUnlock()
		if ok && o.IsActive(now) {
			h.hits.Add(1)
			return true, o
		}
		h.misses.Add(1)
		return false, Override{}
	}
	h.mu.RUnlock()

	// Slow path: refresh cache from store.
	rows, err := h.store.List(ctx, now)
	if err != nil {
		h.storeErr.Add(1)
		// Fail-closed: no override.
		return false, Override{}
	}

	h.mu.Lock()
	h.cache = make(map[string]Override, len(rows))
	for _, r := range rows {
		if r.IsActive(now) {
			h.cache[r.ServiceName] = r
		}
	}
	h.fetchedAt = now
	o, ok := h.cache[service]
	h.mu.Unlock()

	if ok {
		h.hits.Add(1)
		return true, o
	}
	h.misses.Add(1)
	return false, Override{}
}

// Stats returns (hits, misses, storeErrors) counters.
func (h *OverrideHandler) Stats() (hits, misses, storeErrors uint64) {
	return h.hits.Load(), h.misses.Load(), h.storeErr.Load()
}

// ─────────────────────────────────────────────────────────────────────
// InMemOverrideStore — test / cycle-30 default implementation
// ─────────────────────────────────────────────────────────────────────

// InMemOverrideStore is an in-memory OverrideStore. Used by tests and
// by the K8s webhook E2E test in cycle 30; production wires the
// cycle-31+ SQL implementation in `contracts/meta/`.
type InMemOverrideStore struct {
	mu   sync.RWMutex
	rows []Override
}

// NewInMemOverrideStore returns an empty in-memory store.
func NewInMemOverrideStore() *InMemOverrideStore {
	return &InMemOverrideStore{}
}

// Grant inserts an override after validation. Replaces any existing
// row with the same ServiceName + GrantedAt (idempotent re-grant).
func (s *InMemOverrideStore) Grant(o Override) error {
	if err := o.Validate(); err != nil {
		return err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	for i, r := range s.rows {
		if r.ServiceName == o.ServiceName && r.GrantedAt.Equal(o.GrantedAt) {
			s.rows[i] = o
			return nil
		}
	}
	s.rows = append(s.rows, o)
	return nil
}

// List returns active overrides (IsActive(now) == true). Expired rows
// are filtered out but NOT deleted from the underlying slice — the
// audit trail must be preserved (the SQL impl will keep history rows
// indefinitely and rely on this filter).
func (s *InMemOverrideStore) List(_ context.Context, now time.Time) ([]Override, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]Override, 0, len(s.rows))
	for _, r := range s.rows {
		if r.IsActive(now) {
			out = append(out, r)
		}
	}
	return out, nil
}

// All returns every row regardless of expiration. Used by SRE audit
// queries and the cycle-30 unit tests.
func (s *InMemOverrideStore) All() []Override {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]Override, len(s.rows))
	copy(out, s.rows)
	return out
}

// OverrideTTL returns the 24h cap as a package constant for callers
// (e.g., admin CLI sets ExpiresAt = GrantedAt + capacity.OverrideTTL()).
func OverrideTTL() time.Duration { return overrideTTL }
