package api

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// T1 — book-tier MCP tools. Registered together via RegisterBookTools so the book
// stream owns its own file (the per-tier parallelism enabler — T2/T3 add sync_tools.go
// / user_tools.go without touching this). All wrap the shared cores (book_ontology_core.go,
// book_adopt_handler.go, entity_genres_handler.go) so the MCP and HTTP write paths agree.
//
// Gating: reads = GrantView; additive/reversible writes (create/patch, set-active/kind-
// genres deltas, entity-genres) = GrantManage/Edit direct (class W); adopt + delete =
// class C (confirm-token) via the generalized confirm spine.

// RegisterBookTools adds every book-tier tool to the user/book MCP server.
func (s *Server) RegisterBookTools(srv *mcp.Server) {
	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_book_ontology_read",
		Description: "Read a BOOK's local ontology: its adopted/native genres, kinds, attribute " +
			"definitions, and kind↔genre links. This is what entities in the book are described by. " +
			"Use before proposing entities or shaping the book's schema.",
	}, s.toolBookOntologyRead)

	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_adopt_standards",
		Description: "Propose ADOPTING System standards into a book — scaffolds the book's ontology by " +
			"copying the picked genres/kinds (+ their attributes & links) down into the book tier. " +
			"High-impact: it does NOT adopt; it returns a confirm_token + a preview of how many are new, " +
			"which a human confirms via glossary_confirm_action. `universal` genre + `unknown` kind are " +
			"always included. Args are genre/kind CODES (see glossary_list_system_standards).",
	}, s.toolAdoptStandards)

	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_book_create",
		Description: "Create a book-native genre, kind, or attribute (additive, takes effect immediately). " +
			"level=genre|kind|attribute + code + name (+ for attribute: kind_code & genre_code). Use " +
			"glossary_book_ontology_read first to avoid duplicating an existing code.",
	}, s.toolBookCreate)

	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_book_patch",
		Description: "Edit a book genre/kind/attribute in place. level + code identify the row; pass the " +
			"`base_version` you read from glossary_book_ontology_read so a concurrent edit is detected " +
			"(409 on drift). Only the fields you supply change.",
	}, s.toolBookPatch)

	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_book_delete",
		Description: "Propose DELETING a book's genre, kind, or attribute (soft-delete with cascade). " +
			"High-impact and destructive — it does NOT delete; it returns a confirm_token + a preview of " +
			"everything the cascade will remove, which a human must confirm via glossary_confirm_action. " +
			"Address by code: level=genre|kind|attribute + code (for attribute also kind_code + genre_code).",
	}, s.toolBookDelete)

	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_book_revert",
		Description: "Propose REVERTING a book genre/kind/attribute back to the System/User standard it was " +
			"adopted from — discards the book's local edits to this row and re-pulls the parent's CURRENT values. " +
			"It does NOT write; it returns a confirm_token + a preview of the parent it reverts to, which a human " +
			"confirms via glossary_confirm_action. Only works on adopted rows (not book-native ones). Address by " +
			"code: level=genre|kind|attribute + code (for attribute also kind_code + genre_code).",
	}, s.toolBookRevert)

	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_book_set_active_genres",
		Description: "Turn book genres on/off as active matrix columns by DELTA — `add` and/or `remove` " +
			"lists of genre codes. (Delta, not replace, so you never silently drop a column you didn't mention.)",
	}, s.toolBookSetActiveGenres)

	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_book_set_kind_genres",
		Description: "Wire a kind's genre links (matrix row) by DELTA — kind_code + `add`/`remove` lists " +
			"of genre codes. Adds or removes which genres' attributes apply to that kind.",
	}, s.toolBookSetKindGenres)

	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_entity_get_genres",
		Description: "Read one entity's genre override (which genres' attributes apply to it). Empty ⇒ the " +
			"entity follows the book's active genres.",
	}, s.toolEntityGetGenres)

	mcp.AddTool(srv, &mcp.Tool{
		Name: "glossary_entity_set_genres",
		Description: "Set one entity's genre override by CODE list (replaces the override; `universal` is " +
			"always included; an empty list clears back to the book default). Every code must be a live book genre.",
	}, s.toolEntitySetGenres)
}

