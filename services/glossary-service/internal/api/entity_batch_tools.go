package api

import (
	"context"
	"errors"
	"strings"

	"github.com/google/jsonschema-go/jsonschema"
	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
	lwmcp "github.com/loreweave/loreweave_mcp"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// T-ENTITY-BATCH — glossary_propose_entities: the batch-capable sibling that
// supersedes glossary_propose_new_entity (tool-catalog-simplification spec §3.3,
// resolved 2026-07-06 — a confirmed near-term need: a KG-extraction pipeline
// minting many entities per pass). Pure orchestration: reuses proposeNewEntity
// per item, the SAME core glossary_propose_new_entity calls (mcp_server.go), so
// the write paths can never diverge. CAT-1 doesn't apply here (no update/delete
// discriminator to design — this is create-only, matching the tool it
// supersedes) but CAT-3 does: items[] (1..50), per-item independent results.

// RegisterEntityBatchTools adds glossary_propose_entities to the user/book /mcp
// server. Registered separately (append-only convention, matches RegisterOntologyTools).
func (s *Server) RegisterEntityBatchTools(srv *mcp.Server) {
	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_propose_entities",
		Description: "Create/author/add one or more NEW entities (character, place, item, concept, ...) " +
			"with their attribute values for a book's glossary IN ONE CALL -- also the tool to use for a " +
			"SINGLE new entity (pass items with just one item), not only for batches; prefer this over " +
			"calling the legacy glossary_propose_new_entity. Each item is created as a DRAFT suggestion " +
			"in the review inbox -- NOT canon -- and succeeds or fails independently (not all-or-nothing). " +
			"If a name already exists, or was previously rejected, that item is skipped, not duplicated -- " +
			"this tool only CREATES new entities; to add or change attributes on an entity that already " +
			"exists, use glossary_entity_set_attributes (or glossary_entity_rename to rename it). " +
			"Call glossary_search first to confirm names don't already exist; call " +
			"glossary_book_ontology_read to pick valid kinds. Accepts 1-50 items.",
		InputSchema: entityBatchSchema(),
		Meta: lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{
			"create a new entity", "add a new entity", "author an entity", "manually create an entity",
			"add an entity with attribute values", "create a character", "add a character", "add a place",
			"add several characters", "bulk create entities", "mint many entities", "batch propose entities",
		}),
	}, s.toolProposeEntities)
}

func entityBatchSchema() *jsonschema.Schema {
	s := closedSetSchemaFor[proposeEntitiesToolIn](map[string][]any{})
	itemsNode := schemaPropAt(s, "items")
	one, fifty := 1, 50
	itemsNode.MinItems = &one
	itemsNode.MaxItems = &fifty
	return s
}

type proposeEntityItemIn struct {
	Kind       string         `json:"kind" jsonschema:"REQUIRED: the entity kind code (e.g. character, place) -- see glossary_book_ontology_read"`
	Name       string         `json:"name" jsonschema:"REQUIRED: the entity's name"`
	Attributes map[string]any `json:"attributes,omitempty" jsonschema:"optional attribute code to value map"`
	// ScopeLabel (D-GLOSSARY-ENTITY-SCOPE, optional) disambiguates two entities that
	// would otherwise share the same name+kind but are genuinely different (e.g. a
	// world/realm name in a multi-world story) -- a free-text label, not a reference
	// to any other entity. Leave empty unless disambiguation is actually needed.
	ScopeLabel string `json:"scope_label,omitempty" jsonschema:"optional free-text disambiguator (e.g. a world/realm name) for a name that legitimately recurs across different in-story contexts"`
}

type proposeEntitiesToolIn struct {
	BookID string                `json:"book_id" jsonschema:"the book to add entities to (UUID)"`
	Items  []proposeEntityItemIn `json:"items" jsonschema:"1-50 entities to propose; each succeeds or fails independently"`
}

type proposeEntityItemResult struct {
	Name              string   `json:"name"`
	EntityID          string   `json:"entity_id,omitempty"`
	Status            string   `json:"status"` // created | skipped_exists | skipped_tombstoned | error
	AttributesSkipped []string `json:"attributes_skipped,omitempty"`
	Error             string   `json:"error,omitempty"`
}

type proposeEntitiesSummary struct {
	Created int `json:"created"`
	Skipped int `json:"skipped"`
	Failed  int `json:"failed"`
}

type proposeEntitiesOut struct {
	Results []proposeEntityItemResult `json:"results"`
	Summary proposeEntitiesSummary    `json:"summary"`
}

