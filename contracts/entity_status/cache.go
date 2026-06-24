package entity_status

import (
	"context"
	"errors"
	"time"
)

// cache.go — L4.E.5 cache contract.
//
// 60s TTL by spec (S10 §12Z). Invalidation is event-driven via MetaWrite
// outbox events on reality_registry (cycle 2) + pii_kek (cycle 3). On cache
// miss, the resolver fans out to the 4-layer cascade above and writes the
// answer back through CacheWriter.

// DefaultTTL is the S10 §12Z 60s cache TTL.
const DefaultTTL = 60 * time.Second

// CacheReader fetches a cached envelope for the entity. The bool indicates
// hit / miss. Miss is NOT an error.
type CacheReader interface {
	Get(ctx context.Context, ref EntityRef) (EntityStatusEnvelope, bool, error)
}

// CacheWriter persists a freshly-resolved envelope. TTL > 0 required.
type CacheWriter interface {
	Set(ctx context.Context, ref EntityRef, env EntityStatusEnvelope, ttl time.Duration) error
}

// CacheInvalidator removes one or more envelopes after a MetaWrite event
// invalidates the underlying reality / pii_kek row. Implementations typically
// use Redis prefix-delete.
type CacheInvalidator interface {
	// InvalidateReality drops every cached envelope for the given reality.
	InvalidateReality(ctx context.Context, realityID string) (int, error)
	// InvalidateEntity drops one specific envelope.
	InvalidateEntity(ctx context.Context, ref EntityRef) error
}

// CachedResolver wraps a Resolver with a CacheReader+Writer.
// Use this in production hot-path code; bare Resolver is for tests / cold
// callers.
type CachedResolver struct {
	Reader   CacheReader
	Writer   CacheWriter
	Resolver *Resolver
	TTL      time.Duration // 0 ⇒ DefaultTTL
}

// GetEntityStatus tries the cache first; on miss runs Resolver.GetEntityStatus
// and write-back-fills.
func (c *CachedResolver) GetEntityStatus(ctx context.Context, ref EntityRef) (EntityStatusEnvelope, error) {
	if c == nil || c.Resolver == nil {
		return EntityStatusEnvelope{}, errors.New("entity_status: CachedResolver requires Resolver")
	}
	if c.Reader != nil {
		env, hit, err := c.Reader.Get(ctx, ref)
		if err != nil {
			return EntityStatusEnvelope{}, err
		}
		if hit {
			return env, nil
		}
	}
	env, err := c.Resolver.GetEntityStatus(ctx, ref)
	if err != nil {
		return env, err
	}
	if c.Writer != nil {
		ttl := c.TTL
		if ttl <= 0 {
			ttl = DefaultTTL
		}
		// Best-effort: cache-write failure does NOT fail the call (the cache
		// is an optimization, not a source of truth).
		_ = c.Writer.Set(ctx, ref, env, ttl)
	}
	return env, nil
}