const (
	bookLevelGenre = "genre"
	bookLevelKind  = "kind"
	bookLevelAttr  = "attribute"
)

// ── adopt (C) ─────────────────────────────────────────────────────────────────

type adoptToolIn struct {
	BookID string   `json:"book_id" jsonschema:"the book to scaffold (UUID)"`
	Genres []string `json:"genres,omitempty" jsonschema:"system genre codes to adopt (universal is always added)"`
	Kinds  []string `json:"kinds,omitempty" jsonschema:"system kind codes to adopt (unknown is always added)"`
}

func (s *Server) toolAdoptStandards(ctx context.Context, _ *mcp.CallToolRequest, in adoptToolIn) (*mcp.CallToolResult, confirmCardOut, error) {
	userID, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantManage)
	if err != nil {
		return nil, confirmCardOut{}, err
	}
	newGenres, newKinds, err := s.adoptCounts(ctx, bookID, in.Genres, in.Kinds)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("failed to preview the adopt")
	}
	rows := []previewRow{
		{Label: "genres newly adopted", Value: fmt.Sprint(newGenres), Note: "+ universal (always)"},
		{Label: "kinds newly adopted", Value: fmt.Sprint(newKinds), Note: "+ unknown (always)"},
	}
	return s.mintGrantActionCard(userID, bookID, descAdopt, "Adopt standards into this book",
		adoptParams{Genres: in.Genres, Kinds: in.Kinds}, rows, false)
}

// ── create (W) ────────────────────────────────────────────────────────────────

type bookCreateToolIn struct {
	BookID      string   `json:"book_id" jsonschema:"the book (UUID)"`
	Level       string   `json:"level" jsonschema:"genre | kind | attribute"`
	Code        string   `json:"code,omitempty" jsonschema:"machine code (derived from name if omitted)"`
	Name        string   `json:"name" jsonschema:"display name"`
	Description string   `json:"description,omitempty"`
	Icon        string   `json:"icon,omitempty"`
	Color       string   `json:"color,omitempty"`
	SortOrder   int      `json:"sort_order,omitempty"`
	IsHidden    bool     `json:"is_hidden,omitempty" jsonschema:"kind only"`
	KindCode    string   `json:"kind_code,omitempty" jsonschema:"attribute only: the kind it belongs to"`
	GenreCode   string   `json:"genre_code,omitempty" jsonschema:"attribute only: the genre cell (e.g. universal)"`
	FieldType   string   `json:"field_type,omitempty" jsonschema:"attribute only: text|textarea|select|number|date|tags|url|boolean"`
	IsRequired  bool     `json:"is_required,omitempty" jsonschema:"attribute only"`
	Options     []string `json:"options,omitempty" jsonschema:"attribute only: options for a select field"`
}

type bookWriteOut struct {
	Level   string `json:"level"`
	ID      string `json:"id"`
	Code    string `json:"code"`
	Version string `json:"base_version,omitempty"` // updated_at to pass to a follow-up patch
	Status  string `json:"status"`
}

