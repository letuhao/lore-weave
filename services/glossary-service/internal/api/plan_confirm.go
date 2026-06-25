package api

// Plan/Action kit — the execute_plan confirm + preview effects (spec
// docs/specs/2026-06-25-plan-action-kit.md §4, §9). The token-gated confirmAction
// path decodes the typed Plan carried in the action params and runs it through the
// kit's deterministic executor (loreweave_mcp.Execute) over the glossary op
// registry (plan_ops.go). The single-use jti is already claimed by confirmAction
// BEFORE dispatch here, so this effect is the one-shot write; a partial failure is
// reported in the summary, not retried (the human re-proposes).
//
// Phase 1 is additive-only (§18): the op-set has no destructive ops, so enabledOps
// is nil — there is no per-op confirm toggle yet (that arrives with delete/merge in
// Phase 2). The FE ConfirmCard renders the preview rows unchanged.

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/google/uuid"

	mcp "github.com/loreweave/loreweave_mcp"
)

// effectExecutePlan runs the confirmed plan deterministically and returns the
// executor's {applied, skipped, failed, aborted} summary verbatim (the agent
// reports it without inventing an outcome). Re-validates the plan against the
// CURRENT registry at execute time (§13.5 defense-in-depth): re-stamps Destructive,
// rejects an unknown op, dedupes, and freezes ids — idempotent on an already-valid
// plan. The plan is bound to the token's resource (claims.BookID) so it can never
// execute against a different book than the one the token authorized.
func (s *Server) effectExecutePlan(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var plan mcp.Plan
	if err := json.Unmarshal(claims.Params, &plan); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad plan payload")
		return
	}
	plan.BookID = claims.BookID // bind to the authorized resource
	reg := s.planRegistry()
	if err := reg.ValidatePlan(&plan); err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "the plan is no longer valid — propose again")
		return
	}
	// Additive-only Phase 1 → no enabled destructive ops (§18).
	summary := mcp.Execute(ctx, claims.UserID, plan, nil, reg)
	// 200 even on partial failure / abort: the human confirmed and the executor ran;
	// per-op results (incl. failed/aborted) are in the body for the agent to surface.
	writeJSON(w, http.StatusOK, summary)
}

// previewExecutePlan re-renders the plan card from CURRENT state (§9, S2): one row
// per op with a live new-vs-existing signal where cheap (create_kinds counts which
// kinds already exist; adopt counts new genres/kinds; add_attributes flags a
// missing target kind). Never consumes the token.
func (s *Server) previewExecutePlan(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var plan mcp.Plan
	if err := json.Unmarshal(claims.Params, &plan); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad plan payload")
		return
	}
	plan.BookID = claims.BookID
	reg := s.planRegistry()
	if err := reg.ValidatePlan(&plan); err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "the plan is no longer valid — propose again")
		return
	}
	// Best-effort live kind map for the new-vs-existing signal; on error fall back to
	// an empty map (the preview degrades to "all new" rather than failing the card).
	existingKinds, _ := s.loadKindMap(ctx, plan.BookID)
	rows := make([]previewRow, 0, len(plan.Ops))
	for _, op := range plan.Ops {
		rows = append(rows, s.previewPlanOp(ctx, plan.BookID, op, existingKinds))
	}
	writeJSON(w, http.StatusOK, actionPreview{
		Descriptor:  descExecutePlan,
		Destructive: false,
		Title:       fmt.Sprintf("Execute plan — %d operation(s)", len(plan.Ops)),
		PreviewRows: rows,
	})
}

// previewPlanOp renders one plan op as a preview row, decoding its typed params and
// adding a live current-state note where it is cheap to compute.
func (s *Server) previewPlanOp(ctx context.Context, bookID uuid.UUID, op mcp.Op, existingKinds map[string]uuid.UUID) previewRow {
	switch op.Type {
	case "adopt_genres":
		var p adoptParams
		if err := json.Unmarshal(op.Params, &p); err != nil {
			return previewRow{Label: "adopt", Value: "standards", Note: "scaffold baseline + adopt picks"}
		}
		newGenres, newKinds, err := s.adoptCounts(ctx, bookID, p.Genres, p.Kinds)
		if err != nil {
			return previewRow{Label: "adopt", Value: "standards", Note: "scaffold baseline + adopt picks"}
		}
		return previewRow{
			Label: "adopt", Value: fmt.Sprintf("%d genre(s), %d kind(s) new", newGenres, newKinds),
			Note: "+ universal/unknown baseline (always)",
		}
	case "create_kinds":
		var p createKindsParams
		if err := json.Unmarshal(op.Params, &p); err != nil {
			return previewRow{Label: "create kinds", Value: "?", Note: "unreadable op"}
		}
		newN, existN := 0, 0
		for _, k := range p.Kinds {
			if _, ok := existingKinds[strings.TrimSpace(k.Code)]; ok {
				existN++
			} else {
				newN++
			}
		}
		return previewRow{
			Label: "create kinds", Value: fmt.Sprintf("%d new", newN),
			Note: fmt.Sprintf("%d already exist (skipped)", existN),
		}
	case "add_attributes":
		var p addAttributesParams
		if err := json.Unmarshal(op.Params, &p); err != nil {
			return previewRow{Label: "add attributes", Value: "?", Note: "unreadable op"}
		}
		note := fmt.Sprintf("%d attribute(s) → kind %q", len(p.Attributes), p.KindCode)
		if _, ok := existingKinds[strings.TrimSpace(p.KindCode)]; !ok {
			note = fmt.Sprintf("kind %q not found — this op will fail", p.KindCode)
		}
		return previewRow{Label: "add attributes", Value: p.KindCode, Note: note}
	case "edit_attribute":
		var p editAttributeParams
		if err := json.Unmarshal(op.Params, &p); err != nil {
			return previewRow{Label: "edit attribute", Value: "?", Note: "unreadable op"}
		}
		return previewRow{Label: "edit attribute", Value: p.KindCode + "/" + p.Code, Note: "update fields"}
	default:
		return previewRow{Label: op.Type, Value: op.ID}
	}
}
