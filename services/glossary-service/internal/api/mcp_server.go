package api

import (
	"context"
	"crypto/subtle"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"sort"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/loreweave/grantclient"
	lwmcp "github.com/loreweave/loreweave_mcp"
)

// mcpHandler builds the glossary MCP server (Tier-R read tools) wrapped in the
// identity middleware. Mounted at /mcp by Router(). The federation gateway
// (ai-gateway) connects here as an MCP client; each tool call carries the
// per-call envelope (X-Internal-Token + X-User-Id) the gateway forwards.
func (s *Server) mcpHandler() http.Handler {
	srv := mcp.NewServer(&mcp.Implementation{Name: "glossary", Version: "0.1.0"}, nil)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_search",
		Description: "Search a book's glossary for entities (characters, places, items, " +
			"concepts) by name, alias, or natural-language terms. Returns ranked entities " +
			"with name, aliases, kind, and a short description. Use this to find what the " +
			"glossary already knows before answering or proposing changes.",
		Meta: lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, nil),
	}, s.toolSearch)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_get_entity",
		Description: "Fetch one glossary entity's full detail (attributes, aliases, kind, " +
			"counts) by id, within a book. Use after glossary_search to read an entity in depth.",
		Meta: lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, nil),
	}, s.toolGetEntity)

	// F2 (§12.3): retarget of the old glossary_list_kinds → the "what CAN I adopt"
	// standards-browse role. Use BEFORE adopting; for the in-book schema use
	// glossary_book_ontology_read.
	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_list_system_standards",
		Description: "List the SYSTEM standards catalogue — the entity kinds a book can adopt, " +
			"by CODE. Use once to learn what exists BEFORE scaffolding a book, then pass the codes " +
			"you want to glossary_adopt_standards; each kind's attributes come down with it. " +
			"Calling this twice returns the identical list. For what a specific book ALREADY has, " +
			"use glossary_book_ontology_read.",
		// Global System-standards read, no scope key (not book/user scoped) ⇒ ScopeNone.
		Meta: lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeNone, nil, nil),
	}, s.toolListKinds)

	// T1: book-tier ontology tools (read, adopt, create/patch/delete, set-genres,
	// entity-genres) register in their own file so tier streams don't contend here.
	s.RegisterBookTools(srv)
	// T2: book sync tools (available R + apply C). T3: user-tier standards tools.
	// Each appends here from its own file — append-only registration is the
	// per-tier parallelism enabler (buildplan §4).
	s.RegisterSyncTools(srv)
	s.RegisterUserTools(srv)
	// Pipeline M1: read tools (merge-candidates / chapter-links / revisions / unknowns).
	s.RegisterPipelineReadTools(srv)
	// Pipeline M2: direct (class-W) additive write tools (chapter-links, evidence).
	s.RegisterPipelineWriteTools(srv)
	// Pipeline M2: class-C propose tools for destructive curation (status / restore /
	// reassign-kind / merge) — mint a confirm card, never write directly.
	s.RegisterPipelineProposeTools(srv)
	// Pipeline M4: entity-translation tool (class-W; draft, never overwrites verified).
	s.RegisterPipelineTranslateTools(srv)
	// S5: web-search deep-research tool (class-C; paid outward call → confirm-gated).
	s.RegisterDeepResearchTools(srv)
	// General free-form web research (class-R read; paid outward call, not gated —
	// returns neutralized sources for topic research before any entity exists).
	s.RegisterWebSearchTool(srv)
	// T-ONTO: consolidated create/update/delete tools (tool-catalog-simplification
	// spec) — supersede the book/user create/patch/delete tools above, which stay
	// registered (tagged _meta.visibility:"legacy") for existing callers.
	s.RegisterOntologyTools(srv)
	// §3.3 resolved 2026-07-06 — glossary_propose_entities supersedes this
	// tool with a batch-capable sibling (a confirmed near-term need: a
	// KG-extraction pipeline minting many entities per pass).
	s.RegisterEntityBatchTools(srv)
	// Real-usage feedback finding — glossary_entity_delete (Tier-W propose+confirm)
	// + glossary_entity_restore (Tier-A direct): the FE's Undo allowlist already
	// carries these exact tool names (useActivityUndo.ts); this wires them up.
	s.RegisterEntityDeleteTools(srv)
	// Real-usage feedback finding (2026-07-08) — glossary_entity_set_attributes:
	// entities were write-once for attribute values via MCP (creation only); no
	// reachable editor existed for an already-existing entity.
	s.RegisterEntityAttributeEditTools(srv)
	// WS-4A (agent-discoverability spec) — glossary_extract_entities_from_doc: the
	// seed-doc → entity-candidates bridge (workflow W2 / scenario S02 Path B). Tier-R
	// derive: turns a pasted notes doc into {kind,name,attributes} candidates the
	// agent then feeds to glossary_propose_entities. Writes nothing itself.
	s.RegisterEntityDocExtractTools(srv)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_propose_new_entity",
		Description: "Propose a NEW entity (character, place, item, concept, …) for a book's " +
			"glossary. It is created as a DRAFT suggestion in the review inbox — NOT canon — and " +
			"must be approved by a human. If the name already exists, or was previously rejected, " +
			"no duplicate is created. Call glossary_search first to confirm it doesn't already exist; " +
			"call glossary_book_ontology_read to pick a valid kind. " +
			"NOTE: superseded by glossary_propose_entities -- kept for existing callers only.",
		// Tier was previously unset (defaulting to R) despite being a direct write --
		// corrected to A (auto-commit, draft-only so low-risk) while legacy-tagging it,
		// since both edits touch this same registration.
		Meta: lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, nil), lwmcp.VisibilityLegacy),
	}, s.toolProposeNewEntity)

	// Class-C proposals. These MINT a generalized action confirm token (no write) +
	// a confirm card — the actual write is the human-confirmed, JWT-only
	// /v1/glossary/actions/confirm (there is deliberately NO MCP tool that writes —
	// INV-T1/INV-T3). After calling one, pass its confirm_token to the
	// glossary_confirm_action frontend tool so the human can review and confirm.
	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_propose_new_kind",
		Description: "Propose a NEW entity KIND (a schema-level type like 'Power System' that every " +
			"entity of that kind is described by). PASS the kind's defining `attributes` in the SAME call " +
			"(each with a clear `description` — extraction uses it as the per-attribute instruction): they are " +
			"created ATOMICALLY with the kind on ONE confirm, so no follow-up per-attribute call is needed. A " +
			"kind with no attributes can't describe anything. This is high-impact — it does NOT create " +
			"anything; it returns a confirm_token + preview that a human must explicitly confirm. Pass the " +
			"confirm_token to glossary_confirm_action. Use sparingly, only when no existing kind " +
			"(glossary_book_ontology_read) fits.",
		InputSchema: closedSetSchemaFor[proposeKindToolIn](map[string][]any{
			"attributes[].field_type": enumFieldTypes,
		}),
		// Mints a grant confirm_token (no direct write) ⇒ Tier W.
		Meta: lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, nil),
	}, s.toolProposeNewKind)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_propose_kinds",
		Description: "Propose MANY entity kinds AT ONCE — the whole ontology in ONE confirm. PREFER this over " +
			"calling glossary_propose_new_kind repeatedly: the user wants to create an ONTOLOGY, not one kind at a " +
			"time, so batch every kind you intend to add into a single `kinds` list (each kind carries its own " +
			"defining `attributes`, each with a clear `description` — extraction uses it as the per-attribute " +
			"instruction). Returns ONE confirm_token + a preview listing all kinds; the human confirms once via " +
			"glossary_confirm_action and they are all created (idempotent — an existing kind is skipped). High-impact; " +
			"creates nothing until confirmed.",
		InputSchema: closedSetSchemaFor[proposeKindsToolIn](map[string][]any{
			"kinds[].attributes[].field_type": enumFieldTypes,
		}),
		Meta: lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, nil),
	}, s.toolProposeKinds)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_plan",
		Description: "PLAN a multi-step ontology goal in ONE shot. Given a natural-language `goal` (e.g. " +
			"'design an ontology for this xianxia novel'), a capable PLANNER model reads the book's current " +
			"ontology and produces ONE typed plan (adopt genres, create kinds with their attributes, add/edit " +
			"attributes) — returned as a SINGLE confirm_token + a per-operation preview. The human confirms once " +
			"via glossary_confirm_action and a deterministic executor applies the whole plan (idempotent; existing " +
			"rows are skipped). PREFER this for any goal needing more than one or two writes — do NOT loop the " +
			"individual propose tools. Optional `model_ref` overrides the user's default 'planner' model. Creates " +
			"nothing until confirmed.",
		// Mints a grant confirm_token ⇒ Tier W. Calls a PLANNER LLM synchronously at
		// mint time (runPlanner → provider-registry) ⇒ Paid (spends real money on call).
		Meta: lwmcp.WithPaid(lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, nil)),
	}, s.toolPlan)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_propose_batch",
		Description: "Apply MANY ontology changes on ONE confirm — the DETERMINISTIC batch path. Pass the " +
			"operations EXPLICITLY in `ops` and they are validated + minted into a SINGLE execute_plan confirm " +
			"card (no planner model is called — use this, not glossary_plan, when you already know the exact " +
			"changes). ALWAYS prefer this over calling glossary_propose_new_kind / glossary_propose_new_attribute / " +
			"glossary_book_* repeatedly: emitting several individual confirm cards in one turn FAILS — only the first " +
			"can be confirmed. Each op is {type, params, rationale?}. Op types and their params: " +
			"adopt_genres {genres:[code],kinds:[code]}; " +
			"create_kinds {kinds:[{code,name,description,attributes:[{code,name,description,field_type}]}]} (NEW kinds, each with its attributes); " +
			"add_attributes {kind_code,attributes:[{code,name,description,field_type}]} (to an EXISTING kind); " +
			"edit_attribute {kind_code,code,...fields,base_version}; " +
			"delete_genre {genre_code}; delete_kind {kind_code}; delete_attribute {kind_code,genre_code,code}; " +
			"merge_candidate {candidate_id,winner_id?}; dismiss_candidate {candidate_id}. " +
			"Every attribute needs a clear `description` (extraction uses it as the instruction). Slug codes only " +
			"(^[a-z0-9_]+$). The human confirms once; a deterministic executor applies the whole batch idempotently " +
			"(existing rows are skipped, destructive ops are per-op opt-in). Creates nothing until confirmed. Pass " +
			"the returned confirm_token to glossary_confirm_action. " +
			// W0 #6: a worked example of the batch envelope — 4/4 live calls failed
			// because models nested the payload wrong ("op create_kinds: at least one
			// kind is required"); showing one full envelope fixes the shape.
			`Worked example: {"book_id":"<uuid>","goal":"add two kinds","ops":[` +
			`{"type":"create_kinds","params":{"kinds":[{"code":"sect","name":"Sect","description":"An organization of cultivators",` +
			`"attributes":[{"code":"leader","name":"Leader","description":"Who leads this sect","field_type":"text"}]}]},` +
			`"rationale":"the book has none"},` +
			`{"type":"delete_kind","params":{"kind_code":"unused_kind"},"rationale":"user asked to remove it"}]} ` +
			"— note each op's payload goes INSIDE its `params` object (create_kinds params MUST contain a non-empty `kinds` array).",
		InputSchema: relaxAdditionalProps(
			closedSetSchemaFor[proposeBatchToolIn](map[string][]any{
				"ops[].type": {"adopt_genres", "create_kinds", "add_attributes", "edit_attribute",
					"delete_genre", "delete_kind", "delete_attribute", "merge_candidate", "dismiss_candidate"},
			}),
			// weak models add extras at the ROOT (a stray `type`) and on op items;
			// the op `type` enum stays strict, unknowns are admitted (W0 soak).
			"", "ops[]",
		),
		// Mints a grant confirm_token ⇒ Tier W. NO planner LLM (deterministic) ⇒ not paid.
		Meta: lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, nil),
	}, s.toolProposeBatch)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_propose_new_attribute",
		Description: "Propose a NEW attribute on an existing kind (e.g. add 'cultivation_realm' to the " +
			"character kind). Schema-level and high-impact — it does NOT write; it returns a confirm_token + " +
			"preview a human must confirm via glossary_confirm_action. Call glossary_book_ontology_read first to pick " +
			"the kind_code and avoid duplicating an existing attribute.",
		InputSchema: closedSetSchemaFor[proposeAttrToolIn](map[string][]any{
			"field_type": enumFieldTypes,
		}),
		Meta: lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, nil),
	}, s.toolProposeNewAttribute)
	// glossary_book_delete + glossary_book_* tools are registered in RegisterBookTools (T1).

	streamable := mcp.NewStreamableHTTPHandler(
		func(*http.Request) *mcp.Server { return srv },
		&mcp.StreamableHTTPOptions{Stateless: true, JSONResponse: true},
	)
	return s.mcpIdentityMiddleware(streamable)
}