func (s *Server) toolBookCreate(ctx context.Context, _ *mcp.CallToolRequest, in bookCreateToolIn) (*mcp.CallToolResult, bookWriteOut, error) {
	_, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantManage)
	if err != nil {
		return nil, bookWriteOut{}, err
	}
	desc := optStr(in.Description)
	switch strings.TrimSpace(in.Level) {
	case bookLevelGenre:
		g, err := s.createBookGenreCore(ctx, bookID, bookGenreCreateParams{Code: in.Code, Name: in.Name, Icon: in.Icon, Color: in.Color, SortOrder: in.SortOrder})
		if err != nil {
			return nil, bookWriteOut{}, bookCreateToolErr(err)
		}
		return nil, bookWriteOut{Level: bookLevelGenre, ID: g.GenreID, Code: g.Code, Status: "created"}, nil
	case bookLevelKind:
		k, err := s.createBookKindCore(ctx, bookID, bookKindCreateParams{Code: in.Code, Name: in.Name, Description: desc, Icon: in.Icon, Color: in.Color, SortOrder: in.SortOrder, IsHidden: in.IsHidden})
		if err != nil {
			return nil, bookWriteOut{}, bookCreateToolErr(err)
		}
		return nil, bookWriteOut{Level: bookLevelKind, ID: k.BookKindID, Code: k.Code, Status: "created"}, nil
	case bookLevelAttr:
		kindID, gErr := s.resolveBookKindID(ctx, bookID, strings.TrimSpace(in.KindCode))
		if isNoRows(gErr) {
			return nil, bookWriteOut{}, errors.New("no live kind with that kind_code in this book")
		} else if gErr != nil {
			return nil, bookWriteOut{}, errors.New("failed to resolve kind_code")
		}
		genreID, ge := s.resolveBookGenreID(ctx, bookID, strings.TrimSpace(in.GenreCode))
		if isNoRows(ge) {
			return nil, bookWriteOut{}, errors.New("no live genre with that genre_code in this book")
		} else if ge != nil {
			return nil, bookWriteOut{}, errors.New("failed to resolve genre_code")
		}
		a, err := s.createBookAttributeCore(ctx, bookID, bookAttrCreateParams{KindID: kindID, GenreID: genreID, Code: in.Code, Name: in.Name, Description: desc, FieldType: in.FieldType, IsRequired: in.IsRequired, SortOrder: in.SortOrder, Options: in.Options})
		if err != nil {
			return nil, bookWriteOut{}, bookCreateToolErr(err)
		}
		return nil, bookWriteOut{Level: bookLevelAttr, ID: a.AttrID, Code: a.Code, Status: "created"}, nil
	default:
		return nil, bookWriteOut{}, errors.New("level must be genre, kind, or attribute")
	}
}

// bookCreateToolErr maps the shared create-core sentinels to LLM-facing errors.
func bookCreateToolErr(err error) error {
	switch {
	case errors.Is(err, errDuplicateBookCode):
		return errors.New("a row with this code already exists")
	case errors.Is(err, errBookFKNotLive):
		return errors.New("kind_code or genre_code is not a live row of this book")
	case errors.Is(err, errInvalidFieldType):
		return errInvalidFieldType
	default:
		return err
	}
}

// ── patch (W, base-version) ───────────────────────────────────────────────────

type bookPatchToolIn struct {
	BookID      string    `json:"book_id" jsonschema:"the book (UUID)"`
	Level       string    `json:"level" jsonschema:"genre | kind | attribute"`
	Code        string    `json:"code" jsonschema:"the row's code"`
	KindCode    string    `json:"kind_code,omitempty" jsonschema:"attribute only"`
	GenreCode   string    `json:"genre_code,omitempty" jsonschema:"attribute only"`
	BaseVersion string    `json:"base_version,omitempty" jsonschema:"the updated_at you read; 409 if the row changed since"`
	Name        *string   `json:"name,omitempty"`
	Description *string   `json:"description,omitempty"`
	Icon        *string   `json:"icon,omitempty"`
	Color       *string   `json:"color,omitempty"`
	SortOrder   *int      `json:"sort_order,omitempty"`
	IsHidden    *bool     `json:"is_hidden,omitempty" jsonschema:"kind only"`
	FieldType   *string   `json:"field_type,omitempty" jsonschema:"attribute only"`
	IsRequired  *bool     `json:"is_required,omitempty" jsonschema:"attribute only"`
	Options     *[]string `json:"options,omitempty" jsonschema:"attribute only"`
}

