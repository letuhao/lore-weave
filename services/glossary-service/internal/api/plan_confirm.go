package api

// Plan/Action kit — the execute_plan confirm + preview effects (spec
// docs/specs/2026-06-25-plan-action-kit.md §4, §9). The token-gated confirmAction
// path decodes the typed Plan carried in the action params and runs it through the
// kit's deterministic executor (loreweave_mcp.Execute) over the glossary op
// registry (plan_ops.go). The single-use jti is already claimed by confirmAction
// BEFORE dispatch here, so this effect is the one-shot write; a partial failure is
// reported in the summary, not retried (the human re-proposes).
//
// Phase 2 slice 1 adds destructive deletes (delete_genre/kind/attribute): the confirm
// body now carries enabled_ops, and effectExecutePlan threads that set into Execute so
// a destructive op runs ONLY when the human enabled its op-id (G1). Additive ops are
// unaffected (they ignore enabled_ops).

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
func (s *Server) effectExecutePlan(w http.ResponseWriter, ctx context.Context, claims actionClaims, enabledOps []string) {
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
	// Per-op destructive opt-in (§4 G1): each enabled id must name an op IN this plan
	// (an unknown id is a stale/garbage toggle → 422, re-propose). Enabling a
	// non-destructive op is harmless (Execute only consults the set for destructive
	// ops), so we reject only unknown ids, not non-destructive ones.
	planOps := make(map[string]bool, len(plan.Ops))
	for _, op := range plan.Ops {
		planOps[op.ID] = true
	}
	enabled := make(map[string]bool, len(enabledOps))
	for _, id := range enabledOps {
		if !planOps[id] {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "bad_enabled_op: "+id+" is not in this plan — propose again")
			return
		}
		enabled[id] = true
	}
	summary := mcp.Execute(ctx, claims.UserID, plan, enabled, reg)
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
	// create_kinds inserts by LITERAL book_kind code (alias-folded existingKinds
	// would over-count "already exist" → the count wouldn't match execute_plan).
	bookKindCodes, _ := s.loadBookKindCodes(ctx, plan.BookID)
	rows := make([]previewRow, 0, len(plan.Ops))
	anyDestructive := false
	for _, op := range plan.Ops {
		row := s.previewPlanOp(ctx, plan.BookID, op, existingKinds, bookKindCodes)
		// op.Destructive is authoritative here — ValidatePlan above re-stamped it from
		// the registry (a hallucinated `destructive:false` on a delete cannot survive).
		row.OpID = op.ID
		row.Destructive = op.Destructive
		anyDestructive = anyDestructive || op.Destructive
		rows = append(rows, row)
	}
	// Surface the planner's notes (things it could NOT express as an op) on the card too —
	// the FE planner view renders rows whose label is "note" as a trailing notes block.
	// Mirrors planPreviewRows (the mint path); previously only ops were previewed.
	for _, n := range plan.Notes {
		rows = append(rows, previewRow{Label: "note", Value: n})
	}
	writeJSON(w, http.StatusOK, actionPreview{
		Descriptor:  descExecutePlan,
		Destructive: anyDestructive,
		Title:       fmt.Sprintf("Execute plan — %d operation(s)", len(plan.Ops)),
		PreviewRows: rows,
	})
}

// previewPlanOp renders one plan op as a preview row, decoding its typed params and
// adding a live current-state note where it is cheap to compute.
func (s *Server) previewPlanOp(ctx context.Context, bookID uuid.UUID, op mcp.Op, existingKinds map[string]uuid.UUID, bookKindCodes map[string]struct{}) previewRow {
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
			Label: "Set up your world", Value: fmt.Sprintf("%d genre(s), %d lore categories", newGenres, newKinds),
			Note: "plus the always-on baseline",
		}
	case "create_kinds":
		var p createKindsParams
		if err := json.Unmarshal(op.Params, &p); err != nil {
			return previewRow{Label: "create kinds", Value: "?", Note: "unreadable op"}
		}
		// Count against LITERAL book_kind codes (what create_kinds inserts), NOT the
		// alias-folded existingKinds — else an alias of an adopted kind reads as
		// "already exist" while execute_plan actually creates it (count drift).
		newN, existN := 0, 0
		for _, k := range p.Kinds {
			if _, ok := bookKindCodes[strings.TrimSpace(k.Code)]; ok {
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
	case "delete_genre":
		var p deleteGenreParams
		if err := json.Unmarshal(op.Params, &p); err != nil {
			return previewRow{Label: "delete genre", Value: "?", Note: "unreadable op"}
		}
		attrs, links, ok := s.genreCascadeCounts(ctx, bookID, strings.TrimSpace(p.GenreCode))
		if !ok {
			return previewRow{Label: "delete genre", Value: p.GenreCode, Note: "not found — this op will be skipped"}
		}
		return previewRow{Label: "delete genre", Value: p.GenreCode,
			Note: fmt.Sprintf("deprecates the genre + %d attribute(s), %d kind link(s) (cascade)", attrs, links)}
	case "delete_kind":
		var p deleteKindParams
		if err := json.Unmarshal(op.Params, &p); err != nil {
			return previewRow{Label: "delete kind", Value: "?", Note: "unreadable op"}
		}
		attrs, ok := s.kindCascadeCounts(ctx, bookID, strings.TrimSpace(p.KindCode))
		if !ok {
			return previewRow{Label: "delete kind", Value: p.KindCode, Note: "not found — this op will be skipped"}
		}
		return previewRow{Label: "delete kind", Value: p.KindCode,
			Note: fmt.Sprintf("deprecates the kind + %d attribute(s) (cascade)", attrs)}
	case "delete_attribute":
		var p deleteAttributeParams
		if err := json.Unmarshal(op.Params, &p); err != nil {
			return previewRow{Label: "delete attribute", Value: "?", Note: "unreadable op"}
		}
		return previewRow{Label: "delete attribute", Value: p.KindCode + "/" + p.Code, Note: "deprecates this attribute"}
	case "merge_candidate":
		return s.previewMergeCandidateOp(ctx, bookID, op)
	case "dismiss_candidate":
		var p dismissCandidateParams
		if err := json.Unmarshal(op.Params, &p); err != nil {
			return previewRow{Label: "dismiss", Value: "?", Note: "unreadable op"}
		}
		candID, perr := uuid.Parse(strings.TrimSpace(p.CandidateID))
		if perr != nil {
			return previewRow{Label: "dismiss", Value: p.CandidateID, Note: "invalid candidate id"}
		}
		members, _, status, found, _ := s.loadCandidateForMerge(ctx, bookID, candID)
		if !found || status != "proposed" {
			return previewRow{Label: "dismiss", Value: p.CandidateID, Note: "already resolved — will be skipped"}
		}
		names := make([]string, 0, len(members))
		for _, m := range members {
			n, _ := entityNameAndAliases(ctx, s.pool, m)
			if n == "" {
				n = m.String()
			}
			names = append(names, n)
		}
		return previewRow{Label: "dismiss (not duplicates)", Value: strings.Join(names, ", "), Note: "keeps them separate; the suggestion is rejected (no entity changed)"}
	default:
		return previewRow{Label: op.Type, Value: op.ID}
	}
}

