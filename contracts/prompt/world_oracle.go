package prompt

import "context"

// WorldFact is the unit returned by the World Oracle — an opaque
// {key, value} pair tagged with a canon layer (R02 §12B). Foundation
// V1 carries only the shape; the LLM-logic sub-program defines the
// concrete keys and the deterministic fact resolution semantics.
type WorldFact struct {
	// Key — opaque fact identifier (e.g., "current_year", "active_war").
	// Foundation does not enumerate the namespace; LLM-logic owns it.
	Key string

	// Value — fact value as wire-form string. Multi-byte safe.
	Value string

	// CanonLayer — R02 §12B layer (L1=axiomatic, L2=story-canon, etc.).
	// Foundation does not enforce values; lint lives in canon_guardrail.
	CanonLayer string
}

// WorldOracle resolves deterministic facts the LLM should not be
// asked to recall (e.g., "what year is it in this reality"). Cycle 31
// L6.L.2 ships the trait + a no-op default per Q-L6L-1 (LOCKED).
//
// **Why this is a stub V1:** the real World Oracle requires (a) a
// per-reality fact store, (b) a query DSL that respects S2/S3
// visibility filters, (c) a cache to keep prompt-assembly hot path
// fast. All three live in the LLM-logic sub-program. Foundation V1
// ships an interface so consumers can wire the dep early.
type WorldOracle interface {
	// LookupFacts returns the facts matching the given keys (or all
	// available facts if keys is empty). Empty result is a valid
	// answer (the V1 stub always returns empty).
	LookupFacts(ctx context.Context, realityID string, keys []string) ([]WorldFact, error)
}

// NoopWorldOracle is the V1 default per Q-L6L-1. Returns an empty
// fact list for every call. The LLM-logic sub-program will swap this
// for a real per-reality oracle.
type NoopWorldOracle struct{}

// LookupFacts — see WorldOracle. V1: always returns an empty slice.
func (NoopWorldOracle) LookupFacts(_ context.Context, _ string, _ []string) ([]WorldFact, error) {
	return nil, nil
}