// mcpIdentityMiddleware validates the service token (SO-1) and lifts X-User-Id
// into the request context so the tool handlers can read it (the proven §20
// header→ctx pattern — go-sdk stateless + our own middleware). Identity is never
// derived from the LLM (SEC-1).
func (s *Server) mcpIdentityMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		tok := r.Header.Get("X-Internal-Token")
		if s.cfg.InternalServiceToken == "" ||
			subtle.ConstantTimeCompare([]byte(tok), []byte(s.cfg.InternalServiceToken)) != 1 {
			writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "invalid internal token")
			return
		}
		ctx := context.WithValue(r.Context(), ctxKeyUserID, r.Header.Get("X-User-Id"))
		// OD-8 carrier: lift X-Mcp-Key-Id into the kit's ctx so OwnerOnlyFromCtx
		// fires for public-key traffic (glossary runs its own middleware, not the
		// kit's IdentityMiddleware, so we inject via the kit helper).
		ctx = lwmcp.ContextWithMcpKeyID(ctx, r.Header.Get(lwmcp.HeaderMcpKeyID))
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// ── per-call identity (header → ctx) ─────────────────────────────────────────

type mcpCtxKey string

const ctxKeyUserID mcpCtxKey = "x-user-id"

func userIDFromCtx(ctx context.Context) (uuid.UUID, bool) {
	v, _ := ctx.Value(ctxKeyUserID).(string)
	if v == "" {
		return uuid.Nil, false
	}
	id, err := uuid.Parse(v)
	if err != nil {
		return uuid.Nil, false
	}
	return id, true
}

