package api

// Catalog-unification 2026-07-22, Part D — glossary_set_genres.
//
// The three genre-MATRIX setters wired distinct axes but were near-identical tiny Tier-A
// tools: book_set_active_genres (the book's active columns, delta), book_set_kind_genres
// (a kind's genre links, delta), entity_set_genres (a per-entity override, replace). None
// are redundant with ontology_upsert/adopt_standards/propose_batch (those write ontology
// ROWS or adopt standards — nothing else wires the matrix), but three one-purpose tools add
// catalog noise. This UNIFIES them behind ONE tool with a closed-set `target` enum. Each
// target REUSES the SAME core the legacy tool uses (set*GenresCore below) — the legacy
// handlers in book_tools.go are now thin wrappers, so the write logic has ONE home.
//
// The grant level differs by target (book/kind wiring = Manage; a per-entity override =
// Edit), so the grant is checked per-target inside the dispatch, not once up front.

import (
	"context"
	"errors"
	"strings"

	"github.com/loreweave/grantclient"
	lwmcp "github.com/loreweave/loreweave_mcp"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// RegisterSetGenresTool adds glossary_set_genres to the user/book /mcp server.
func (s *Server) RegisterSetGenresTool(srv *mcp.Server) {
	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_set_genres",
		Description: "Turn a book's genres ON or OFF, wire a kind's genres, or override an entity's genres — " +
			"the genre MATRIX (which genres' attributes apply where). Use this to ACTIVATE or DEACTIVATE a genre. " +
			"Pick a `target`:\n" +
			"  • book_active — turn the book's genres ON/OFF (activate/deactivate the active matrix columns) by " +
			"DELTA. Uses add[] and/or remove[] genre codes (delta, so you never drop a column you didn't mention).\n" +
			"  • kind — wire a KIND's genre links (matrix row) by DELTA. Needs kind_code + add[]/remove[].\n" +
			"  • entity — set one ENTITY's genre override by REPLACE. Needs entity_id + genre_codes[] " +
			"(the full list; `universal` is always kept; an empty list clears back to the book default).\n" +
			"Writes immediately (Tier A, reversible). book_id is optional inside a book studio. NOT for " +
			"creating genres/kinds — use glossary_ontology_upsert or glossary_adopt_standards for that.",
		InputSchema: closedSetSchemaFor[setGenresToolIn](map[string][]any{
			"target": {"book_active", "kind", "entity"},
		}),
		Meta: lwmcp.WithAmbientBook(lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{
			"activate a genre", "turn on a genre", "link a genre to a kind", "set entity genres",
			"override an entity's genres", "wire the genre matrix",
		})),
	}, s.toolSetGenres)
}

// setGenresToolIn is a flat superset keyed by `target`; each target reads only its own fields.
type setGenresToolIn struct {
	// book_id OPTIONAL (ambient_book) — omitted inside a book studio, resolves from the envelope.
	BookID     string   `json:"book_id,omitempty" jsonschema:"the book (UUID). Omit inside a book studio — the current book is used."`
	Target     string   `json:"target" jsonschema:"which genre wiring to change: book_active | kind | entity"`
	KindCode   string   `json:"kind_code,omitempty" jsonschema:"for kind — the kind whose genre links to change"`
	EntityID   string   `json:"entity_id,omitempty" jsonschema:"for entity — the entity to override (UUID)"`
	Add        []string `json:"add,omitempty" jsonschema:"for book_active or kind — genre codes to add (delta)"`
	Remove     []string `json:"remove,omitempty" jsonschema:"for book_active or kind — genre codes to remove (delta)"`
	GenreCodes []string `json:"genre_codes,omitempty" jsonschema:"for entity — the full genre-code list for the override (replace; empty clears to the book default)"`
	// AllowCrossBook confirms a WRITE to a book DIFFERENT from the ambient studio (studio context
	// binding §2.2). Normally omit — the current book is used. A Tier-A write to another book is
	// soft-blocked until this is set (book-service parity; /review-impl MED fix 2026-07-22).
	AllowCrossBook bool `json:"allow_cross_book,omitempty" jsonschema:"set true ONLY to confirm editing a book different from the studio you're in (normally omit — the current book is used)"`
}

