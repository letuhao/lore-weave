package api

// Plan/Action kit — glossary op-set registration (spec
// docs/specs/2026-06-25-plan-action-kit.md §14). This file wires the ops the planner
// may emit into the shared `loreweave_mcp` Registry: each OpSpec maps a typed params
// blob to one of the EXISTING write cores (createKindFromParams /
// createAttrDefFromParams / adoptBookOntologyCore / the book_patch core / the
// cascade-delete primitives), and translates the core's Postgres/sentinel errors to
// the kit's outcome sentinels (ErrUniqueViolation / ErrNotFound / ErrStaleVersion /
// ErrBadParams / ErrAlreadyDone). No new write logic lives here — the kit owns
// execution control flow (execute.go), this file owns only the domain registration.
//
// Phase 1 ops (tiers 0–4) are additive (Destructive:false). Phase 2 slice 1 adds the
// tier-5 destructive deletes (delete_genre/kind/attribute, Destructive:true) — the
// executor skips each unless its op-id is in enabled_ops (G1). Every op is Idempotent
// (NewRegistry panics otherwise, G3). `edit_attribute` is the only base_version op
// (§17 — edit ops only).

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"

	"github.com/google/uuid"

	mcp "github.com/loreweave/loreweave_mcp"
)

// slugPattern is the `code` shape every kind/attribute code must match (§14 S4).
// Lowercase ASCII slug — the same shape the create cores assume downstream.
var slugPattern = regexp.MustCompile(`^[a-z0-9_]+$`)

// maxKindsPerOp bounds a single create_kinds op (MaxPlanOps caps op COUNT, not the
// kinds inside one op). Keeps the plan token + execution bounded (MED-4).
const maxKindsPerOp = 30

// ── op param shapes (thin wrappers over the existing typed params) ────────────

// createKindsParams is the create_kinds op payload — the same batch shape the
// single-confirm glossary_propose_kinds path uses (kindsBatchParams).
type createKindsParams struct {
	Kinds []kindCreateParams `json:"kinds"`
}

// addAttributesParams is the add_attributes op payload: attach attributes to an
// EXISTING kind (a NEW kind's attributes ride inside its create_kinds op, §14).
type addAttributesParams struct {
	KindCode   string         `json:"kind_code"`
	Attributes []kindAttrSpec `json:"attributes"`
}

// editAttributeFields is the editable subset for edit_attribute (§14: name,
// description, field_type — all optional; a nil field is left unchanged).
type editAttributeFields struct {
	Name        *string `json:"name,omitempty"`
	Description *string `json:"description,omitempty"`
	FieldType   *string `json:"field_type,omitempty"`
}

// editAttributeParams is the edit_attribute op payload — code-addressed by
// (kind_code, genre_code, code), the same identity the single-op book_patch uses.
type editAttributeParams struct {
	KindCode  string              `json:"kind_code"`
	GenreCode string              `json:"genre_code"`
	Code      string              `json:"code"`
	Fields    editAttributeFields `json:"fields"`
}

// ── destructive op param shapes (Phase 2 slice 1, §18) ────────────────────────
// All three address a LIVE book-tier ontology row by its code and soft-deprecate it
// (the existing cascade primitives). They are Destructive — the executor skips them
// unless their op id is in enabled_ops (G1), so a hallucinated/injected delete never
// runs on a bare "approve".

type deleteGenreParams struct {
	GenreCode string `json:"genre_code"`
}

type deleteKindParams struct {
	KindCode string `json:"kind_code"`
}

// deleteAttributeParams is code-addressed by (kind_code, genre_code, code) — an
// attribute is keyed by (kind × genre × code), so the genre is required to disambiguate
// (same identity as edit_attribute).
type deleteAttributeParams struct {
	KindCode  string `json:"kind_code"`
	GenreCode string `json:"genre_code"`
	Code      string `json:"code"`
}

// mergeCandidateParams orchestrates the EXISTING merge action over a DETECTED duplicate
// cluster (slice 2 — "planner orchestrates existing actions"). The planner copies a
// `candidate_id` from the "Pending merge candidates" context block (one stable PK per
// cluster — never an ambiguous entity name or a transcribed member UUID). The handler
// resolves the candidate's CURRENT members at execute time; winner_id is an optional
// override of the detector's suggested winner.
type mergeCandidateParams struct {
	CandidateID string `json:"candidate_id"`
	WinnerID    string `json:"winner_id,omitempty"`
}

// dismissCandidateParams rejects a detected duplicate cluster ("these are NOT the same
// entity"). Non-destructive — it only flips the candidate's status to 'dismissed'; no
// entity is merged or deleted. The planner copies a candidate_id from the same context
// block merge uses.
type dismissCandidateParams struct {
	CandidateID string `json:"candidate_id"`
}

