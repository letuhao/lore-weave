package loreweave_mcp

import (
	"context"
	"errors"
	"sort"

	"github.com/google/uuid"
)

// Execute is the deterministic plan executor (§5). Pure code — no LLM, no agent.
// It sorts the plan's ops into dependency tiers, applies each op's handler, and
// maps the handler's sentinel error (or success) to a per-op OpOutcome by the §5
// error-class → outcome table. Only an unexpected (non-sentinel) error aborts the
// remaining plan; every business outcome is isolated to its op (S1).
//
// The plan is never mutated: the tier sort runs on a copy of p.Ops. enabledOps
// is the set of destructive op ids the user confirmed (G1); a nil map means none
// enabled, so every destructive op is skipped not_confirmed.
//
// Design: docs/specs/2026-06-25-plan-action-kit.md §5 (the class table is the
// contract) and §13.
func Execute(ctx context.Context, userID uuid.UUID, p Plan, enabledOps map[string]bool, reg Registry) Summary {
	// Non-nil empty slices so the JSON summary renders [] not null (§5/G4).
	summary := Summary{
		Applied: []OpOutcome{},
		Skipped: []OpOutcome{},
		Failed:  []OpOutcome{},
	}

	// Stable-sort a COPY by registered tier; original order is preserved within a
	// tier (§16: execution order is Tier then id, ids do not change under the sort).
	ops := make([]Op, len(p.Ops))
	copy(ops, p.Ops)
	sort.SliceStable(ops, func(i, j int) bool {
		return reg[ops[i].Type].Tier < reg[ops[j].Type].Tier
	})

	for _, op := range ops {
		outcome := OpOutcome{OpID: op.ID, Type: op.Type}

		spec, ok := reg[op.Type]
		if !ok {
			// Should not happen post-ValidatePlan (unknown types are rejected there);
			// be defensive and treat as an internal/abort condition rather than panic.
			outcome.Status = StatusFailed
			outcome.Reason = ReasonInternal
			outcome.Message = ErrUnknownOpType.Error() + ": " + op.Type
			summary.Failed = append(summary.Failed, outcome)
			summary.Aborted = true
			return summary
		}

		// G1 — a destructive op runs only if the user enabled it at confirm time;
		// otherwise it is skipped not_confirmed (a plan can never silently delete).
		if spec.Destructive && !enabledOps[op.ID] {
			outcome.Status = StatusSkipped
			outcome.Reason = ReasonNotConfirmed
			summary.Skipped = append(summary.Skipped, outcome)
			continue
		}

		detail, err := spec.Handler(ctx, p.BookID, userID, op.Params, op.BaseVersion)
		switch {
		case err == nil:
			outcome.Status = StatusApplied
			outcome.Detail = detail
			summary.Applied = append(summary.Applied, outcome)

		case errors.Is(err, ErrUniqueViolation):
			outcome.Status = StatusSkipped
			outcome.Reason = ReasonAlreadyExists
			summary.Skipped = append(summary.Skipped, outcome)

		case errors.Is(err, ErrAlreadyDone):
			outcome.Status = StatusSkipped
			outcome.Reason = ReasonAlreadyDone
			summary.Skipped = append(summary.Skipped, outcome)

		case errors.Is(err, ErrNotFound):
			outcome.Status = StatusFailed
			outcome.Reason = ReasonTargetGone
			outcome.Message = err.Error()
			summary.Failed = append(summary.Failed, outcome)

		case errors.Is(err, ErrStaleVersion):
			outcome.Status = StatusFailed
			outcome.Reason = ReasonChangedSincePlanned
			outcome.Message = err.Error()
			summary.Failed = append(summary.Failed, outcome)

		case errors.Is(err, ErrBadParams):
			outcome.Status = StatusFailed
			outcome.Reason = ReasonBadParams
			outcome.Message = err.Error()
			summary.Failed = append(summary.Failed, outcome)

		default:
			// Any other error is an unexpected/internal failure: the stack is
			// unhealthy. Record it, abort, and return the partial summary — the
			// remaining ops do NOT run (§5).
			outcome.Status = StatusFailed
			outcome.Reason = ReasonInternal
			outcome.Message = err.Error()
			summary.Failed = append(summary.Failed, outcome)
			summary.Aborted = true
			return summary
		}
	}

	return summary
}
