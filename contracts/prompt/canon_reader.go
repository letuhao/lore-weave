package prompt

// canon_reader.go — L5.E.3 cache-aside reader for per-reality canon.
//
// RAID cycle 25 DPS 1. Composes Cache (hot) + Reader (cold per-reality
// canon_projection SELECT, cycle-23 L5.D) into a single read-path that
// the cycle-21 [WORLD_CANON] prompt builder calls.
//
// # Cache-aside semantics (Q-L5-1 read flow)
//
//   1. Cache.Get(realityID, bookID, attributePath)
//      a. If hit, return — emit IncHit metric.
//      b. If ErrAttributeNotCacheable, skip to step 3 (NEVER cache).
//      c. If ErrCacheMiss, continue.
//   2. Reader.ReadCanon(realityID, bookID, attributePath) — production
//      binds to a sqlx SELECT on canon_projection in the reality's DB
//      via cycle-5 pgbouncer pool. Tests inject FakeReader.
//   3. On Reader hit, Set in cache (only if cacheable).
//   4. Return CanonValue.
//
// Per L5.E.4 acceptance: cache hit < 1ms; miss to projection < 10ms;
// miss to RPC < 50ms P99. The cache layer here makes step 1 fast; the
// projection SELECT speed is owned by cycle-23 L5.D indexes.

import (
	"context"
	"errors"
	"fmt"

	"github.com/google/uuid"
)

// CanonValue is the return shape from CanonReader.Read. Mirrors the
// cacheable portion of a canon_projection row.
type CanonValue struct {
	CanonEntryID  uuid.UUID
	RealityID     uuid.UUID
	BookID        uuid.UUID
	AttributePath string
	Value         []byte // canonical JSON bytes
	CanonLayer    string // Q-L5-3 enum
	// FromCache is true if this value was served from the Cache;
	// false if served from the cold-path Reader. Useful for tests
	// and hit-rate monitoring.
	FromCache bool
}

// ErrCanonNotFound is returned by CanonReader.Read (and from cold-path
// Reader.ReadCanon implementations) when no canon_projection row exists
// for (realityID, bookID, attributePath). Distinct from ErrCacheMiss
// (which signals "ask the cold path"); ErrCanonNotFound terminates the
// read with no value.
var ErrCanonNotFound = errors.New("canon_reader: canon not found")

// Reader is the cold-path canon reader. Production wires this to a sqlx
// SELECT on per-reality canon_projection (cycle-23 L5.D); tests inject
// FakeReader.
type Reader interface {
	ReadCanon(ctx context.Context, realityID, bookID uuid.UUID, attributePath string) (CanonValue, error)
}

// CanonReader composes Cache + Reader into the cache-aside hot read path.
type CanonReader struct {
	cache  *Cache
	reader Reader
}

// CanonReaderConfig bundles dependencies.
type CanonReaderConfig struct {
	Cache  *Cache
	Reader Reader
}

// NewCanonReader constructs a CanonReader. Both deps required.
func NewCanonReader(cfg CanonReaderConfig) (*CanonReader, error) {
	if cfg.Cache == nil {
		return nil, errors.New("canon_reader: Cache nil")
	}
	if cfg.Reader == nil {
		return nil, errors.New("canon_reader: Reader nil")
	}
	return &CanonReader{cache: cfg.Cache, reader: cfg.Reader}, nil
}

// Read implements the Q-L5-1 cache-aside flow described in the file
// header. On cache miss, populates the cache from the Reader result.
//
// Returns ErrCanonNotFound if the cold-path Reader has no row.
func (r *CanonReader) Read(ctx context.Context, realityID, bookID uuid.UUID, attributePath string) (CanonValue, error) {
	// Step 1 — cache lookup (skipped for non-cacheable paths).
	if IsAttributeCacheable(attributePath) {
		entry, err := r.cache.Get(ctx, realityID, bookID, attributePath)
		switch {
		case err == nil:
			return CanonValue{
				CanonEntryID:  entry.CanonEntryID,
				RealityID:     entry.RealityID,
				BookID:        entry.BookID,
				AttributePath: entry.AttributePath,
				Value:         entry.Value,
				CanonLayer:    entry.CanonLayer,
				FromCache:     true,
			}, nil
		case errors.Is(err, ErrCacheMiss):
			// fall through to cold path
		case errors.Is(err, ErrAttributeNotCacheable):
			// unreachable (we IsAttributeCacheable-gated), but be
			// defensive: fall through.
		default:
			// Cache backend error — degrade to cold path. We do NOT
			// fail the whole read on cache errors (availability over
			// correctness for the cache layer; the cold path is the
			// SSOT).
			// fall through
		}
	}

	// Step 2 — cold path.
	val, err := r.reader.ReadCanon(ctx, realityID, bookID, attributePath)
	if err != nil {
		return CanonValue{}, err
	}

	// Step 3 — populate cache (best-effort; never fails the read).
	if IsAttributeCacheable(attributePath) {
		entry := CacheEntry{
			RealityID:     val.RealityID,
			CanonEntryID:  val.CanonEntryID,
			BookID:        val.BookID,
			AttributePath: val.AttributePath,
			Value:         val.Value,
			CanonLayer:    val.CanonLayer,
		}
		_ = r.cache.Set(ctx, entry) // intentionally ignored
	}

	val.FromCache = false
	return val, nil
}