// uniformOwnershipError maps the ownership sentinels to caller-visible messages.
// Not-found and not-owner collapse to the SAME "not accessible" (H13) so a tool
// can't be used as an existence oracle; book-service-down is distinct so the
// caller knows to retry.
func uniformOwnershipError(err error) error {
	if errors.Is(err, ErrBookUnavailable) {
		return errors.New("book ownership check unavailable, try again")
	}
	if errors.Is(err, ErrBookInactive) {
		return errors.New("book is not in an editable state")
	}
	return errors.New("book not accessible")
}

// ── tool arg / result types ──────────────────────────────────────────────────

const (
	searchToolDefaultLimit = 20
	searchToolMaxLimit     = 50 // SO-3: bound tool output fed back to the LLM
)

type searchToolIn struct {
	BookID string `json:"book_id" jsonschema:"the book whose glossary to search (UUID)"`
	Query  string `json:"query" jsonschema:"natural-language search terms"`
	Limit  int    `json:"limit,omitempty" jsonschema:"max entities to return (default 20, max 50)"`
}
type searchToolOut struct {
	Entities []glossaryEntityForContext `json:"entities"`
}

type getEntityToolIn struct {
	BookID   string `json:"book_id" jsonschema:"the book the entity belongs to (UUID)"`
	EntityID string `json:"entity_id" jsonschema:"the entity to fetch (UUID)"`
}
type getEntityToolOut struct {
	Entity *entityDetailResp `json:"entity"`
}

