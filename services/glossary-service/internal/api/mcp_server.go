package api

import (
	"context"
	"crypto/subtle"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/loreweave/glossary-service/internal/domain"
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
	}, s.toolSearch)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_get_entity",
		Description: "Fetch one glossary entity's full detail (attributes, aliases, kind, " +
			"counts) by id, within a book. Use after glossary_search to read an entity in depth.",
	}, s.toolGetEntity)

	// F2 (§12.3): retarget of the old glossary_list_kinds → the "what CAN I adopt"
	// standards-browse role. Use BEFORE adopting; for the in-book schema use
	// glossary_book_ontology_read.
	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_list_system_standards",
		Description: "List the SYSTEM standards catalogue (entity kinds + their attribute " +
			"definitions) — the templates a book can adopt. Use to learn what standards exist " +
			"BEFORE scaffolding a book. For what a specific book ALREADY has, use glossary_book_ontology_read.",
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
type listKindsToolOut struct {
	Kinds []domain.EntityKind `json:"kinds"`
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
	Ontology *bookOntologyResp `json:"ontology"`
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
	return nil, bookOntologyReadToolOut{Ontology: ont}, nil
}

func (s *Server) toolListKinds(ctx context.Context, _ *mcp.CallToolRequest, _ listKindsToolIn) (*mcp.CallToolResult, listKindsToolOut, error) {
	// Kinds are global (not book-scoped); the X-Internal-Token gate is sufficient.
	kinds, err := s.loadKinds(ctx)
	if err != nil {
		return nil, listKindsToolOut{}, errors.New("failed to load kinds")
	}
	// /review-impl MED-1: loadKinds' EntityCount is a GLOBAL (cross-book)
	// aggregate — both a cross-tenant info leak and misleading for a single-book
	// assistant (the LLM would read it as "this book's count"). Strip it; the
	// schema (kinds + attributes) is what the assistant needs, not counts.
	for i := range kinds {
		kinds[i].EntityCount = 0
	}
	return nil, listKindsToolOut{Kinds: kinds}, nil
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
}
type proposeEntityToolOut struct {
	EntityID string `json:"entity_id"`
	// Status is created | skipped_exists | skipped_tombstoned.
	Status string `json:"status"`
	// AttributesSkipped (070): attribute codes the caller supplied that don't
	// exist on the kind and were therefore dropped — surfaced so the LLM knows
	// they didn't land (mirrors the bulk extract's entityResult.AttributesSkipped).
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
	entityID, status, skipped, err := s.proposeNewEntity(ctx, bookID, kindID, name, in.Attributes)
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
func (s *Server) proposeNewEntity(ctx context.Context, bookID, kindID uuid.UUID, name string, attrs map[string]any) (uuid.UUID, string, []string, error) {
	existingID, err := s.findEntityByNameOrAlias(ctx, s.pool, bookID, kindID, name)
	if err != nil {
		return uuid.Nil, "", nil, fmt.Errorf("entity lookup: %w", err)
	}
	if existingID != uuid.Nil {
		rejected, err := s.entityHasTag(ctx, s.pool, existingID, tagAIRejected)
		if err != nil {
			return uuid.Nil, "", nil, fmt.Errorf("tombstone check: %w", err)
		}
		if rejected {
			return existingID, "skipped_tombstoned", nil, nil
		}
		return existingID, "skipped_exists", nil, nil
	}

	attrDefMap, err := s.loadAttrDefMap(ctx, bookID)
	if err != nil {
		return uuid.Nil, "", nil, fmt.Errorf("attr defs: %w", err)
	}
	ent := extractedEntity{Name: name, Attributes: attrs}
	// "und" (ISO 639-2 undetermined) for the tool-proposed name's language — the
	// human can correct it when reviewing the draft in the inbox.
	//
	// /review-impl HIGH fix: this used to pre-compute "skipped" itself (any code
	// missing from attrDefMap) and tell the LLM it "didn't land" — true when
	// createExtractedEntity silently dropped unmatched codes, FALSE now that it
	// captures them into "description" (D-GLOSSARY-UNMATCHED-ATTR-FALLBACK). Use
	// createExtractedEntity's own returned skip list instead of duplicating
	// (now-stale) logic about what it does with an unmatched code.
	entityID, _, skippedAttrs, err := s.createExtractedEntity(ctx, s.pool, bookID, kindID, ent, nil, attrDefMap, "und", []string{tagAISuggested, tagAssistant})
	if err != nil {
		return uuid.Nil, "", nil, fmt.Errorf("create draft: %w", err)
	}
	var skipped []string
	for _, sa := range skippedAttrs {
		skipped = append(skipped, sa.Code)
	}
	return entityID, "created", skipped, nil
}