// planRegistry builds the glossary Phase-1 op registry consumed by the kit's
// executor. Each Handler is self-transactional (delegates to a core that owns its
// own tx) and maps core errors to the kit sentinels.
//
// ParamSchema is left nil for every op: the existing cores + the per-op Validate
// funcs below are the strict gate (slug code + mandatory description, S4), and a
// hand-written JSON Schema would only duplicate that gate while drifting from the
// rich typed params (kindCreateParams has nested attributes, options, etc.). The
// planner's repair round (§15) keys off Validate's error string, not the schema.
func (s *Server) planRegistry() mcp.Registry {
	return mcp.NewRegistry(
		// tier 0 — adopt_genres (singleton; scaffolds `universal` so later ops anchor)
		mcp.OpSpec{
			Type:        "adopt_genres",
			Tier:        0,
			Destructive: false,
			Idempotent:  true,
			IdentityKey: func(json.RawMessage) (string, error) { return "adopt", nil },
			Handler: func(ctx context.Context, bookID, userID uuid.UUID, params json.RawMessage, _ string) (any, error) {
				var p adoptParams
				if err := json.Unmarshal(params, &p); err != nil {
					return nil, fmt.Errorf("%w: %v", mcp.ErrBadParams, err)
				}
				if err := s.adoptBookOntologyCore(ctx, bookID, userID, p.Genres, p.Kinds); err != nil {
					return nil, mapCoreErr(err)
				}
				return map[string]any{"adopted": true}, nil
			},
		},

		// tier 1 — create_kinds (each kind + its defining attributes, atomic per kind)
		mcp.OpSpec{
			Type:        "create_kinds",
			Tier:        1,
			Destructive: false,
			Idempotent:  true,
			IdentityKey: func(json.RawMessage) (string, error) { return "create_kinds", nil },
			Validate:    validateCreateKinds,
			Handler: func(ctx context.Context, bookID, _ uuid.UUID, params json.RawMessage, _ string) (any, error) {
				var p createKindsParams
				if err := json.Unmarshal(params, &p); err != nil {
					return nil, fmt.Errorf("%w: %v", mcp.ErrBadParams, err)
				}
				created := make([]string, 0, len(p.Kinds))
				skipped := make([]string, 0)
				// Skip-on-conflict mirrors effectSchemaCreateKinds: an already-present
				// kind code is a no-op skip (idempotent re-run), not a failure (G3).
				for _, kp := range p.Kinds {
					switch _, err := s.createKindFromParams(ctx, bookID, kp); {
					case err == nil:
						created = append(created, kp.Code)
					case isUniqueViolation(err):
						skipped = append(skipped, kp.Code)
					default:
						return nil, mapCoreErr(err)
					}
				}
				return map[string]any{"created": created, "skipped": skipped}, nil
			},
		},

		// tier 2 — add_attributes (attach to an EXISTING kind)
		mcp.OpSpec{
			Type:        "add_attributes",
			Tier:        2,
			Destructive: false,
			Idempotent:  true,
			IdentityKey: addAttributesIdentity,
			Validate:    validateAddAttributes,
			Handler: func(ctx context.Context, bookID, _ uuid.UUID, params json.RawMessage, _ string) (any, error) {
				var p addAttributesParams
				if err := json.Unmarshal(params, &p); err != nil {
					return nil, fmt.Errorf("%w: %v", mcp.ErrBadParams, err)
				}
				// Resolve the target kind once; a missing kind is target_gone (fail), not
				// a per-attribute skip — every attribute in this op shares the kind.
				kindID, kerr := s.resolveBookKindID(ctx, bookID, strings.TrimSpace(p.KindCode))
				if isNoRows(kerr) {
					return nil, fmt.Errorf("%w: kind %q not found in book ontology", mcp.ErrNotFound, p.KindCode)
				}
				if kerr != nil {
					return nil, mapCoreErr(kerr)
				}
				added := make([]string, 0, len(p.Attributes))
				skipped := make([]string, 0)
				for _, a := range p.Attributes {
					in := attrCreateParams{
						KindID:         kindID.String(),
						Code:           a.Code,
						Name:           a.Name,
						Description:    a.Description,
						FieldType:      a.FieldType,
						IsRequired:     a.IsRequired,
						Options:        a.Options,
						AutoFillPrompt: a.AutoFillPrompt,
					}
					switch _, err := s.createAttrDefFromParams(ctx, bookID, in); {
					case err == nil:
						added = append(added, a.Code)
					case isUniqueViolation(err):
						skipped = append(skipped, a.Code) // already present — idempotent
					case isForeignKeyViolation(err) || errors.Is(err, errNotAdopted):
						// The kind vanished between resolve and insert → target_gone.
						return nil, fmt.Errorf("%w: kind %q no longer present", mcp.ErrNotFound, p.KindCode)
					default:
						return nil, mapCoreErr(err)
					}
				}
				return map[string]any{"added": added, "skipped": skipped}, nil
			},
		},

		// tier 4 — edit_attribute (the only base_version op, §17)
		mcp.OpSpec{
			Type:        "edit_attribute",
			Tier:        4,
			Destructive: false,
			Idempotent:  true,
			IdentityKey: editAttributeIdentity,
			Handler: func(ctx context.Context, bookID, _ uuid.UUID, params json.RawMessage, baseVersion string) (any, error) {
				var p editAttributeParams
				if err := json.Unmarshal(params, &p); err != nil {
					return nil, fmt.Errorf("%w: %v", mcp.ErrBadParams, err)
				}
				detail, err := s.editAttributeCore(ctx, bookID, p, baseVersion)
				if err != nil {
					return nil, mapCoreErr(err)
				}
				return detail, nil
			},
		},

		// tier 5 — destructive deletes (run AFTER every create/edit; skipped unless the
		// op's id is in enabled_ops, G1). Each resolves the code deprecation-aware so a
		// re-run is already_done (idempotent), an absent code is target_gone (§5).
		mcp.OpSpec{
			Type:        "delete_genre",
			Tier:        5,
			Destructive: true,
			Idempotent:  true,
			IdentityKey: deleteGenreIdentity,
			Validate:    validateDeleteGenre,
			Handler: func(ctx context.Context, bookID, _ uuid.UUID, params json.RawMessage, _ string) (any, error) {
				var p deleteGenreParams
				if err := json.Unmarshal(params, &p); err != nil {
					return nil, fmt.Errorf("%w: %v", mcp.ErrBadParams, err)
				}
				id, err := s.resolveBookGenreForDelete(ctx, bookID, strings.TrimSpace(p.GenreCode))
				if err != nil {
					return nil, err // already a kit sentinel (ErrAlreadyDone / ErrNotFound)
				}
				found, derr := s.cascadeDeleteBookGenre(ctx, bookID, id)
				if derr != nil {
					return nil, mapCoreErr(derr)
				}
				if !found {
					return nil, mcp.ErrAlreadyDone // raced: deprecated between resolve and delete
				}
				return map[string]any{"deleted": "genre", "code": p.GenreCode}, nil
			},
		},
		mcp.OpSpec{
			Type:        "delete_kind",
			Tier:        5,
			Destructive: true,
			Idempotent:  true,
			IdentityKey: deleteKindIdentity,
			Validate:    validateDeleteKind,
			Handler: func(ctx context.Context, bookID, _ uuid.UUID, params json.RawMessage, _ string) (any, error) {
				var p deleteKindParams
				if err := json.Unmarshal(params, &p); err != nil {
					return nil, fmt.Errorf("%w: %v", mcp.ErrBadParams, err)
				}
				id, err := s.resolveBookKindForDelete(ctx, bookID, strings.TrimSpace(p.KindCode))
				if err != nil {
					return nil, err
				}
				found, derr := s.cascadeDeleteBookKind(ctx, bookID, id)
				if derr != nil {
					return nil, mapCoreErr(derr)
				}
				if !found {
					return nil, mcp.ErrAlreadyDone
				}
				return map[string]any{"deleted": "kind", "code": p.KindCode}, nil
			},
		},
		mcp.OpSpec{
			Type:        "delete_attribute",
			Tier:        5,
			Destructive: true,
			Idempotent:  true,
			IdentityKey: deleteAttributeIdentity,
			Validate:    validateDeleteAttribute,
			Handler: func(ctx context.Context, bookID, _ uuid.UUID, params json.RawMessage, _ string) (any, error) {
				var p deleteAttributeParams
				if err := json.Unmarshal(params, &p); err != nil {
					return nil, fmt.Errorf("%w: %v", mcp.ErrBadParams, err)
				}
				id, err := s.resolveBookAttrForDelete(ctx, bookID,
					strings.TrimSpace(p.KindCode), strings.TrimSpace(p.GenreCode), strings.TrimSpace(p.Code))
				if err != nil {
					return nil, err
				}
				found, derr := s.softDeleteBookAttribute(ctx, bookID, id)
				if derr != nil {
					return nil, mapCoreErr(derr)
				}
				if !found {
					return nil, mcp.ErrAlreadyDone
				}
				return map[string]any{"deleted": "attribute", "code": p.KindCode + "/" + p.Code}, nil
			},
		},

		// tier 5 — merge_candidate (orchestrates the EXISTING merge action over a
		// DETECTED duplicate cluster; Destructive — journaled + reversible). One op per
		// candidate so each gets its own enable toggle (slice 2).
		mcp.OpSpec{
			Type:        "merge_candidate",
			Tier:        5,
			Destructive: true,
			Idempotent:  true,
			IdentityKey: mergeCandidateIdentity,
			Validate:    validateMergeCandidate,
			Handler: func(ctx context.Context, bookID, userID uuid.UUID, params json.RawMessage, _ string) (any, error) {
				var p mergeCandidateParams
				if err := json.Unmarshal(params, &p); err != nil {
					return nil, fmt.Errorf("%w: %v", mcp.ErrBadParams, err)
				}
				candID, perr := uuid.Parse(strings.TrimSpace(p.CandidateID))
				if perr != nil {
					return nil, fmt.Errorf("%w: candidate_id %q is not a uuid", mcp.ErrBadParams, p.CandidateID)
				}
				members, suggested, status, found, lerr := s.loadCandidateForMerge(ctx, bookID, candID)
				if lerr != nil {
					return nil, lerr // → ReasonInternal (abort)
				}
				if !found {
					return nil, fmt.Errorf("%w: merge candidate %s not found in this book", mcp.ErrNotFound, candID)
				}
				if status != "proposed" {
					return nil, fmt.Errorf("%w: merge candidate %s is already %s", mcp.ErrAlreadyDone, candID, status)
				}
				winner, werr := resolveMergeWinner(members, suggested, strings.TrimSpace(p.WinnerID))
				if werr != nil {
					return nil, werr
				}
				losers := make([]string, 0, len(members)-1)
				for _, m := range members {
					if m != winner {
						losers = append(losers, m.String())
					}
				}
				if len(losers) == 0 {
					return nil, fmt.Errorf("%w: merge candidate %s has no losers (need ≥2 members)", mcp.ErrBadParams, candID)
				}
				results, merr := s.mergeEntitiesCore(ctx, bookID, winner, losers, userID)
				if errors.Is(merr, errMergeBadWinner) {
					return nil, fmt.Errorf("%w: the winner entity is no longer live", mcp.ErrNotFound)
				}
				if merr != nil {
					return nil, merr // → ReasonInternal (abort)
				}
				// Idempotency that does NOT depend on the candidate's status flip (which is
				// markCandidatesMerged's best-effort, possibly-lagging post-commit effect):
				// if NO loser was actually merged — every one was already merged away — the
				// re-run is a no-op → already_done.
				merged := 0
				for _, r := range results {
					if r.Status == "merged" {
						merged++
					}
				}
				if merged == 0 {
					return nil, fmt.Errorf("%w: every member of candidate %s was already merged", mcp.ErrAlreadyDone, candID)
				}
				return map[string]any{"candidate_id": candID.String(), "winner_id": winner.String(), "merged": merged, "results": results}, nil
			},
		},

		// tier 4 — dismiss_candidate (NON-destructive: reject a detected duplicate
		// cluster as "not the same entity"; flips status to 'dismissed', no entity
		// touched). Applies on confirm without an enable toggle.
		mcp.OpSpec{
			Type:        "dismiss_candidate",
			Tier:        4,
			Destructive: false,
			Idempotent:  true,
			IdentityKey: dismissCandidateIdentity,
			Validate:    validateDismissCandidate,
			Handler: func(ctx context.Context, bookID, _ uuid.UUID, params json.RawMessage, _ string) (any, error) {
				var p dismissCandidateParams
				if err := json.Unmarshal(params, &p); err != nil {
					return nil, fmt.Errorf("%w: %v", mcp.ErrBadParams, err)
				}
				candID, perr := uuid.Parse(strings.TrimSpace(p.CandidateID))
				if perr != nil {
					return nil, fmt.Errorf("%w: candidate_id %q is not a uuid", mcp.ErrBadParams, p.CandidateID)
				}
				_, _, status, found, lerr := s.loadCandidateForMerge(ctx, bookID, candID)
				if lerr != nil {
					return nil, lerr // → ReasonInternal (abort)
				}
				if !found {
					return nil, fmt.Errorf("%w: merge candidate %s not found in this book", mcp.ErrNotFound, candID)
				}
				if status != "proposed" {
					// already dismissed, or already merged — either way it is resolved.
					return nil, fmt.Errorf("%w: candidate %s is already %s", mcp.ErrAlreadyDone, candID, status)
				}
				reason, derr := s.dismissMergeCandidateCore(ctx, bookID, candID)
				if derr != nil {
					return nil, derr // → ReasonInternal (abort)
				}
				switch reason {
				case "":
					return map[string]any{"dismissed": candID.String()}, nil
				case "already_merged":
					return nil, fmt.Errorf("%w: candidate %s was merged before it could be dismissed", mcp.ErrAlreadyDone, candID)
				default: // "not_found" (raced to delete)
					return nil, fmt.Errorf("%w: candidate %s is no longer present", mcp.ErrNotFound, candID)
				}
			},
		},
	)
}