type listKindsToolIn struct{}

// standardKind — the COMPACT view of a System standard, and the only thing an agent needs
// in order to answer the one question this tool exists to answer: "which of these do I
// adopt?" You adopt BY CODE (glossary_adopt_standards takes genre/kind codes), and the
// attribute definitions come down with the kind automatically when you do.
//
// It used to return domain.EntityKind — every kind with every attribute definition inlined,
// each carrying its own UUID, auto_fill_prompt, translation_hint, sort_order, is_active…
// **44,254 characters. 86% of it was `default_attributes` (114 objects the model cannot act
// on).** That is ~11k tokens — a THIRD of a turn's entire budget — for one read.
//
// The cost was not theoretical. Measured live: gemma called this tool TWENTY-FOUR times in a
// single S01 run and built nothing. Each call buried the previous call's answer deeper in the
// window, so the model could never see what it had already fetched, so it fetched it again.
// A tool whose result cannot fit in the context of the agent that calls it is not a tool the
// agent can use — it is a context bomb with a friendly description.
//
// 44,254 chars → ~1,500. Same decision, 3% of the cost.
type standardKind struct {
	Code        string   `json:"code"`
	Name        string   `json:"name"`
	Description string   `json:"description,omitempty"`
	GenreTags   []string `json:"genre_tags,omitempty"`
	// AttributeCount, not the attributes: enough for the agent to know the kind carries a
	// schema, without shipping the schema it never reads.
	AttributeCount int `json:"attribute_count"`
}

