package entity_status

import (
	"context"
	"errors"
	"fmt"
	"time"
)

// EntityRef identifies one game entity for status lookups. Aggregate-type is
// REQUIRED so the resolver knows which projection table to consult.
// reality_id is REQUIRED so the resolver can answer reality-level gates
// (dropped / archived) without an additional lookup.
type EntityRef struct {
	// EntityID is the aggregate's primary key (UUID string).
	EntityID string

	// AggregateType is one of {pc, npc, region, world_kv, session} — matches
	// the 5 per-aggregate projection skeletons shipped cycle 13.
	AggregateType string

	// RealityID is the home reality. Required: a missing reality_id forces
	// the resolver into pessimistic-fail mode (returns StateDropped to be
	// safe).
	RealityID string
}

// Validate fail-fast on missing required fields.
func (r EntityRef) Validate() error {
	if r.EntityID == "" {
		return errors.New("entity_status: entity_id empty")
	}
	if r.AggregateType == "" {
		return errors.New("entity_status: aggregate_type empty")
	}
	if r.RealityID == "" {
		return errors.New("entity_status: reality_id empty")
	}
	return nil
}

// EntityStatusEnvelope is the resolver's return type. Versioned so future
// V2 changes can ship without breaking V1 callers.
//
// EnvelopeVersion is the wire format version of THIS struct (currently 1).
type EntityStatusEnvelope struct {
	// EnvelopeVersion = 1 for this cycle.
	EnvelopeVersion int `json:"envelope_version"`

	// Ref echoes the input for forensic correlation.
	Ref EntityRef `json:"ref"`

	// State is the resolved (compound-collapsed) GoneState.
	State GoneState `json:"state"`

	// SourceLayer records WHICH resolver layer answered. One of:
	// "pii_kek" | "reality_registry" | "reality_ancestry" | "projections" |
	// "default_active". Used by SRE to debug surprises.
	SourceLayer string `json:"source_layer"`

	// AggregateVersion carries the Q-L3-4 projection version when the
	// answer came from the projections layer. 0 when not applicable.
	AggregateVersion uint64 `json:"aggregate_version"`

	// ResolvedAt is when the resolver returned (wall clock).
	ResolvedAt time.Time `json:"resolved_at"`
}

// LookupResult is what one resolver layer returns. A layer that has no
// opinion sets `Has` to false and the resolver moves on to the next layer.
type LookupResult struct {
	Has              bool
	State            GoneState
	AggregateVersion uint64
}

// PIIKekReader answers "is this user PII crypto-shredded?" using pii_kek
// (cycle 3 L1.A-2). Production wires the contracts/meta KMS client; tests
// inject a fake.
type PIIKekReader interface {
	// LookupByEntity returns LookupResult{Has:true, State: user_erased}
	// when the entity's user has been erased. Most non-PC entities have no
	// PII link and the reader returns Has=false.
	LookupByEntity(ctx context.Context, ref EntityRef) (LookupResult, error)
}

// RealityRegistryReader answers reality-level questions (dropped / archived /
// frozen). Backed by the cycle 2 reality_registry table.
type RealityRegistryReader interface {
	LookupByReality(ctx context.Context, realityID string) (LookupResult, error)
}

// RealityAncestryReader answers cross-reality migration questions. Backed
// by reality_ancestry (cycle 5+ table).
type RealityAncestryReader interface {
	LookupByEntity(ctx context.Context, ref EntityRef) (LookupResult, error)
}

// ProjectionReader is the LAST-resort layer that loads the entity's actual
// projection row. Implementations reuse the cycle-12 load_aggregate pattern
// (NOT raw SQL) so projection-version metadata flows through to the envelope.
//
// Returning Has=false here means "no row in projections" — the resolver
// promotes this to StateDropped (entity never existed or was hard-deleted).
type ProjectionReader interface {
	LookupByEntity(ctx context.Context, ref EntityRef) (LookupResult, error)
}

// Resolver orchestrates the 4-layer cascade. Always-runs each layer in
// order, short-circuits on the first authoritative answer, otherwise falls
// back to projections.
type Resolver struct {
	// PIIKek may be nil — entities without PII (regions, world_kv) skip this
	// layer.
	PIIKek            PIIKekReader
	RealityRegistry   RealityRegistryReader
	RealityAncestry   RealityAncestryReader
	Projections       ProjectionReader
	// Now is injected so tests can pin ResolvedAt.
	Now func() time.Time
}