// resolveMergeWinner picks the winner for a merge_candidate op: an explicit winner_id
// (when it is a member of the cluster) overrides; otherwise the detector's suggested
// winner (when it is a member); otherwise ErrBadParams — the plan must name a winner.
func resolveMergeWinner(members []uuid.UUID, suggested *uuid.UUID, winnerID string) (uuid.UUID, error) {
	isMember := func(id uuid.UUID) bool {
		for _, m := range members {
			if m == id {
				return true
			}
		}
		return false
	}
	if winnerID != "" {
		w, err := uuid.Parse(winnerID)
		if err != nil {
			return uuid.Nil, fmt.Errorf("%w: winner_id %q is not a uuid", mcp.ErrBadParams, winnerID)
		}
		if !isMember(w) {
			return uuid.Nil, fmt.Errorf("%w: winner_id is not a member of this candidate", mcp.ErrBadParams)
		}
		return w, nil
	}
	if suggested != nil && isMember(*suggested) {
		return *suggested, nil
	}
	return uuid.Nil, fmt.Errorf("%w: candidate has no suggested winner — the plan must supply winner_id", mcp.ErrBadParams)
}

// loadCandidateForMerge reads one merge candidate's CURRENT members + suggested winner +
// status, book-scoped (found=false when the id is unknown / belongs to another book).
func (s *Server) loadCandidateForMerge(ctx context.Context, bookID, candidateID uuid.UUID) (members []uuid.UUID, suggested *uuid.UUID, status string, found bool, err error) {
	row := s.pool.QueryRow(ctx, `
		SELECT member_entity_ids, suggested_winner_entity_id, status
		FROM merge_candidates WHERE book_id = $1 AND candidate_id = $2`, bookID, candidateID)
	if err := row.Scan(&members, &suggested, &status); err != nil {
		if isNoRows(err) {
			return nil, nil, "", false, nil
		}
		return nil, nil, "", false, err
	}
	return members, suggested, status, true, nil
}