type listKindsToolOut struct {
	Kinds []standardKind `json:"kinds"`
	Note  string         `json:"note,omitempty"`
}

// ── tool handlers ─────────────────────────────────────────────────────────────

func (s *Server) toolSearch(ctx context.Context, _ *mcp.CallToolRequest, in searchToolIn) (*mcp.CallToolResult, searchToolOut, error) {
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, searchToolOut{}, errors.New("missing caller identity")
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, searchToolOut{}, errors.New("book_id must be a UUID")
	}
	if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantView); err != nil {
		return nil, searchToolOut{}, uniformOwnershipError(err)
	}
	limit := in.Limit
	if limit <= 0 {
		limit = searchToolDefaultLimit
	}
	if limit > searchToolMaxLimit {
		limit = searchToolMaxLimit
	}
	resp, err := s.selectGlossaryForContext(ctx, bookID, selectForContextRequest{
		Query:       in.Query,
		MaxEntities: limit,
	})
	if err != nil {
		return nil, searchToolOut{}, errors.New("glossary search failed")
	}
	return nil, searchToolOut{Entities: resp.Entities}, nil
}

func (s *Server) toolGetEntity(ctx context.Context, _ *mcp.CallToolRequest, in getEntityToolIn) (*mcp.CallToolResult, getEntityToolOut, error) {
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, getEntityToolOut{}, errors.New("missing caller identity")
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, getEntityToolOut{}, errors.New("book_id must be a UUID")
	}
	entityID, err := uuid.Parse(in.EntityID)
	if err != nil {
		return nil, getEntityToolOut{}, errors.New("entity_id must be a UUID")
	}
	if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantView); err != nil {
		return nil, getEntityToolOut{}, uniformOwnershipError(err)
	}
	detail, err := s.loadEntityDetail(ctx, bookID, entityID)
	if err != nil {
		// MCP-LOW3: a genuinely-missing entity (ErrNoRows) collapses to the
		// uniform "not accessible" (H13 — no existence oracle), but an INFRA
		// error (DB down, etc.) must not be silently masked — log it so the
		// fault is visible, while the caller still sees the uniform message.
		if !errors.Is(err, pgx.ErrNoRows) {
			slog.Error("glossary_get_entity: loadEntityDetail failed",
				"error", err.Error(), "book_id", bookID.String(), "entity_id", entityID.String())
		}
		return nil, getEntityToolOut{}, errors.New("entity not accessible")
	}
	return nil, getEntityToolOut{Entity: detail}, nil
}

