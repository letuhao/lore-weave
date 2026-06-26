package loreweave_mcp

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// Plan/Action kit — the shared plan-and-execute layer above the confirm-token
// spine (confirm_token.go). A capable planner emits ONE typed Plan; a
// deterministic executor (execute.go) applies it under ONE human confirm. A
// domain service registers an op-set + handlers (Registry); the kit owns the
// envelope, validation, propose/mint (propose.go), and execution control flow.
//
// Design: docs/specs/2026-06-25-plan-action-kit.md (Part II §13–§20 are the
// implementation contract). This file is K0 — the frozen types every other unit
// keys off; do not change a field name here without re-checking execute.go,
// propose.go, planner.go, and the glossary consumer.

const (
	PlanVersion = 1 // envelope version

	// DescriptorExecutePlan is the confirm-token descriptor a plan rides on. It
	// reuses the existing action-token spine (mintActionToken); the consuming
	// service must allow it in its liveDescriptor set.
	DescriptorExecutePlan = "execute_plan"

	// MaxPlanOps bounds token size, execution time, and preview cost (§19). Over
	// the cap is an error at the planner, never a silent truncation.
	MaxPlanOps = 50

	// PlanTokenTTL is the confirm window for a plan — longer than the 10-minute
	// single-op TTL because a multi-op plan takes longer to read (§19, S5).
	PlanTokenTTL = 30 * time.Minute
)

// Plan is the typed, validated artifact the planner emits and the executor runs.
// Single-resource scope: BookID == the confirm token's ResourceID (§10).
type Plan struct {
	Version int       `json:"version"`
	BookID  uuid.UUID `json:"book_id"`
	Goal    string    `json:"goal"`            // NL goal, echoed in the review header
	Ops     []Op      `json:"ops"`             // ids assigned by the kit at validate, frozen in the token (§16)
	Notes   []string  `json:"notes,omitempty"` // planner's unsupported-intent surfacings (§6.4); NOT executed
}

// Op is one operation. Type is domain-registered; Params is validated against the
// OpSpec.ParamSchema/Validate. Destructive is stamped FROM the registry, never
// trusted from planner output (G1). BaseVersion is the optimistic-concurrency
// token for EDIT ops only (§17); create/adopt/delete carry none.
type Op struct {
	ID          string          `json:"id"`
	Type        string          `json:"type"`
	Params      json.RawMessage `json:"params"`
	Rationale   string          `json:"rationale,omitempty"`
	Destructive bool            `json:"destructive"`
	BaseVersion string          `json:"base_version,omitempty"`
}

// Outcome statuses + reason codes (§5 error-class → outcome table). The agent
// reports these verbatim; failures must be surfaced, never buried (G4).
const (
	StatusApplied = "applied"
	StatusSkipped = "skipped"
	StatusFailed  = "failed"

	ReasonAlreadyExists       = "already_exists"        // unique violation → skipped
	ReasonNotConfirmed        = "not_confirmed"         // destructive op not in enabledOps → skipped (G1)
	ReasonTargetGone          = "target_gone"           // not-found / FK → failed
	ReasonChangedSincePlanned = "changed_since_planned" // stale base_version → failed (G2)
	ReasonBadParams           = "bad_params"            // validation → failed (S4)
	ReasonAlreadyDone         = "already_done"          // paid/effect idempotency guard → skipped (G3)
	ReasonInternal            = "internal"              // unexpected → failed + abort the rest
)

// OpOutcome is the per-op result. Detail (on applied) is a COMPACT descriptor
// (e.g. {code,name}), never the full row, to bound summary size (§13).
type OpOutcome struct {
	OpID    string `json:"op_id"`
	Type    string `json:"type"`
	Status  string `json:"status"`
	Reason  string `json:"reason,omitempty"`
	Message string `json:"message,omitempty"`
	Detail  any    `json:"detail,omitempty"`
}

// Summary is the executor's structured report. Aborted is true when an internal
// error stopped the run early (the stack is unhealthy) — the only case where
// remaining ops do not run (§5).
type Summary struct {
	Applied []OpOutcome `json:"applied"`
	Skipped []OpOutcome `json:"skipped"`
	Failed  []OpOutcome `json:"failed"`
	Aborted bool        `json:"aborted"`
}

// Sentinel errors a Handler returns to signal a business outcome; Execute maps
// each to the matching reason (§5). Any OTHER (non-sentinel) error is treated as
// ReasonInternal and aborts the remaining plan.
var (
	ErrUniqueViolation = errors.New("loreweave_mcp: unique violation")       // → already_exists (skip)
	ErrNotFound        = errors.New("loreweave_mcp: target not found")       // → target_gone (fail)
	ErrStaleVersion    = errors.New("loreweave_mcp: stale base_version")     // → changed_since_planned (fail)
	ErrBadParams       = errors.New("loreweave_mcp: invalid params")         // → bad_params (fail)
	ErrAlreadyDone     = errors.New("loreweave_mcp: effect already applied") // → already_done (skip)
)