// ── deprecation-aware delete resolvers (idempotency, §5) ──────────────────────
// The plain resolveBook*ID helpers filter deprecated_at IS NULL, so they conflate
// "never existed" with "already deprecated". A delete op needs them split: a re-run
// (already deprecated) is an idempotent skip (ErrAlreadyDone), an absent code is
// target_gone (ErrNotFound). These look up the row IGNORING its own deprecated_at and
// return the kit sentinel directly.

func (s *Server) resolveBookGenreForDelete(ctx context.Context, bookID uuid.UUID, code string) (uuid.UUID, error) {
	var id uuid.UUID
	var deprecated bool
	err := s.pool.QueryRow(ctx,
		`SELECT genre_id, deprecated_at IS NOT NULL FROM book_genres WHERE book_id=$1 AND code=$2`,
		bookID, code).Scan(&id, &deprecated)
	return resolveDeleteResult(id, deprecated, err, "genre", code)
}

func (s *Server) resolveBookKindForDelete(ctx context.Context, bookID uuid.UUID, code string) (uuid.UUID, error) {
	var id uuid.UUID
	var deprecated bool
	err := s.pool.QueryRow(ctx,
		`SELECT book_kind_id, deprecated_at IS NOT NULL FROM book_kinds WHERE book_id=$1 AND code=$2`,
		bookID, code).Scan(&id, &deprecated)
	return resolveDeleteResult(id, deprecated, err, "kind", code)
}