func (s *Server) toolBookPatch(ctx context.Context, _ *mcp.CallToolRequest, in bookPatchToolIn) (*mcp.CallToolResult, bookWriteOut, error) {
	_, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantManage)
	if err != nil {
		return nil, bookWriteOut{}, err
	}
	level := strings.TrimSpace(in.Level)
	// Validate an attribute field_type before any write (no DB CHECK backstops it).
	if level == bookLevelAttr && in.FieldType != nil && !isValidFieldType(*in.FieldType) {
		return nil, bookWriteOut{}, errInvalidFieldType
	}
	table, idCol, id, fields, perr := s.resolveBookPatch(ctx, bookID, level, in)
	if perr != nil {
		return nil, bookWriteOut{}, perr
	}
	// Optimistic-concurrency: compare the caller's base_version to the live updated_at.
	cur, err := s.bookRowVersion(ctx, table, idCol, bookID, id)
	if err != nil {
		return nil, bookWriteOut{}, errors.New("the target no longer exists")
	}
	if cverr := compareBaseVersion(cur, strings.TrimSpace(in.BaseVersion)); cverr != nil {
		return nil, bookWriteOut{}, errors.New("the row changed since you read it (409) — re-read glossary_book_ontology_read and retry")
	}
	if len(fields) == 0 {
		return nil, bookWriteOut{}, errors.New("no editable fields supplied")
	}
	if err := s.applyBookUpdate(ctx, table, idCol, bookID, id, fields); err != nil {
		return nil, bookWriteOut{}, errors.New("update failed")
	}
	newVer, _ := s.bookRowVersion(ctx, table, idCol, bookID, id)
	return nil, bookWriteOut{Level: level, ID: id.String(), Code: strings.TrimSpace(in.Code), Version: newVer, Status: "patched"}, nil
}

// resolveBookPatch resolves the target row + builds the validated updateField set for
// the level (only fields valid for that level are accepted).
func (s *Server) resolveBookPatch(ctx context.Context, bookID uuid.UUID, level string, in bookPatchToolIn) (table, idCol string, id uuid.UUID, fields []updateField, err error) {
	add := func(col string, v any) { fields = append(fields, updateField{col, v}) }
	code := strings.TrimSpace(in.Code)
	switch level {
	case bookLevelGenre:
		id, err = s.resolveBookGenreID(ctx, bookID, code)
		table, idCol = "book_genres", "genre_id"
		if in.Name != nil {
			add("name", *in.Name)
		}
		if in.Icon != nil {
			add("icon", *in.Icon)
		}
		if in.Color != nil {
			add("color", *in.Color)
		}
		if in.SortOrder != nil {
			add("sort_order", *in.SortOrder)
		}
	case bookLevelKind:
		id, err = s.resolveBookKindID(ctx, bookID, code)
		table, idCol = "book_kinds", "book_kind_id"
		if in.Name != nil {
			add("name", *in.Name)
		}
		if in.Description != nil {
			add("description", in.Description)
		}
		if in.Icon != nil {
			add("icon", *in.Icon)
		}
		if in.Color != nil {
			add("color", *in.Color)
		}
		if in.SortOrder != nil {
			add("sort_order", *in.SortOrder)
		}
		if in.IsHidden != nil {
			add("is_hidden", *in.IsHidden)
		}
	case bookLevelAttr:
		id, err = s.resolveBookAttrID(ctx, bookID, strings.TrimSpace(in.KindCode), strings.TrimSpace(in.GenreCode), code)
		table, idCol = "book_attributes", "attr_id"
		if in.Name != nil {
			add("name", *in.Name)
		}
		if in.Description != nil {
			add("description", in.Description)
		}
		if in.FieldType != nil {
			add("field_type", *in.FieldType)
		}
		if in.IsRequired != nil {
			add("is_required", *in.IsRequired)
		}
		if in.SortOrder != nil {
			add("sort_order", *in.SortOrder)
		}
		if in.Options != nil {
			add("options", *in.Options)
		}
	default:
		return "", "", uuid.Nil, nil, errors.New("level must be genre, kind, or attribute")
	}
	if isNoRows(err) {
		return "", "", uuid.Nil, nil, errors.New("no live row with that code in this book")
	}
	if err != nil {
		return "", "", uuid.Nil, nil, errors.New("failed to resolve the target")
	}
	return table, idCol, id, fields, nil
}

