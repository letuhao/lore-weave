package prompt

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

// ProviderConfig is the resolved-provider record returned by
// ProviderResolver. Cycle 31 L6.J.1 keeps the surface minimal — the
// foundation does NOT model BYOK credentials (that belongs to
// provider-registry-service); only the fields prompt-assembly +
// routing need.
type ProviderConfig struct {
	// ProviderName — canonical name (e.g., "anthropic", "openai",
	// "byok_local"). Opaque to foundation; the LLM-gateway adapter
	// registry owns the namespace.
	ProviderName string

	// ModelRef — resolved model identifier per CLAUDE.md "No
	// hardcoded model names". Source: user's provider-registry config.
	ModelRef string

	// EndpointURL — provider endpoint base URL. Foundation does NOT
	// dial this; the LLM-gateway adapter uses it.
	EndpointURL string

	// TrainingOnInput — V1 advisory flag (true iff the provider may
	// train on submitted prompts). Consumed by the ConsentGate to
	// enforce BYOK telemetry consent (S09 §12Y.5).
	TrainingOnInput bool

	// FetchedAt — when this config was loaded from
	// provider-registry-service. Used by the cache for TTL eviction.
	FetchedAt time.Time
}

// Validate enforces minimum shape — the resolver MUST NOT return a
// half-populated config (Q-L6H-1).
func (p ProviderConfig) Validate() error {
	if p.ProviderName == "" {
		return errors.New("provider_config: ProviderName empty")
	}
	if p.ModelRef == "" {
		return errors.New("provider_config: ModelRef empty (CLAUDE.md: no hardcoded model names — must come from registry)")
	}
	if p.EndpointURL == "" {
		return errors.New("provider_config: EndpointURL empty")
	}
	return nil
}

// ProviderResolver maps a model identifier to a ProviderConfig. The
// LLM-logic sub-program will wire a concrete impl that calls
// provider-registry-service via the existing HTTP/JSON RPC (per
// Q-L5-4 LOCKED). Foundation V1 ships the interface + a cache wrapper
// + a test/mock impl.
//
// **CLAUDE.md provider gateway invariant:** implementations MUST NOT
// call provider SDKs directly. The whole point of this indirection is
// that provider-registry-service is the single chokepoint for BYOK
// credential resolution; the prompt SDK never sees raw API keys.
type ProviderResolver interface {
	// Resolve looks up the config for a model identifier (model_id +
	// reality_id scope). Returns ErrProviderNotFound for unknown models.
	Resolve(ctx context.Context, modelID string, realityID string) (ProviderConfig, error)
}

// ErrProviderNotFound is returned when the resolver has no config for
// the requested model_id.
var ErrProviderNotFound = errors.New("provider_resolver: provider config not found")

// CachedProviderResolver wraps another ProviderResolver with a
// time-bounded cache. Default TTL = 5 minutes (matches cycle 1 L1.B
// consent.go cache discipline). Per L6.J acceptance criterion: cache
// matches L1.B consent.go 5min TTL (or shorter for cost-sensitive ops).
//
// The cache is keyed on (modelID, realityID) so per-reality BYOK
// configs don't bleed. **No background refresh** — fresh fetch on miss
// only; refresh-ahead is a future optimization for the LLM-gateway
// sub-program.
type CachedProviderResolver struct {
	Inner ProviderResolver
	TTL   time.Duration

	// Now is the clock source — tests override.
	Now func() time.Time

	mu    sync.RWMutex
	cache map[cacheKey]ProviderConfig
}

type cacheKey struct {
	ModelID   string
	RealityID string
}

// DefaultProviderTTL is the recommended TTL — 5 minutes per acceptance
// criterion (matches cycle 1 L1.B consent.go).
const DefaultProviderTTL = 5 * time.Minute

// NewCachedProviderResolver constructs a cache wrapper with TTL.
// When ttl <= 0 the default 5min is applied.
func NewCachedProviderResolver(inner ProviderResolver, ttl time.Duration) *CachedProviderResolver {
	if ttl <= 0 {
		ttl = DefaultProviderTTL
	}
	return &CachedProviderResolver{
		Inner: inner,
		TTL:   ttl,
		Now:   time.Now,
		cache: make(map[cacheKey]ProviderConfig),
	}
}

// Resolve — see ProviderResolver. Cache hit returns the entry iff it
// is still within TTL; miss or expired entry triggers a fresh inner
// resolve.
func (c *CachedProviderResolver) Resolve(ctx context.Context, modelID, realityID string) (ProviderConfig, error) {
	if c == nil || c.Inner == nil {
		return ProviderConfig{}, errors.New("provider_resolver: nil receiver or inner")
	}
	if c.Now == nil {
		c.Now = time.Now
	}
	k := cacheKey{ModelID: modelID, RealityID: realityID}

	c.mu.RLock()
	cfg, ok := c.cache[k]
	c.mu.RUnlock()
	if ok && c.Now().Sub(cfg.FetchedAt) < c.TTL {
		return cfg, nil
	}

	// Cache miss or expired — fetch.
	fresh, err := c.Inner.Resolve(ctx, modelID, realityID)
	if err != nil {
		return ProviderConfig{}, err
	}
	if err := fresh.Validate(); err != nil {
		return ProviderConfig{}, fmt.Errorf("provider_resolver: inner returned invalid config: %w", err)
	}
	fresh.FetchedAt = c.Now()

	c.mu.Lock()
	c.cache[k] = fresh
	c.mu.Unlock()

	return fresh, nil
}

// MockProviderResolver is a test/mock impl. Returns the configured
// entries from a map. Useful in the foundation test suite + for
// downstream services until the real provider-registry RPC client lands.
type MockProviderResolver struct {
	Entries map[string]ProviderConfig
}

// Resolve — see ProviderResolver.
func (m *MockProviderResolver) Resolve(_ context.Context, modelID, _ string) (ProviderConfig, error) {
	if m == nil || m.Entries == nil {
		return ProviderConfig{}, ErrProviderNotFound
	}
	cfg, ok := m.Entries[modelID]
	if !ok {
		return ProviderConfig{}, fmt.Errorf("%w: model=%q", ErrProviderNotFound, modelID)
	}
	return cfg, nil
}