// resolveBookAttrForDelete keys by (kind × genre × code) on LIVE parent kind+genre
// (a deprecated parent already cascade-deprecated this attribute → target_gone, which
// is the honest outcome). The attribute's OWN deprecated_at is what splits
// already_done from a live delete.
func (s *Server) resolveBookAttrForDelete(ctx context.Context, bookID uuid.UUID, kindCode, genreCode, attrCode string) (uuid.UUID, error) {
	var id uuid.UUID
	var deprecated bool
	err := s.pool.QueryRow(ctx, `
		SELECT a.attr_id, a.deprecated_at IS NOT NULL
		  FROM book_attributes a
		  JOIN book_kinds  k ON k.book_kind_id = a.kind_id  AND k.deprecated_at IS NULL
		  JOIN book_genres g ON g.genre_id     = a.genre_id AND g.deprecated_at IS NULL
		 WHERE a.book_id = $1 AND k.code = $2 AND g.code = $3 AND a.code = $4`,
		bookID, kindCode, genreCode, attrCode).Scan(&id, &deprecated)
	return resolveDeleteResult(id, deprecated, err, "attribute", kindCode+"/"+attrCode)
}

// loadBookGenreCodes returns the live book genre codes (sorted) for the planner's
// state summary — the planner can only delete_genre a code it is shown here.
func (s *Server) loadBookGenreCodes(ctx context.Context, bookID uuid.UUID) ([]string, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT code FROM book_genres WHERE book_id=$1 AND deprecated_at IS NULL ORDER BY code`, bookID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	codes := make([]string, 0)
	for rows.Next() {
		var c string
		if err := rows.Scan(&c); err != nil {
			return nil, err
		}
		codes = append(codes, c)
	}
	return codes, rows.Err()
}

// resolveDeleteResult folds a delete-target lookup into the kit's outcome sentinels:
// no row → ErrNotFound (target_gone); already deprecated → ErrAlreadyDone (idempotent
// skip); live → (id, nil).
func resolveDeleteResult(id uuid.UUID, deprecated bool, err error, kind, code string) (uuid.UUID, error) {
	if isNoRows(err) {
		return uuid.Nil, fmt.Errorf("%w: %s %q not found in book ontology", mcp.ErrNotFound, kind, code)
	}
	if err != nil {
		return uuid.Nil, err // → ReasonInternal (abort)
	}
	if deprecated {
		return uuid.Nil, fmt.Errorf("%w: %s %q already deleted", mcp.ErrAlreadyDone, kind, code)
	}
	return id, nil
}

// editAttributeCore is the book_patch CORE for an attribute edit, composed from the
// same primitives toolBookPatch uses (resolveBookPatch → bookRowVersion →
// compareBaseVersion → applyBookUpdate) but WITHOUT the tool-level grant auth: the
// plan executor already authorized the confirm, and the handler is handed a resolved
// bookID. base is the optimistic-concurrency token from §17; a mismatch surfaces as
// errVersionConflict (→ ErrStaleVersion) and a missing row as pgx.ErrNoRows (→
// ErrNotFound), both via mapCoreErr at the call site.
func (s *Server) editAttributeCore(ctx context.Context, bookID uuid.UUID, p editAttributeParams, base string) (any, error) {
	// Fail closed when no base_version is supplied: compareBaseVersion treats "" as
	// "no check", so without this an edit would silently clobber a concurrent change.
	// The planner cannot read row versions, so plan-driven edits land here — reject
	// them rather than clobber (HIGH-1). edit_attribute via a plan is deferred until
	// the planner threads per-row versions.
	if strings.TrimSpace(base) == "" {
		return nil, fmt.Errorf("%w: edit_attribute requires a base_version (not supported via a plan yet)", mcp.ErrBadParams)
	}
	if p.Fields.FieldType != nil && !isValidFieldType(*p.Fields.FieldType) {
		return nil, errInvalidFieldType
	}
	in := bookPatchToolIn{
		Level:       bookLevelAttr,
		Code:        strings.TrimSpace(p.Code),
		KindCode:    strings.TrimSpace(p.KindCode),
		GenreCode:   strings.TrimSpace(p.GenreCode),
		BaseVersion: base,
		Name:        p.Fields.Name,
		Description: p.Fields.Description,
		FieldType:   p.Fields.FieldType,
	}
	table, idCol, id, fields, perr := s.resolveBookPatch(ctx, bookID, bookLevelAttr, in)
	if perr != nil {
		// resolveBookPatch maps a no-row target to a descriptive (non-pgx) error, so
		// translate it to the not-found sentinel here.
		return nil, fmt.Errorf("%w: %v", mcp.ErrNotFound, perr)
	}
	cur, err := s.bookRowVersion(ctx, table, idCol, bookID, id)
	if err != nil {
		return nil, fmt.Errorf("%w: target no longer exists", mcp.ErrNotFound)
	}
	if cverr := compareBaseVersion(cur, strings.TrimSpace(base)); cverr != nil {
		return nil, cverr // errVersionConflict → ErrStaleVersion
	}
	if len(fields) == 0 {
		return nil, fmt.Errorf("%w: no editable fields supplied", mcp.ErrBadParams)
	}
	if err := s.applyBookUpdate(ctx, table, idCol, bookID, id, fields); err != nil {
		return nil, err
	}
	newVer, _ := s.bookRowVersion(ctx, table, idCol, bookID, id)
	return map[string]any{"code": in.Code, "version": newVer}, nil
}

// ── identity keys (§16 dedupe/conflict detection) ─────────────────────────────

func addAttributesIdentity(params json.RawMessage) (string, error) {
	var p addAttributesParams
	if err := json.Unmarshal(params, &p); err != nil {
		return "", err
	}
	return strings.TrimSpace(p.KindCode), nil
}

func editAttributeIdentity(params json.RawMessage) (string, error) {
	var p editAttributeParams
	if err := json.Unmarshal(params, &p); err != nil {
		return "", err
	}
	return strings.TrimSpace(p.KindCode) + "/" + strings.TrimSpace(p.GenreCode) + "/" + strings.TrimSpace(p.Code), nil
}

func deleteGenreIdentity(params json.RawMessage) (string, error) {
	var p deleteGenreParams
	if err := json.Unmarshal(params, &p); err != nil {
		return "", err
	}
	return strings.TrimSpace(p.GenreCode), nil
}

func deleteKindIdentity(params json.RawMessage) (string, error) {
	var p deleteKindParams
	if err := json.Unmarshal(params, &p); err != nil {
		return "", err
	}
	return strings.TrimSpace(p.KindCode), nil
}

func deleteAttributeIdentity(params json.RawMessage) (string, error) {
	var p deleteAttributeParams
	if err := json.Unmarshal(params, &p); err != nil {
		return "", err
	}
	return strings.TrimSpace(p.KindCode) + "/" + strings.TrimSpace(p.GenreCode) + "/" + strings.TrimSpace(p.Code), nil
}

func mergeCandidateIdentity(params json.RawMessage) (string, error) {
	var p mergeCandidateParams
	if err := json.Unmarshal(params, &p); err != nil {
		return "", err
	}
	return strings.TrimSpace(p.CandidateID), nil // one merge per candidate (dedupe)
}

func dismissCandidateIdentity(params json.RawMessage) (string, error) {
	var p dismissCandidateParams
	if err := json.Unmarshal(params, &p); err != nil {
		return "", err
	}
	return strings.TrimSpace(p.CandidateID), nil
}

// ── Validate (S4 — slug code + mandatory description) ─────────────────────────

func validateCreateKinds(params json.RawMessage) error {
	var p createKindsParams
	if err := json.Unmarshal(params, &p); err != nil {
		return err
	}
	if len(p.Kinds) == 0 {
		return errors.New("create_kinds: at least one kind is required")
	}
	if len(p.Kinds) > maxKindsPerOp {
		return fmt.Errorf("create_kinds: at most %d kinds per op (got %d) — split the goal into a smaller plan", maxKindsPerOp, len(p.Kinds))
	}
	for _, k := range p.Kinds {
		if !slugPattern.MatchString(k.Code) {
			return fmt.Errorf("create_kinds: kind code %q must match ^[a-z0-9_]+$", k.Code)
		}
		if strings.TrimSpace(k.Name) == "" {
			return fmt.Errorf("create_kinds: kind %q must have a non-empty name", k.Code)
		}
		for _, a := range k.Attributes {
			if err := validateAttrSpec("create_kinds", a); err != nil {
				return err
			}
		}
	}
	return nil
}

func validateAddAttributes(params json.RawMessage) error {
	var p addAttributesParams
	if err := json.Unmarshal(params, &p); err != nil {
		return err
	}
	if !slugPattern.MatchString(strings.TrimSpace(p.KindCode)) {
		return fmt.Errorf("add_attributes: kind_code %q must match ^[a-z0-9_]+$", p.KindCode)
	}
	if len(p.Attributes) == 0 {
		return errors.New("add_attributes: at least one attribute is required")
	}
	for _, a := range p.Attributes {
		if err := validateAttrSpec("add_attributes", a); err != nil {
			return err
		}
	}
	return nil
}

// ── destructive op Validate (slug codes; the target need not exist at validate
// time — a missing target surfaces at execute as target_gone, §5) ─────────────

func validateDeleteGenre(params json.RawMessage) error {
	var p deleteGenreParams
	if err := json.Unmarshal(params, &p); err != nil {
		return err
	}
	if !slugPattern.MatchString(strings.TrimSpace(p.GenreCode)) {
		return fmt.Errorf("delete_genre: genre_code %q must match ^[a-z0-9_]+$", p.GenreCode)
	}
	return nil
}

func validateDeleteKind(params json.RawMessage) error {
	var p deleteKindParams
	if err := json.Unmarshal(params, &p); err != nil {
		return err
	}
	if !slugPattern.MatchString(strings.TrimSpace(p.KindCode)) {
		return fmt.Errorf("delete_kind: kind_code %q must match ^[a-z0-9_]+$", p.KindCode)
	}
	return nil
}

func validateDeleteAttribute(params json.RawMessage) error {
	var p deleteAttributeParams
	if err := json.Unmarshal(params, &p); err != nil {
		return err
	}
	if !slugPattern.MatchString(strings.TrimSpace(p.KindCode)) {
		return fmt.Errorf("delete_attribute: kind_code %q must match ^[a-z0-9_]+$", p.KindCode)
	}
	if !slugPattern.MatchString(strings.TrimSpace(p.GenreCode)) {
		return fmt.Errorf("delete_attribute: genre_code %q must match ^[a-z0-9_]+$ (an attribute is keyed by kind × genre × code)", p.GenreCode)
	}
	if !slugPattern.MatchString(strings.TrimSpace(p.Code)) {
		return fmt.Errorf("delete_attribute: code %q must match ^[a-z0-9_]+$", p.Code)
	}
	return nil
}

// validateMergeCandidate checks the candidate_id (and optional winner_id) are UUIDs.
// The candidate need not exist at validate time — a stale id surfaces at execute as
// target_gone (§5), the same shape as the delete ops.
func validateMergeCandidate(params json.RawMessage) error {
	var p mergeCandidateParams
	if err := json.Unmarshal(params, &p); err != nil {
		return err
	}
	if _, err := uuid.Parse(strings.TrimSpace(p.CandidateID)); err != nil {
		return fmt.Errorf("merge_candidate: candidate_id %q must be a uuid (copy it from the Pending merge candidates block)", p.CandidateID)
	}
	if w := strings.TrimSpace(p.WinnerID); w != "" {
		if _, err := uuid.Parse(w); err != nil {
			return fmt.Errorf("merge_candidate: winner_id %q must be a uuid", p.WinnerID)
		}
	}
	return nil
}

func validateDismissCandidate(params json.RawMessage) error {
	var p dismissCandidateParams
	if err := json.Unmarshal(params, &p); err != nil {
		return err
	}
	if _, err := uuid.Parse(strings.TrimSpace(p.CandidateID)); err != nil {
		return fmt.Errorf("dismiss_candidate: candidate_id %q must be a uuid (copy it from the Pending merge candidates block)", p.CandidateID)
	}
	return nil
}

// validateAttrSpec enforces a slug code and a non-empty description on an attribute
// (S4 — descriptions are mandatory and load-bearing for downstream extraction).
func validateAttrSpec(op string, a kindAttrSpec) error {
	if !slugPattern.MatchString(a.Code) {
		return fmt.Errorf("%s: attribute code %q must match ^[a-z0-9_]+$", op, a.Code)
	}
	if strings.TrimSpace(a.Name) == "" {
		return fmt.Errorf("%s: attribute %q must have a non-empty name", op, a.Code)
	}
	if a.Description == nil || strings.TrimSpace(*a.Description) == "" {
		return fmt.Errorf("%s: attribute %q must have a non-empty description", op, a.Code)
	}
	return nil
}

// ── error mapping (core/Postgres error → kit sentinel, §5) ────────────────────

// mapCoreErr translates an existing-core error to the kit's outcome sentinel. A
// value that is ALREADY a kit sentinel passes through; anything unrecognized is
// returned as-is (the kit treats a non-sentinel error as ReasonInternal and aborts
// the remaining plan, §5).
func mapCoreErr(err error) error {
	switch {
	case err == nil:
		return nil
	case errors.Is(err, mcp.ErrUniqueViolation),
		errors.Is(err, mcp.ErrNotFound),
		errors.Is(err, mcp.ErrStaleVersion),
		errors.Is(err, mcp.ErrBadParams),
		errors.Is(err, mcp.ErrAlreadyDone):
		return err // already a kit sentinel
	case isUniqueViolation(err):
		return fmt.Errorf("%w: %v", mcp.ErrUniqueViolation, err)
	case isForeignKeyViolation(err), isNoRows(err), errors.Is(err, errNotAdopted):
		return fmt.Errorf("%w: %v", mcp.ErrNotFound, err)
	case errors.Is(err, errVersionConflict):
		return fmt.Errorf("%w: %v", mcp.ErrStaleVersion, err)
	case errors.Is(err, errInvalidFieldType):
		return fmt.Errorf("%w: %v", mcp.ErrBadParams, err)
	default:
		return err // → ReasonInternal (abort remaining plan)
	}
}