func (s *Server) bookRowVersion(ctx context.Context, table, idCol string, bookID, id uuid.UUID) (string, error) {
	var ts time.Time
	// table/idCol are internal constants (never request input) → no injection.
	q := fmt.Sprintf("SELECT updated_at FROM %s WHERE book_id=$1 AND %s=$2 AND deprecated_at IS NULL", table, idCol)
	if err := s.pool.QueryRow(ctx, q, bookID, id).Scan(&ts); err != nil {
		return "", err
	}
	return ts.UTC().Format(time.RFC3339Nano), nil
}

// ── set-active-genres / set-kind-genres (W, delta) ────────────────────────────

type setActiveGenresToolIn struct {
	BookID string   `json:"book_id" jsonschema:"the book (UUID)"`
	Add    []string `json:"add,omitempty" jsonschema:"genre codes to activate"`
	Remove []string `json:"remove,omitempty" jsonschema:"genre codes to deactivate"`
}
type activeGenresToolOut struct {
	ActiveCodes []string `json:"active_codes"`
}

func (s *Server) toolBookSetActiveGenres(ctx context.Context, _ *mcp.CallToolRequest, in setActiveGenresToolIn) (*mcp.CallToolResult, activeGenresToolOut, error) {
	_, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantManage)
	if err != nil {
		return nil, activeGenresToolOut{}, err
	}
	addIDs, err := s.resolveGenreCodes(ctx, bookID, in.Add)
	if err != nil {
		return nil, activeGenresToolOut{}, err
	}
	remIDs, err := s.resolveGenreCodes(ctx, bookID, in.Remove)
	if err != nil {
		return nil, activeGenresToolOut{}, err
	}
	for _, gid := range addIDs {
		if _, err := s.pool.Exec(ctx, `INSERT INTO book_active_genres (book_id, genre_id) VALUES ($1,$2) ON CONFLICT DO NOTHING`, bookID, gid); err != nil {
			return nil, activeGenresToolOut{}, errors.New("activate failed")
		}
	}
	for _, gid := range remIDs {
		if _, err := s.pool.Exec(ctx, `DELETE FROM book_active_genres WHERE book_id=$1 AND genre_id=$2`, bookID, gid); err != nil {
			return nil, activeGenresToolOut{}, errors.New("deactivate failed")
		}
	}
	codes, err := s.activeGenreCodes(ctx, bookID)
	if err != nil {
		return nil, activeGenresToolOut{}, errors.New("reload failed")
	}
	return nil, activeGenresToolOut{ActiveCodes: codes}, nil
}

type setKindGenresToolIn struct {
	BookID   string   `json:"book_id" jsonschema:"the book (UUID)"`
	KindCode string   `json:"kind_code" jsonschema:"the kind whose genre links to change"`
	Add      []string `json:"add,omitempty" jsonschema:"genre codes to link"`
	Remove   []string `json:"remove,omitempty" jsonschema:"genre codes to unlink"`
}
type kindGenresToolOut struct {
	GenreCodes []string `json:"genre_codes"`
}