type bookOntologyReadToolIn struct {
	BookID string `json:"book_id" jsonschema:"the book whose local ontology to read (UUID)"`
}
type bookOntologyReadToolOut struct {
	// D-2-ONTOLOGY-BLOAT: the COMPACT projection (identifiers + counts + base_version), not the full
	// per-attribute definitions — those inlined up to 117KB and crowded the model's context out.
	Ontology *compactBookOntology `json:"ontology"`
}

// toolBookOntologyRead reads a book's local ontology (genres/kinds/attributes/links).
// View-gated — the in-book schema read for an assistant working inside a book.
func (s *Server) toolBookOntologyRead(ctx context.Context, _ *mcp.CallToolRequest, in bookOntologyReadToolIn) (*mcp.CallToolResult, bookOntologyReadToolOut, error) {
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, bookOntologyReadToolOut{}, errors.New("missing caller identity")
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, bookOntologyReadToolOut{}, errors.New("book_id must be a UUID")
	}
	if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantView); err != nil {
		return nil, bookOntologyReadToolOut{}, uniformOwnershipError(err)
	}
	ont, err := s.loadBookOntology(ctx, bookID)
	if err != nil {
		return nil, bookOntologyReadToolOut{}, errors.New("failed to load book ontology")
	}
	// D-2-ONTOLOGY-BLOAT: return the compact projection (patch-able + counts), not the full defs.
	return nil, bookOntologyReadToolOut{Ontology: compactBookOntologyOf(ont)}, nil
}

func (s *Server) toolListKinds(ctx context.Context, _ *mcp.CallToolRequest, _ listKindsToolIn) (*mcp.CallToolResult, listKindsToolOut, error) {
	// Kinds are global (not book-scoped); the X-Internal-Token gate is sufficient.
	kinds, err := s.loadKinds(ctx)
	if err != nil {
		return nil, listKindsToolOut{}, errors.New("failed to load kinds")
	}
	// Project down to the compact view (see standardKind). Two things are deliberately
	// dropped here:
	//   * EntityCount — /review-impl MED-1: loadKinds' count is a GLOBAL, cross-book
	//     aggregate. A cross-tenant leak, and misleading to a single-book assistant, which
	//     would read it as "this book's count".
	//   * DefaultAttributes — 86% of the old payload and unusable by the caller: you adopt a
	//     standard by CODE, and its attributes come down with it.
	out := make([]standardKind, 0, len(kinds))
	for _, k := range kinds {
		desc := ""
		if k.Description != nil {
			desc = *k.Description
		}
		out = append(out, standardKind{
			Code:           k.Code,
			Name:           k.Name,
			Description:    desc,
			GenreTags:      k.GenreTags,
			AttributeCount: len(k.Attributes),
		})
	}
	return nil, listKindsToolOut{
		Kinds: out,
		Note: "Adopt these by CODE with glossary_adopt_standards (pass the kind/genre codes). " +
			"Each kind's attribute definitions come with it — you do not need to fetch or " +
			"re-state them.",
	}, nil
}

// ── Tier-W: propose a new entity (draft) ─────────────────────────────────────

// tagAssistant marks an assistant-originated suggestion (provenance, H1) alongside
// the ai-suggested inbox tag — so the review UI can distinguish chat-assistant
// proposals from background-pipeline discoveries.
const tagAssistant = "assistant"

