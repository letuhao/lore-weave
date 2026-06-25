package api

// Plan/Action kit — glossary Phase-1 op-set registration (spec
// docs/specs/2026-06-25-plan-action-kit.md §14). This file wires the four
// additive-only ops the planner may emit into the shared `loreweave_mcp`
// Registry: each OpSpec maps a typed params blob to one of the EXISTING write
// cores (createKindFromParams / createAttrDefFromParams / adoptBookOntologyCore /
// the book_patch core), and translates the core's Postgres/sentinel errors to the
// kit's outcome sentinels (ErrUniqueViolation / ErrNotFound / ErrStaleVersion /
// ErrBadParams). No new write logic lives here — the kit owns execution control
// flow (execute.go), this file owns only the domain registration (§13/§14).
//
// Phase 1 is additive-only: every op is Destructive:false and Idempotent:true
// (NewRegistry panics on a non-idempotent op, G3). `edit_attribute` is the only
// op carrying base_version (§17 — edit ops only).

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
	)
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