func (s *Server) toolBookSetKindGenres(ctx context.Context, _ *mcp.CallToolRequest, in setKindGenresToolIn) (*mcp.CallToolResult, kindGenresToolOut, error) {
	_, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantManage)
	if err != nil {
		return nil, kindGenresToolOut{}, err
	}
	kindID, kerr := s.resolveBookKindID(ctx, bookID, strings.TrimSpace(in.KindCode))
	if isNoRows(kerr) {
		return nil, kindGenresToolOut{}, errors.New("no live kind with that kind_code in this book")
	} else if kerr != nil {
		return nil, kindGenresToolOut{}, errors.New("failed to resolve kind_code")
	}
	addIDs, err := s.resolveGenreCodes(ctx, bookID, in.Add)
	if err != nil {
		return nil, kindGenresToolOut{}, err
	}
	remIDs, err := s.resolveGenreCodes(ctx, bookID, in.Remove)
	if err != nil {
		return nil, kindGenresToolOut{}, err
	}
	for _, gid := range addIDs {
		if _, err := s.pool.Exec(ctx, `INSERT INTO book_kind_genres (book_id, kind_id, genre_id) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING`, bookID, kindID, gid); err != nil {
			return nil, kindGenresToolOut{}, errors.New("link failed")
		}
	}
	for _, gid := range remIDs {
		if _, err := s.pool.Exec(ctx, `DELETE FROM book_kind_genres WHERE book_id=$1 AND kind_id=$2 AND genre_id=$3`, bookID, kindID, gid); err != nil {
			return nil, kindGenresToolOut{}, errors.New("unlink failed")
		}
	}
	codes, err := s.kindGenreCodes(ctx, bookID, kindID)
	if err != nil {
		return nil, kindGenresToolOut{}, errors.New("reload failed")
	}
	return nil, kindGenresToolOut{GenreCodes: codes}, nil
}

// ── entity-genres (R / W) ─────────────────────────────────────────────────────

type entityGenresGetToolIn struct {
	BookID   string `json:"book_id" jsonschema:"the book (UUID)"`
	EntityID string `json:"entity_id" jsonschema:"the entity (UUID)"`
}
type entityGenresToolOut struct {
	GenreIDs        []string `json:"genre_ids"`
	UsesBookDefault bool     `json:"uses_book_default"`
}

func (s *Server) toolEntityGetGenres(ctx context.Context, _ *mcp.CallToolRequest, in entityGenresGetToolIn) (*mcp.CallToolResult, entityGenresToolOut, error) {
	_, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantView)
	if err != nil {
		return nil, entityGenresToolOut{}, err
	}
	entityID, err := uuid.Parse(in.EntityID)
	if err != nil {
		return nil, entityGenresToolOut{}, errors.New("entity_id must be a UUID")
	}
	if ok, err := s.entityExistsInBook(ctx, entityID, bookID); err != nil {
		return nil, entityGenresToolOut{}, errors.New("lookup failed")
	} else if !ok {
		return nil, entityGenresToolOut{}, errors.New("entity not found in this book")
	}
	ids, err := s.getEntityGenreIDs(ctx, entityID)
	if err != nil {
		return nil, entityGenresToolOut{}, errors.New("query failed")
	}
	return nil, entityGenresToolOut{GenreIDs: ids, UsesBookDefault: len(ids) == 0}, nil
}

type entityGenresSetToolIn struct {
	BookID     string   `json:"book_id" jsonschema:"the book (UUID)"`
	EntityID   string   `json:"entity_id" jsonschema:"the entity (UUID)"`
	GenreCodes []string `json:"genre_codes,omitempty" jsonschema:"genre codes for the override; empty clears to book default"`
}