type proposeEntityToolIn struct {
	BookID     string         `json:"book_id" jsonschema:"the book to add the entity to (UUID)"`
	Kind       string         `json:"kind" jsonschema:"the entity kind code (e.g. character, place) — see glossary_book_ontology_read"`
	Name       string         `json:"name" jsonschema:"the entity's name"`
	Attributes map[string]any `json:"attributes,omitempty" jsonschema:"optional attribute code → value map"`
	// ScopeLabel (D-GLOSSARY-ENTITY-SCOPE, optional) disambiguates two entities that
	// would otherwise share the same name+kind but are genuinely different (e.g. a
	// world/realm name in a multi-world story) — a free-text label, not a reference
	// to any other entity. Leave empty unless disambiguation is actually needed.
	ScopeLabel string `json:"scope_label,omitempty" jsonschema:"optional free-text disambiguator (e.g. a world/realm name) for a name that legitimately recurs across different in-story contexts"`
}
type proposeEntityToolOut struct {
	EntityID string `json:"entity_id"`
	// Status is created | skipped_exists | skipped_tombstoned.
	Status string `json:"status"`
	// AttributesSkipped (070): attribute codes the caller supplied that were NOT
	// applied — either they don't exist on the kind (status=created) OR the entity
	// already exists and this tool never mutates one (status=skipped_exists /
	// skipped_tombstoned, in which case ALL supplied attrs are listed). Surfaced so
	// the LLM knows they didn't land and can reapply via glossary_entity_set_attributes.
	AttributesSkipped []string `json:"attributes_skipped,omitempty"`
}

func (s *Server) toolProposeNewEntity(ctx context.Context, _ *mcp.CallToolRequest, in proposeEntityToolIn) (*mcp.CallToolResult, proposeEntityToolOut, error) {
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, proposeEntityToolOut{}, errors.New("missing caller identity")
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, proposeEntityToolOut{}, errors.New("book_id must be a UUID")
	}
	name := strings.TrimSpace(in.Name)
	if name == "" {
		return nil, proposeEntityToolOut{}, errors.New("name is required")
	}
	if strings.TrimSpace(in.Kind) == "" {
		return nil, proposeEntityToolOut{}, errors.New("kind is required")
	}
	scopeLabel, err := validateScopeLabel(in.ScopeLabel)
	if err != nil {
		return nil, proposeEntityToolOut{}, err
	}
	if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantEdit); err != nil {
		return nil, proposeEntityToolOut{}, uniformOwnershipError(err)
	}
	kindMap, err := s.loadKindMap(ctx, bookID)
	if err != nil {
		return nil, proposeEntityToolOut{}, errors.New("failed to resolve kinds")
	}
	kindID, ok := kindMap[in.Kind]
	if !ok {
		return nil, proposeEntityToolOut{}, errors.New("unknown kind: " + in.Kind)
	}
	entityID, status, skipped, err := s.proposeNewEntity(ctx, bookID, kindID, name, in.Attributes, scopeLabel)
	if err != nil {
		return nil, proposeEntityToolOut{}, errors.New("propose failed")
	}
	return nil, proposeEntityToolOut{EntityID: entityID.String(), Status: status, AttributesSkipped: skipped}, nil
}

