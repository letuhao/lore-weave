package api

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strconv"
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
			"calling a per-entity propose tool. Each item is created as a DRAFT suggestion " +
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
	// Guidance makes SUCCESS unambiguous when `created == 0` because every item ALREADY
	// EXISTED. Without it the model reads `{"created": 0, "skipped": 1}` as a failure and
	// retries the identical call — measured live 2026-07-23 (session 019f8de6): the same
	// `glossary_propose_entities` call at iterations 1, 2 and 3, each answering
	// `skipped_exists`, the entity present in the DB the whole time.
	//
	// This is the same retry-loop class the IsError guard below already fixed for the
	// FAILED case ("9x in one session, book untouched"); the all-skipped case was the
	// remaining hole. It stays a NON-error — nothing went wrong, the desired state simply
	// already held — so the fix is a positive statement, not an error flag.
	Guidance string `json:"guidance,omitempty"`
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
		// Message discipline (review-impl): the chat-service agent loop DROPS
		// structuredContent on an isError result, so the per-item Results never reach
		// the agent — the message TEXT is all it receives. So (1) never point at
		// structuredContent, (2) inline the DISTINCT failure reasons, and (3) report the
		// real counts, not "every item failed" (which is false when some already existed).
		reasons := distinctErrorReasons(out.Results)
		msg := fmt.Sprintf("no entities were created — %d of %d item(s) failed",
			out.Summary.Failed, len(in.Items))
		if out.Summary.Skipped > 0 {
			msg += fmt.Sprintf(" (%d already existed)", out.Summary.Skipped)
		}
		if len(reasons) > 0 {
			msg += ". Reasons: " + strings.Join(reasons, "; ")
		}
		if allFailuresAreUnknownKind(out.Results) {
			msg += ". An 'unknown kind' means that category does not exist in this book yet — " +
				"create the categories first (glossary_adopt_standards to adopt the system kinds, or " +
				"glossary_propose_batch for custom ones), then retry."
		} else {
			msg += "."
		}
		return &mcp.CallToolResult{
			IsError: true,
			Content: []mcp.Content{&mcp.TextContent{Text: msg}},
		}, out, nil
	}
	// Success-discrimination (OUT-4): nothing created because everything already
	// existed is a SUCCESS, but `{"created": 0}` reads as failure to a mid-tier model,
	// which then re-issues the identical call. Say the desired state already holds and
	// name the existing entities, so the model reports to the user instead of retrying.
	if out.Summary.Created == 0 && out.Summary.Failed == 0 && out.Summary.Skipped > 0 {
		out.Guidance = "SUCCESS — nothing to do: " + existingNamesPhrase(out.Results) +
			" already exist in this book's glossary, so no duplicate was created. " +
			"This is the desired end state. Do NOT call this tool again with the same " +
			"items; tell the user the entity already exists (use glossary_get_entity or " +
			"glossary_entity_set_attributes to inspect or change it)."
	}
	return nil, out, nil
}

// existingNamesPhrase renders the already-existing entity names for the all-skipped
// guidance, capped so a 50-item batch can't produce a giant string.
func existingNamesPhrase(results []proposeEntityItemResult) string {
	const maxNames = 5
	names := make([]string, 0, maxNames)
	extra := 0
	for _, r := range results {
		if r.Status != "skipped_exists" && r.Status != "skipped_tombstoned" {
			continue
		}
		if len(names) < maxNames {
			names = append(names, strconv.Quote(r.Name))
		} else {
			extra++
		}
	}
	if len(names) == 0 {
		return "the requested entities"
	}
	phrase := strings.Join(names, ", ")
	if extra > 0 {
		phrase += fmt.Sprintf(" and %d more", extra)
	}
	return phrase
}

// distinctErrorReasons collects the DISTINCT error strings across the failed items,
// preserving first-seen order and capping the count so a large heterogeneous batch
// can't produce a giant message. This is what the caller actually reads (the chat
// agent loop drops the per-item structuredContent on an isError result).
func distinctErrorReasons(results []proposeEntityItemResult) []string {
	const maxReasons = 5
	seen := make(map[string]bool, maxReasons)
	out := make([]string, 0, maxReasons)
	extra := 0
	for _, r := range results {
		if r.Status != "error" || r.Error == "" || seen[r.Error] {
			continue
		}
		seen[r.Error] = true
		if len(out) < maxReasons {
			out = append(out, r.Error)
		} else {
			extra++
		}
	}
	if extra > 0 {
		out = append(out, fmt.Sprintf("(+%d more)", extra))
	}
	return out
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

// normalizeKindSynonym maps a natural-language kind word an LLM commonly emits to its
// canonical system-kind code, so "add a place" (kind:"place") resolves to "location".
// ONLY common, unambiguous synonyms whose target is one of the 12 seeded system kinds —
// ambiguous ones (e.g. faction → org vs organization) are deliberately left out so we
// never silently mis-route. Used strictly as a FALLBACK (the raw code is tried first),
// so a book's own custom kind of the same name is never overridden.
func normalizeKindSynonym(code string) string {
	switch strings.ToLower(strings.TrimSpace(code)) {
	case "place", "places", "setting", "settings", "region", "area", "locale":
		return "location"
	case "person", "people", "char", "cast", "npc":
		return "character"
	case "thing", "object", "artifact", "artefact":
		return "item"
	case "concept", "term", "terms", "jargon_term":
		return "terminology"
	default:
		return code
	}
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
		// (b) Synonym fallback — an LLM naturally emits "place"/"person" for a
		// location/character (the dominant "unknown kind" cause). Map common,
		// unambiguous synonyms to their canonical system-kind code and retry. A
		// FALLBACK only (the raw code was tried first), so a book's OWN custom kind
		// of the same name always wins. Adopt `kind` to the canonical either way so
		// a still-unadopted miss reports "unknown kind: location" (a real, adoptable
		// system kind) not "place" — this is what lets the adopt→retry guidance work.
		if canon := normalizeKindSynonym(kind); canon != kind {
			kind = canon
			kindID, ok = kindMap[kind]
		}
	}
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
		// T13-D2 — THE CAUSE USED TO BE DISCARDED HERE, and nothing was logged either, so a
		// failed item was undiagnosable from BOTH ends. `proposeNewEntity` wraps every failure
		// with the operation that produced it ("begin tx: …", "book lock: …", "entity lookup:
		// …", "tombstone check: …") and all of it was replaced by the constant "propose
		// failed". Measured live 2026-08-13 (session 019ffa96): a single-item propose returned
		// results[0] = {"status":"error","error":"propose failed"} and `docker logs
		// glossary-service` had NOTHING for the request — no way to tell a transient DB error
		// from a permanent one, and nothing an author or a model could act on.
		//
		// The branch immediately above already surfaces its cause via err.Error(); this one is
		// the outlier. The wrapped error can carry storage detail, so it goes to the LOG (where
		// an operator needs it) while the caller gets a message that at least says what KIND of
		// failure it is — a server-side one, so retrying the identical item will not help. That
		// distinction is the actionable part: the previous text left "fix your argument" and
		// "the database is down" indistinguishable.
		slog.Error("propose_entities: item failed",
			"book_id", bookID.String(), "name", name, "kind", kind, "error", err)
		res.Status, res.Error = "error", "could not be saved (server-side failure, not a problem "+
			"with this item) — it has been logged; retrying the same item is unlikely to help"
		return res
	}
	res.EntityID = entityID.String()
	res.Status = status
	res.AttributesSkipped = skipped
	return res
}