// DefaultResolver builds a Resolver with time.Now and the supplied readers.
// PIIKek + RealityAncestry are optional (pass nil to skip).
func DefaultResolver(
	piiKek PIIKekReader,
	realityRegistry RealityRegistryReader,
	realityAncestry RealityAncestryReader,
	projections ProjectionReader,
) *Resolver {
	return &Resolver{
		PIIKek:          piiKek,
		RealityRegistry: realityRegistry,
		RealityAncestry: realityAncestry,
		Projections:     projections,
		Now:             time.Now,
	}
}

// GetEntityStatus runs the 4-layer cascade and returns the envelope.
//
// Cascade:
//  1. PIIKek          → if user_erased, return immediately.
//  2. RealityRegistry → if reality dropped, return dropped (highest precedence).
//  3. RealityAncestry → if entity severed or archived by cross-reality move.
//  4. Projections     → straight load_aggregate; missing row promotes to dropped.
//
// Compound precedence is applied only when multiple layers signal in the
// same call (rare; usually one layer wins early). When the entity isn't
// even found in projections, we return StateDropped — better to be wrong
// pessimistically (caller treats as gone) than optimistically (caller
// shows stale data).
func (r *Resolver) GetEntityStatus(ctx context.Context, ref EntityRef) (EntityStatusEnvelope, error) {
	if err := ref.Validate(); err != nil {
		return EntityStatusEnvelope{}, err
	}
	if r.RealityRegistry == nil || r.Projections == nil {
		return EntityStatusEnvelope{}, errors.New("entity_status: RealityRegistry + Projections are mandatory")
	}

	now := r.now()

	// Layer 1: PII KEK (skip if not wired or aggregate type has no PII).
	if r.PIIKek != nil {
		res, err := r.PIIKek.LookupByEntity(ctx, ref)
		if err != nil {
			return EntityStatusEnvelope{}, fmt.Errorf("pii_kek lookup: %w", err)
		}
		if res.Has && res.State == StateUserErased {
			return EntityStatusEnvelope{
				EnvelopeVersion: 1,
				Ref:             ref,
				State:           StateUserErased,
				SourceLayer:     "pii_kek",
				ResolvedAt:      now,
			}, nil
		}
	}

	// Layer 2: reality registry (gives StateDropped / StateArchived for the whole reality).
	reg, err := r.RealityRegistry.LookupByReality(ctx, ref.RealityID)
	if err != nil {
		return EntityStatusEnvelope{}, fmt.Errorf("reality_registry lookup: %w", err)
	}
	if reg.Has && reg.State == StateDropped {
		return EntityStatusEnvelope{
			EnvelopeVersion: 1,
			Ref:             ref,
			State:           StateDropped,
			SourceLayer:     "reality_registry",
			ResolvedAt:      now,
		}, nil
	}

	// Layer 3: reality ancestry (severed / archived via cross-reality move).
	if r.RealityAncestry != nil {
		anc, err := r.RealityAncestry.LookupByEntity(ctx, ref)
		if err != nil {
			return EntityStatusEnvelope{}, fmt.Errorf("reality_ancestry lookup: %w", err)
		}
		if anc.Has {
			// Compound with reality layer (e.g., archived reality + severed entity → archived).
			composite := Reduce(reg.State, anc.State)
			source := "reality_ancestry"
			if composite == reg.State && reg.Has {
				source = "reality_registry"
			}
			return EntityStatusEnvelope{
				EnvelopeVersion: 1,
				Ref:             ref,
				State:           composite,
				SourceLayer:     source,
				ResolvedAt:      now,
			}, nil
		}
	}

	// Layer 4: projections (last resort; uses cycle-12 load_aggregate pattern).
	proj, err := r.Projections.LookupByEntity(ctx, ref)
	if err != nil {
		return EntityStatusEnvelope{}, fmt.Errorf("projections lookup: %w", err)
	}
	if !proj.Has {
		// No projection row + reality is healthy → entity never existed or was hard-deleted.
		return EntityStatusEnvelope{
			EnvelopeVersion: 1,
			Ref:             ref,
			State:           StateDropped,
			SourceLayer:     "projections",
			ResolvedAt:      now,
		}, nil
	}

	// Combine projection state with reality-layer state (reality might be
	// archived but projection still shows active).
	composite := Reduce(reg.State, proj.State)
	source := "projections"
	if composite != proj.State && reg.Has {
		source = "reality_registry"
	}
	return EntityStatusEnvelope{
		EnvelopeVersion:  1,
		Ref:              ref,
		State:            composite,
		SourceLayer:      source,
		AggregateVersion: proj.AggregateVersion,
		ResolvedAt:       now,
	}, nil
}

func (r *Resolver) now() time.Time {
	if r.Now != nil {
		return r.Now()
	}
	return time.Now()
}