func (s *Server) toolEntitySetGenres(ctx context.Context, _ *mcp.CallToolRequest, in entityGenresSetToolIn) (*mcp.CallToolResult, entityGenresToolOut, error) {
	_, bookID, err := s.bookToolAuth(ctx, in.BookID, grantclient.GrantEdit)
	if err != nil {
		return nil, entityGenresToolOut{}, err
	}
	entityID, err := uuid.Parse(in.EntityID)
	if err != nil {
		return nil, entityGenresToolOut{}, errors.New("entity_id must be a UUID")
	}
	if ok, err := s.entityExistsInBook(ctx, entityID, bookID); err != nil {
		return nil, entityGenresToolOut{}, errors.New("lookup failed")
	} else if !ok {
		return nil, entityGenresToolOut{}, errors.New("entity not found in this book")
	}
	want, err := s.resolveGenreCodes(ctx, bookID, in.GenreCodes)
	if err != nil {
		return nil, entityGenresToolOut{}, err
	}
	resp, err := s.setEntityGenresCore(ctx, bookID, entityID, want)
	if err != nil {
		if errors.Is(err, errEntityGenreInvalid) || errors.Is(err, errBookNoUniversal) {
			return nil, entityGenresToolOut{}, err
		}
		return nil, entityGenresToolOut{}, errors.New("set genres failed")
	}
	return nil, entityGenresToolOut{GenreIDs: resp.GenreIDs, UsesBookDefault: resp.UsesBookDefault}, nil
}

// ── shared helpers ────────────────────────────────────────────────────────────

// bookToolAuth resolves the caller identity + parses book_id + checks the grant —
// the common preamble for every book tool. Returns uniform ownership errors (H13).
func (s *Server) bookToolAuth(ctx context.Context, rawBookID string, level grantclient.GrantLevel) (uuid.UUID, uuid.UUID, error) {
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return uuid.Nil, uuid.Nil, errors.New("missing caller identity")
	}
	bookID, err := uuid.Parse(rawBookID)
	if err != nil {
		return uuid.Nil, uuid.Nil, errors.New("book_id must be a UUID")
	}
	if err := s.checkGrant(ctx, bookID, userID, level); err != nil {
		return uuid.Nil, uuid.Nil, uniformOwnershipError(err)
	}
	return userID, bookID, nil
}

// resolveGenreCodes maps book-genre codes to ids, rejecting any that isn't a live
// genre of the book (tenancy — no silent skip).
func (s *Server) resolveGenreCodes(ctx context.Context, bookID uuid.UUID, codes []string) ([]uuid.UUID, error) {
	out := make([]uuid.UUID, 0, len(codes))
	for _, c := range codes {
		c = strings.TrimSpace(c)
		if c == "" {
			continue
		}
		id, err := s.resolveBookGenreID(ctx, bookID, c)
		if isNoRows(err) {
			return nil, fmt.Errorf("no live genre with code %q in this book", c)
		}
		if err != nil {
			return nil, errors.New("failed to resolve a genre code")
		}
		out = append(out, id)
	}
	return out, nil
}

func (s *Server) activeGenreCodes(ctx context.Context, bookID uuid.UUID) ([]string, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT bg.code FROM book_active_genres ag
		JOIN book_genres bg ON bg.genre_id = ag.genre_id
		WHERE ag.book_id=$1 AND bg.deprecated_at IS NULL
		ORDER BY bg.sort_order, bg.code`, bookID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanCodeList(rows)
}

func (s *Server) kindGenreCodes(ctx context.Context, bookID, kindID uuid.UUID) ([]string, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT bg.code FROM book_kind_genres kg
		JOIN book_genres bg ON bg.genre_id = kg.genre_id
		WHERE kg.book_id=$1 AND kg.kind_id=$2 AND bg.deprecated_at IS NULL
		ORDER BY bg.sort_order, bg.code`, bookID, kindID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanCodeList(rows)
}

func optStr(s string) *string {
	if t := strings.TrimSpace(s); t != "" {
		return &t
	}
	return nil
}

// scanCodeList collects a single-text-column result into a slice.
func scanCodeList(rows interface {
	Next() bool
	Scan(...any) error
	Err() error
}) ([]string, error) {
	out := []string{}
	for rows.Next() {
		var c string
		if err := rows.Scan(&c); err != nil {
			return nil, err
		}
		out = append(out, c)
	}
	return out, rows.Err()
}
