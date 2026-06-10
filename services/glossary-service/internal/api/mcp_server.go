package api

import (
	"context"
	"crypto/subtle"
	"errors"
	"fmt"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/loreweave/glossary-service/internal/domain"
)

// mcpHandler builds the glossary MCP server (Tier-R read tools) wrapped in the
// identity middleware. Mounted at /mcp by Router(). The federation gateway
// (ai-gateway) connects here as an MCP client; each tool call carries the
// per-call envelope (X-Internal-Token + X-User-Id) the gateway forwards.
func (s *Server) mcpHandler() http.Handler {
	srv := mcp.NewServer(&mcp.Implementation{Name: "glossary", Version: "0.1.0"}, nil)

	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_search",
		Description: "Search a book's glossary for entities (characters, places, items, " +
			"concepts) by name, alias, or natural-language terms. Returns ranked entities " +
			"with name, aliases, kind, and a short description. Use this to find what the " +
			"glossary already knows before answering or proposing changes.",
	}, s.toolSearch)

	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_get_entity",
		Description: "Fetch one glossary entity's full detail (attributes, aliases, kind, " +
			"counts) by id, within a book. Use after glossary_search to read an entity in depth.",
	}, s.toolGetEntity)

	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_list_kinds",
		Description: "List the glossary's entity kinds and their attribute definitions " +
			"(the schema). Use to learn what kinds/attributes exist before reasoning about entities.",
	}, s.toolListKinds)

	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_propose_new_entity",
		Description: "Propose a NEW entity (character, place, item, concept, …) for a book's " +
			"glossary. It is created as a DRAFT suggestion in the review inbox — NOT canon — and " +
			"must be approved by a human. If the name already exists, or was previously rejected, " +
			"no duplicate is created. Call glossary_search first to confirm it doesn't already exist; " +
			"call glossary_list_kinds to pick a valid kind.",
	}, s.toolProposeNewEntity)

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
	if err := s.checkBookOwnership(ctx, bookID, userID); err != nil {
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
	if err := s.checkBookOwnership(ctx, bookID, userID); err != nil {
		return nil, getEntityToolOut{}, uniformOwnershipError(err)
	}
	detail, err := s.loadEntityDetail(ctx, bookID, entityID)
	if err != nil {
		// Not found within this (owned) book → uniform not-accessible.
		return nil, getEntityToolOut{}, errors.New("entity not accessible")
	}
	return nil, getEntityToolOut{Entity: detail}, nil
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
	Kind       string         `json:"kind" jsonschema:"the entity kind code (e.g. character, place) — see glossary_list_kinds"`
	Name       string         `json:"name" jsonschema:"the entity's name"`
	Attributes map[string]any `json:"attributes,omitempty" jsonschema:"optional attribute code → value map"`
}
type proposeEntityToolOut struct {
	EntityID string `json:"entity_id"`
	// Status is created | skipped_exists | skipped_tombstoned.
	Status string `json:"status"`
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
	if err := s.checkBookOwnership(ctx, bookID, userID); err != nil {
		return nil, proposeEntityToolOut{}, uniformOwnershipError(err)
	}
	kindMap, err := s.loadKindMap(ctx)
	if err != nil {
		return nil, proposeEntityToolOut{}, errors.New("failed to resolve kinds")
	}
	kindID, ok := kindMap[in.Kind]
	if !ok {
		return nil, proposeEntityToolOut{}, errors.New("unknown kind: " + in.Kind)
	}
	entityID, status, err := s.proposeNewEntity(ctx, bookID, kindID, name, in.Attributes)
	if err != nil {
		return nil, proposeEntityToolOut{}, errors.New("propose failed")
	}
	return nil, proposeEntityToolOut{EntityID: entityID.String(), Status: status}, nil
}

// proposeNewEntity creates a NEW glossary entity as a DRAFT suggestion, or skips
// when the name already exists (dedup, H9) or was previously ai-rejected
// (tombstone, H9). Reuses the pipeline writeback path so a tool-proposed draft is
// indistinguishable from a pipeline-discovered one (INV-1: draft never reaches
// canon). The caller must have verified book ownership. Returns the entity id +
// a status: created | skipped_exists | skipped_tombstoned.
func (s *Server) proposeNewEntity(ctx context.Context, bookID, kindID uuid.UUID, name string, attrs map[string]any) (uuid.UUID, string, error) {
	existingID, err := s.findEntityByNameOrAlias(ctx, bookID, kindID, name)
	if err != nil {
		return uuid.Nil, "", fmt.Errorf("entity lookup: %w", err)
	}
	if existingID != uuid.Nil {
		rejected, err := s.entityHasTag(ctx, existingID, tagAIRejected)
		if err != nil {
			return uuid.Nil, "", fmt.Errorf("tombstone check: %w", err)
		}
		if rejected {
			return existingID, "skipped_tombstoned", nil
		}
		return existingID, "skipped_exists", nil
	}

	attrDefMap, err := s.loadAttrDefMap(ctx)
	if err != nil {
		return uuid.Nil, "", fmt.Errorf("attr defs: %w", err)
	}
	ent := extractedEntity{Name: name, Attributes: attrs}
	// "und" (ISO 639-2 undetermined) for the tool-proposed name's language — the
	// human can correct it when reviewing the draft in the inbox.
	entityID, err := s.createExtractedEntity(ctx, bookID, kindID, ent, nil, attrDefMap, "und", []string{tagAISuggested, tagAssistant})
	if err != nil {
		return uuid.Nil, "", fmt.Errorf("create draft: %w", err)
	}
	return entityID, "created", nil
}