// OpSpec is what a domain service registers per op type. The kit knows nothing
// domain-specific. Handler is self-transactional (its own DB tx, like
// createKindFromParams) and maps its errors to the sentinels above.
type OpSpec struct {
	Type        string
	Tier        int    // dependency tier: adopt(0) → kinds(1) → attributes(2) → entities(3) → edits(4) → deletes(5)
	Destructive bool   // stamped onto every Op of this type; planner cannot override (G1)
	Idempotent  bool   // MUST be true; NewRegistry panics otherwise (G3)
	ParamSchema []byte // strict JSON Schema for params (S4); used by the planner's validate/repair (§15)

	// IdentityKey yields a stable key for dedupe/conflict detection (§16): two ops
	// with the same (Type, IdentityKey) and identical params collapse; with
	// different params they are a duplicate_conflict.
	IdentityKey func(params json.RawMessage) (string, error)

	// Validate runs structural pre-checks beyond the schema (slug code, non-empty
	// description, …) (S4). nil ⇒ schema-only.
	Validate func(params json.RawMessage) error

	// Handler applies one op. baseVersion is empty for non-edit ops.
	Handler func(ctx context.Context, bookID, userID uuid.UUID, params json.RawMessage, baseVersion string) (detail any, err error)
}

// Registry maps op type → spec.
type Registry map[string]OpSpec

// NewRegistry builds a registry, enforcing the invariants at startup (fail fast):
// every op must be idempotent (G3) and carry a Handler + IdentityKey.
func NewRegistry(specs ...OpSpec) Registry {
	reg := make(Registry, len(specs))
	for _, s := range specs {
		switch {
		case s.Type == "":
			panic("loreweave_mcp: OpSpec.Type is required")
		case !s.Idempotent:
			panic(fmt.Sprintf("loreweave_mcp: op %q must be idempotent (G3) — toggle/increment/append shapes are forbidden", s.Type))
		case s.Handler == nil:
			panic(fmt.Sprintf("loreweave_mcp: op %q needs a Handler", s.Type))
		case s.IdentityKey == nil:
			panic(fmt.Sprintf("loreweave_mcp: op %q needs an IdentityKey", s.Type))
		}
		if _, dup := reg[s.Type]; dup {
			panic(fmt.Sprintf("loreweave_mcp: duplicate op registration %q", s.Type))
		}
		reg[s.Type] = s
	}
	return reg
}

// TokenLedger is the single-use jti store the consuming service already owns
// (glossary's consumed_tokens). The kit stays storage-agnostic. Claim returns
// claimed=true the FIRST time a jti is seen, false on replay (§4).
type TokenLedger interface {
	Claim(ctx context.Context, jti, descriptor string, exp time.Time) (claimed bool, err error)
}

// Plan-validation errors (returned by Registry.ValidatePlan).
var (
	ErrEmptyPlan         = errors.New("loreweave_mcp: plan has no executable ops")
	ErrPlanTooLarge      = errors.New("loreweave_mcp: plan exceeds MaxPlanOps")
	ErrUnknownOpType     = errors.New("loreweave_mcp: unknown op type")
	ErrDuplicateConflict = errors.New("loreweave_mcp: duplicate ops with different params")
)

// ValidatePlan normalizes a planner-produced plan IN PLACE against the registry,
// and is the single gate before mint (§15, §16):
//   - rejects unknown op types and over-cap plans;
//   - runs each op's Validate (slug code, non-empty description, …);
//   - stamps Destructive from the registry (never trusts planner output, G1);
//   - dedupes by (type, IdentityKey): identical params collapse, different params
//     are an ErrDuplicateConflict (the planner contradicted itself);
//   - rejects an empty result (no card for a no-op plan, S3);
//   - assigns frozen ids op-1..N in surviving order (so preview and confirm agree).
//
// On success p.Ops is the normalized, id-stamped list and p.Version is set.
func (reg Registry) ValidatePlan(p *Plan) error {
	if len(p.Ops) > MaxPlanOps {
		return fmt.Errorf("%w: %d > %d", ErrPlanTooLarge, len(p.Ops), MaxPlanOps)
	}
	seen := make(map[string]int, len(p.Ops)) // (type|identity) → index into out
	out := make([]Op, 0, len(p.Ops))
	for _, op := range p.Ops {
		spec, ok := reg[op.Type]
		if !ok {
			return fmt.Errorf("%w: %q", ErrUnknownOpType, op.Type)
		}
		if spec.Validate != nil {
			if err := spec.Validate(op.Params); err != nil {
				return fmt.Errorf("%w: op %s: %v", ErrBadParams, op.Type, err)
			}
		}
		op.Destructive = spec.Destructive // authoritative (G1)
		idk, err := spec.IdentityKey(op.Params)
		if err != nil {
			return fmt.Errorf("%w: op %s identity: %v", ErrBadParams, op.Type, err)
		}
		key := op.Type + "|" + idk
		if idx, dup := seen[key]; dup {
			if !bytes.Equal(canonicalJSON(out[idx].Params), canonicalJSON(op.Params)) {
				return fmt.Errorf("%w: %s", ErrDuplicateConflict, key)
			}
			continue // identical → collapse
		}
		seen[key] = len(out)
		out = append(out, op)
	}
	if len(out) == 0 {
		return ErrEmptyPlan
	}
	for i := range out {
		out[i].ID = fmt.Sprintf("op-%d", i+1) // frozen ids (§16)
	}
	p.Ops = out
	if p.Version == 0 {
		p.Version = PlanVersion
	}
	return nil
}

// canonicalJSON re-marshals through a generic value so key order / whitespace do
// not produce false duplicate-conflicts. Falls back to the raw bytes on parse
// failure (a malformed op is caught earlier by Validate).
func canonicalJSON(raw json.RawMessage) []byte {
	var v any
	if err := json.Unmarshal(raw, &v); err != nil {
		return raw
	}
	b, err := json.Marshal(v)
	if err != nil {
		return raw
	}
	return b
}