// Invalidate is a convenience pass-through for Cache.Invalidate. Lets
// canon_writer call CanonReader.Invalidate without holding a separate
// Cache handle. Returns the count of deleted keys.
func (r *CanonReader) Invalidate(ctx context.Context, realityID, canonEntryID uuid.UUID) (int, error) {
	return r.cache.Invalidate(ctx, realityID, canonEntryID)
}

// ─────────────────────────────────────────────────────────────────────────
// Guardrail integration interface (Q-L5-5).
// ─────────────────────────────────────────────────────────────────────────

// CanonGuardrail is the L5.I.3 runtime canon-guardrail interface
// (Q-L5-5). Roleplay-service / world-service call this BEFORE writing a
// proposed L3 event to reject any write that conflicts with L1_axiom
// canon for the same (book_id, attribute_path).
//
// Cycle 25 ships ONLY the INTERFACE — the implementation
// (`crates/contracts-prompt/canon_guardrail.rs` per L5.I.3) lands in a
// downstream cycle. Cycle 25's RPC contract (L5.F) wires this interface
// into the canon-write endpoint so the guardrail is the FIRST gate the
// request hits.
//
// # Semantics
//
//   - Returns nil if the proposed write does NOT conflict with any L1
//     canon for the same (book_id, attribute_path).
//   - Returns a non-nil ViolationError describing the conflict
//     (which axiom is violated, what the axiom value is, what the
//     proposed value is). The caller MUST reject the write and surface
//     the error to the user.
//   - V1 implementation (cycle L5.I) is synchronous + uses the
//     CanonReader.Read to fetch the L1 axiom and compares. V2+ may
//     batch / async / parallelize.
//
// # NoOpGuardrail is the default impl used by the L5.F.5 round-trip
// tests in cycle 25. Production binds the real impl from
// crates/contracts-prompt/canon_guardrail.rs (Q-L5-5 downstream).
type CanonGuardrail interface {
	// CheckProposedWrite returns nil if the proposed write is allowed,
	// or a *GuardrailViolation describing the L1 conflict.
	CheckProposedWrite(ctx context.Context, proposal GuardrailProposal) error
}

// GuardrailProposal is the input to CanonGuardrail.CheckProposedWrite.
// Carries enough info for the guardrail to look up the corresponding L1
// axiom and compare.
type GuardrailProposal struct {
	RealityID     uuid.UUID
	BookID        uuid.UUID
	AttributePath string
	// ProposedValue is the canonical JSON the caller wants to write.
	ProposedValue []byte
	// SourceEventType is the wire event_type that triggered the proposal
	// (e.g. "l3.event.recorded"). Used by the guardrail for audit
	// classification.
	SourceEventType string
}

// GuardrailViolation is returned (as the error) when a proposed write
// conflicts with L1 axiomatic canon.
type GuardrailViolation struct {
	// Axiom is the canon row that was violated. Carries the canon
	// value the caller's proposal contradicts.
	Axiom CanonValue
	// ProposedValue is the conflicting value the caller proposed.
	ProposedValue []byte
	// Reason is a human-readable description of the conflict.
	Reason string
}

// Error implements error.
func (v *GuardrailViolation) Error() string {
	return fmt.Sprintf("canon_guardrail: L1 axiom violated for %s.%s (reason=%s)",
		v.Axiom.BookID, v.Axiom.AttributePath, v.Reason)
}

// NoOpGuardrail is the cycle-25 default impl: always allows. The real
// impl (L5.I.3, downstream cycle) replaces this binding at production
// wiring time. Useful for cycle-25 RPC round-trip tests that verify
// the integration point WITHOUT requiring L5.I to be done.
type NoOpGuardrail struct{}

// CheckProposedWrite implements CanonGuardrail.
func (NoOpGuardrail) CheckProposedWrite(context.Context, GuardrailProposal) error { return nil }

// StubRejectGuardrail always returns a GuardrailViolation — used by
// tests that need to assert the rejection path is wired correctly.
type StubRejectGuardrail struct {
	// Reason is the message embedded in the returned violation.
	Reason string
}

// CheckProposedWrite implements CanonGuardrail.
func (s StubRejectGuardrail) CheckProposedWrite(_ context.Context, p GuardrailProposal) error {
	return &GuardrailViolation{
		Axiom: CanonValue{
			BookID:        p.BookID,
			AttributePath: p.AttributePath,
			CanonLayer:    "L1_axiom",
		},
		ProposedValue: p.ProposedValue,
		Reason:        s.Reason,
	}
}