// setGenresToolOut is a discriminated union keyed by `target`. (Total/UsesBookDefault-style
// omitempty is intentional for the union — a false/zero on a branch that doesn't own the field
// would be misleading noise, unlike the single-purpose legacy tools that always owned it.)
type setGenresToolOut struct {
	Target          string   `json:"target"`
	ActiveCodes     []string `json:"active_codes,omitempty"`      // target=book_active
	GenreCodes      []string `json:"genre_codes,omitempty"`       // target=kind
	GenreIDs        []string `json:"genre_ids,omitempty"`         // target=entity
	UsesBookDefault bool     `json:"uses_book_default,omitempty"` // target=entity
	// Cross-book WRITE pre-confirm (§2.2): set (to the book_id) when a cross-book write was NOT
	// applied because allow_cross_book was absent. ScopeSource = "arg" | "envelope".
	CrossBookConfirmTarget string `json:"cross_book_confirm_required,omitempty"`
	ScopeSource            string `json:"scope_source,omitempty"`
	Guidance               string `json:"guidance,omitempty"`
}

func (s *Server) toolSetGenres(ctx context.Context, _ *mcp.CallToolRequest, in setGenresToolIn) (*mcp.CallToolResult, setGenresToolOut, error) {
	target := strings.TrimSpace(in.Target)
	// Cross-book WRITE pre-confirm (book-service parity, /review-impl MED 2026-07-22): set_genres is
	// a Tier-A IMMEDIATE write, so a write to a book OTHER than the ambient studio book must be
	// confirmed FIRST — never silently mutate the wrong book. Gate before the per-target grant so
	// nothing is applied without allow_cross_book. (Grant on the target book is still checked below.)
	if scope, ok := lwmcp.ResolveBookScope(ctx, in.BookID); ok && scope.CrossBook && !in.AllowCrossBook {
		return nil, setGenresToolOut{
			Target:                 target,
			CrossBookConfirmTarget: scope.BookID.String(),
			ScopeSource:            scope.Source,
			Guidance: "NOT APPLIED — this would edit genres on a DIFFERENT book (book_id=" +
				scope.BookID.String() + ") than the studio you're in. If that is intended, re-issue " +
				"the SAME call with allow_cross_book=true.",
		}, nil
	}
	switch target {
	case "book_active":
		_, bookID, err := s.bookToolAuthAmbient(ctx, in.BookID, grantclient.GrantManage)
		if err != nil {
			return nil, setGenresToolOut{}, err
		}
		out, err := s.setActiveGenresCore(ctx, bookID, in.Add, in.Remove)
		if err != nil {
			return nil, setGenresToolOut{}, err
		}
		return nil, setGenresToolOut{Target: "book_active", ActiveCodes: out.ActiveCodes}, nil
	case "kind":
		_, bookID, err := s.bookToolAuthAmbient(ctx, in.BookID, grantclient.GrantManage)
		if err != nil {
			return nil, setGenresToolOut{}, err
		}
		out, err := s.setKindGenresCore(ctx, bookID, in.KindCode, in.Add, in.Remove)
		if err != nil {
			return nil, setGenresToolOut{}, err
		}
		return nil, setGenresToolOut{Target: "kind", GenreCodes: out.GenreCodes}, nil
	case "entity":
		_, bookID, err := s.bookToolAuthAmbient(ctx, in.BookID, grantclient.GrantEdit)
		if err != nil {
			return nil, setGenresToolOut{}, err
		}
		out, err := s.setEntityGenresToolCore(ctx, bookID, in.EntityID, in.GenreCodes)
		if err != nil {
			return nil, setGenresToolOut{}, err
		}
		return nil, setGenresToolOut{Target: "entity", GenreIDs: out.GenreIDs, UsesBookDefault: out.UsesBookDefault}, nil
	default:
		return nil, setGenresToolOut{}, errors.New("target must be book_active, kind, or entity")
	}
}