func (s *Server) toolProposeEntities(ctx context.Context, _ *mcp.CallToolRequest, in proposeEntitiesToolIn) (*mcp.CallToolResult, proposeEntitiesOut, error) {
	if len(in.Items) == 0 {
		return nil, proposeEntitiesOut{}, errors.New("items must have at least one entry")
	}
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, proposeEntitiesOut{}, errors.New("missing caller identity")
	}
	bookID, err := uuid.Parse(strings.TrimSpace(in.BookID))
	if err != nil {
		return nil, proposeEntitiesOut{}, errors.New("book_id must be a UUID")
	}
	if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantEdit); err != nil {
		return nil, proposeEntitiesOut{}, uniformOwnershipError(err)
	}
	// Resolved ONCE for the whole batch (not per item) -- the kind map is
	// immutable for the duration of this call and every item needs it.
	kindMap, err := s.loadKindMap(ctx, bookID)
	if err != nil {
		return nil, proposeEntitiesOut{}, errors.New("failed to resolve kinds")
	}

	out := proposeEntitiesOut{Results: make([]proposeEntityItemResult, 0, len(in.Items))}
	for _, it := range in.Items {
		res := s.proposeOneEntity(ctx, bookID, kindMap, it)
		out.Results = append(out.Results, res)
		switch res.Status {
		case "created":
			out.Summary.Created++
		case "skipped_exists", "skipped_tombstoned":
			out.Summary.Skipped++
		default:
			out.Summary.Failed++
		}
	}
	// Silent-success guard (S01 live-eval): the batch is per-item independent, so a
	// PARTIAL failure (something WAS created, or all remaining were skipped-because-
	// they-exist) stays ok — the per-item errors live in Results. But if NOTHING was
	// created AND at least one item genuinely errored, the envelope MUST report
	// IsError. Otherwise a caller reads ok:true, never sees the hidden Failed count,
	// and retries forever — the measured mid-tier loop was proposing entities of a
	// kind that doesn't exist yet (`unknown kind`), 9× in one session, book untouched.
	// Per-item detail is preserved: the go-sdk still marshals `out` into
	// structuredContent when the handler returns a non-nil result with err==nil.
	if out.Summary.Created == 0 && out.Summary.Failed > 0 {
		msg := "no entities were created — every proposed item failed (see structuredContent for each item's error)."
		if allFailuresAreUnknownKind(out.Results) {
			msg += " Each failure is an 'unknown kind': that category does not exist in this book yet. " +
				"Create the categories first (glossary_adopt_standards to adopt the system kinds, or " +
				"glossary_propose_kinds for custom ones), then retry."
		}
		return &mcp.CallToolResult{
			IsError: true,
			Content: []mcp.Content{&mcp.TextContent{Text: msg}},
		}, out, nil
	}
	return nil, out, nil
}

// allFailuresAreUnknownKind reports whether every errored item failed with an
// "unknown kind" — the dominant silent-success cause — so the IsError message can
// point the caller at the actual fix (adopt/create the kind first). Returns false
// if there were no failures or any failure was for a different reason.
func allFailuresAreUnknownKind(results []proposeEntityItemResult) bool {
	sawFailure := false
	for _, r := range results {
		if r.Status == "error" {
			sawFailure = true
			if !strings.HasPrefix(r.Error, "unknown kind:") {
				return false
			}
		}
	}
	return sawFailure
}

// proposeOneEntity resolves one item's kind then delegates to proposeNewEntity
// (mcp_server.go) -- the EXACT core glossary_propose_new_entity calls, so a
// batch-created entity is indistinguishable from a singly-created one.
func (s *Server) proposeOneEntity(ctx context.Context, bookID uuid.UUID, kindMap map[string]uuid.UUID, it proposeEntityItemIn) proposeEntityItemResult {
	name := strings.TrimSpace(it.Name)
	res := proposeEntityItemResult{Name: name}
	if name == "" {
		res.Status, res.Error = "error", "name is required"
		return res
	}
	kind := strings.TrimSpace(it.Kind)
	if kind == "" {
		res.Status, res.Error = "error", "kind is required"
		return res
	}
	kindID, ok := kindMap[kind]
	if !ok {
		res.Status, res.Error = "error", "unknown kind: "+kind
		return res
	}
	scopeLabel, err := validateScopeLabel(it.ScopeLabel)
	if err != nil {
		res.Status, res.Error = "error", err.Error()
		return res
	}
	entityID, status, skipped, err := s.proposeNewEntity(ctx, bookID, kindID, name, it.Attributes, scopeLabel)
	if err != nil {
		res.Status, res.Error = "error", "propose failed"
		return res
	}
	res.EntityID = entityID.String()
	res.Status = status
	res.AttributesSkipped = skipped
	return res
}