// previewMergeCandidateOp resolves a merge_candidate op to its winner-kept + losers-
// merged-away names so the human verifies the destructive merge before enabling it.
func (s *Server) previewMergeCandidateOp(ctx context.Context, bookID uuid.UUID, op mcp.Op) previewRow {
	var p mergeCandidateParams
	if err := json.Unmarshal(op.Params, &p); err != nil {
		return previewRow{Label: "merge", Value: "?", Note: "unreadable op"}
	}
	candID, perr := uuid.Parse(strings.TrimSpace(p.CandidateID))
	if perr != nil {
		return previewRow{Label: "merge", Value: p.CandidateID, Note: "invalid candidate id"}
	}
	members, suggested, status, found, _ := s.loadCandidateForMerge(ctx, bookID, candID)
	if !found || status != "proposed" {
		return previewRow{Label: "merge", Value: p.CandidateID, Note: "already resolved — will be skipped"}
	}
	winner, werr := resolveMergeWinner(members, suggested, strings.TrimSpace(p.WinnerID))
	if werr != nil {
		return previewRow{Label: "merge", Value: p.CandidateID, Note: "no winner — will fail unless winner_id is supplied"}
	}
	winnerName, _ := entityNameAndAliases(ctx, s.pool, winner)
	if winnerName == "" {
		winnerName = winner.String()
	}
	losers := make([]string, 0, len(members)-1)
	for _, m := range members {
		if m != winner {
			n, _ := entityNameAndAliases(ctx, s.pool, m)
			if n == "" {
				n = m.String()
			}
			losers = append(losers, n)
		}
	}
	return previewRow{
		Label: "merge → keep " + winnerName,
		Value: "merge away: " + strings.Join(losers, ", "),
		Note:  "soft-deletes the losers (names folded into the winner); reversible/journaled",
	}
}

// genreCascadeCounts returns the live attribute + kind-link counts a delete_genre would
// deprecate/drop, for the preview blast-radius note. ok=false when the genre code does
// not resolve to a LIVE genre (the op would be a no-op skip). Best-effort: a query
// error degrades to (0,0,true) rather than failing the card.
func (s *Server) genreCascadeCounts(ctx context.Context, bookID uuid.UUID, code string) (attrs, links int, ok bool) {
	var genreID uuid.UUID
	if err := s.pool.QueryRow(ctx,
		`SELECT genre_id FROM book_genres WHERE book_id=$1 AND code=$2 AND deprecated_at IS NULL`,
		bookID, code).Scan(&genreID); err != nil {
		return 0, 0, false
	}
	_ = s.pool.QueryRow(ctx,
		`SELECT count(*) FROM book_attributes WHERE book_id=$1 AND genre_id=$2 AND deprecated_at IS NULL`,
		bookID, genreID).Scan(&attrs)
	_ = s.pool.QueryRow(ctx,
		`SELECT count(*) FROM book_kind_genres WHERE book_id=$1 AND genre_id=$2`, bookID, genreID).Scan(&links)
	return attrs, links, true
}

// kindCascadeCounts returns the live attribute count a delete_kind would deprecate.
// ok=false when the kind code does not resolve to a LIVE kind.
func (s *Server) kindCascadeCounts(ctx context.Context, bookID uuid.UUID, code string) (attrs int, ok bool) {
	var kindID uuid.UUID
	if err := s.pool.QueryRow(ctx,
		`SELECT book_kind_id FROM book_kinds WHERE book_id=$1 AND code=$2 AND deprecated_at IS NULL`,
		bookID, code).Scan(&kindID); err != nil {
		return 0, false
	}
	_ = s.pool.QueryRow(ctx,
		`SELECT count(*) FROM book_attributes WHERE book_id=$1 AND kind_id=$2 AND deprecated_at IS NULL`,
		bookID, kindID).Scan(&attrs)
	return attrs, true
}