// proposeNewEntity creates a NEW glossary entity as a DRAFT suggestion, or skips
// when the name already exists (dedup, H9) or was previously ai-rejected
// (tombstone, H9). Reuses the pipeline writeback path so a tool-proposed draft is
// indistinguishable from a pipeline-discovered one (INV-1: draft never reaches
// canon). The caller must have verified book ownership. Returns the entity id +
// a status: created | skipped_exists | skipped_tombstoned.
//
// scopeLabel (D-GLOSSARY-ENTITY-SCOPE, optional) — a plain author-set disambiguator
// (e.g. a world/realm name) so two entities that share a name+kind but are
// genuinely different aren't folded together by the dedup check below. "" behaves
// exactly as before (empty only matches another empty-scope entity).
// sortedAttrKeys returns the attribute codes in a caller-supplied attrs map, sorted
// for a stable result. Empty/nil map → nil (nothing to report).
func sortedAttrKeys(attrs map[string]any) []string {
	if len(attrs) == 0 {
		return nil
	}
	keys := make([]string, 0, len(attrs))
	for k := range attrs {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func (s *Server) proposeNewEntity(ctx context.Context, bookID, kindID uuid.UUID, name string, attrs map[string]any, scopeLabel string) (uuid.UUID, string, []string, error) {
	// D-GLOSSARY-PROPOSE-LOCK (cleared 2026-07-09): dedup check, tombstone check,
	// attr-def load, create, and the scope_label set all now run on ONE tx, held
	// under the SAME per-book advisory lock the bulk extraction pipeline already
	// uses (extractionWritebackLockNS, INV-C1) — this closes the TOCTOU race that
	// let 8 truly concurrent identical proposals create 8 duplicate rows.
	//
	// Two earlier attempts at this deadlocked under concurrent test load (each
	// hanging the full 600s timeout): both mixed tx-bound calls with a call that
	// hit s.pool directly (a SEPARATE connection) while the tx's own connection
	// was still held open — with a small pool and enough concurrent callers,
	// every goroutine ends up holding one connection while waiting on a second,
	// and nothing ever completes. The fix isn't "add a lock", it's "never need a
	// 2nd connection": every call below — including loadAttrDefMap, which used to
	// hardcode s.pool with no querier param at all — now takes tx explicitly, so
	// this whole function runs on exactly one connection start to finish.
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return uuid.Nil, "", nil, fmt.Errorf("begin tx: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck // no-op after a successful Commit

	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1, hashtext($2))`,
		extractionWritebackLockNS, bookID.String()); err != nil {
		return uuid.Nil, "", nil, fmt.Errorf("book lock: %w", err)
	}

	existingID, err := s.findEntityByNameOrAlias(ctx, tx, bookID, kindID, name, scopeLabel)
	if err != nil {
		return uuid.Nil, "", nil, fmt.Errorf("entity lookup: %w", err)
	}
	if existingID != uuid.Nil {
		rejected, err := s.entityHasTag(ctx, tx, existingID, tagAIRejected)
		if err != nil {
			return uuid.Nil, "", nil, fmt.Errorf("tombstone check: %w", err)
		}
		// The entity already exists and this tool NEVER mutates an existing one, so
		// none of the caller's attributes were applied. Surface them (rather than drop
		// them silently) so a weak model can see they didn't land and reapply via
		// glossary_entity_set_attributes.
		discarded := sortedAttrKeys(attrs)
		if rejected {
			return existingID, "skipped_tombstoned", discarded, nil
		}
		return existingID, "skipped_exists", discarded, nil
	}

	attrDefMap, err := s.loadAttrDefMap(ctx, tx, bookID)
	if err != nil {
		return uuid.Nil, "", nil, fmt.Errorf("attr defs: %w", err)
	}
	ent := extractedEntity{Name: name, Attributes: attrs}

	// /review-impl HIGH fix (2026-07-09): entity creation + the scope_label set
	// share this same tx — a uq_entity_dedup collision on the scope_label UPDATE
	// rolls back the whole creation instead of leaving a wrongly-scoped orphan.

	// "und" (ISO 639-2 undetermined) for the tool-proposed name's language — the
	// human can correct it when reviewing the draft in the inbox.
	//
	// /review-impl HIGH fix: this used to pre-compute "skipped" itself (any code
	// missing from attrDefMap) and tell the LLM it "didn't land" — true when
	// createExtractedEntity silently dropped unmatched codes, FALSE now that it
	// captures them into "description" (D-GLOSSARY-UNMATCHED-ATTR-FALLBACK). Use
	// createExtractedEntity's own returned skip list instead of duplicating
	// (now-stale) logic about what it does with an unmatched code.
	entityID, _, skippedAttrs, err := s.createExtractedEntity(ctx, tx, bookID, kindID, ent, nil, attrDefMap, "und", []string{tagAISuggested, tagAssistant})
	if err != nil {
		return uuid.Nil, "", nil, fmt.Errorf("create draft: %w", err)
	}
	if scopeLabel != "" {
		if _, err := tx.Exec(ctx,
			`UPDATE glossary_entities SET scope_label = $1 WHERE entity_id = $2`,
			scopeLabel, entityID,
		); err != nil {
			// entityID is real but never committed (the deferred Rollback above
			// undoes the whole tx) — safe to discard here, unlike before this fix.
			return uuid.Nil, "", nil, fmt.Errorf("set scope_label: %w", err)
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return uuid.Nil, "", nil, fmt.Errorf("commit: %w", err)
	}
	var skipped []string
	for _, sa := range skippedAttrs {
		skipped = append(skipped, sa.Code)
	}
	return entityID, "created", skipped, nil
}
