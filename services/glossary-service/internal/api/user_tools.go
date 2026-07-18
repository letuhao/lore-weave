package api

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	lwmcp "github.com/loreweave/loreweave_mcp"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// T3 — user-tier standards MCP tools. The agent helps a user build a reusable
// personal standards library (their own genres/kinds/attributes) that books can
// later adopt. Registered together via RegisterUserTools (append-only, the per-tier
// parallelism enabler).
//
// AUTHORITY (§4a): user-tier is OWNER-SCOPED, not book-scoped — the gate is simply
// "X-User-Id IS the owner", no grant/book lookup. Every query filters on the caller's
// user id (the tenancy chokepoint). In a shared book a grantee's user-tier tools act
// on the GRANTEE's own library (§11 #11), so descriptions say "your personal standards".
//
// CLASS: reads = R; create/patch/delete/restore = W (direct) — deletes are soft
// (trash), reversible via glossary_user_restore, so they are W not C (§3c). Patches
// carry a base_version (content_hash for genre/attribute, updated_at for kind) and
// 409 on drift (§12.6). Every semantic write refreshes content_hash so G5 Sync can
// detect the edit downstream (D-GKA-HASH-REFRESH).
//
// SCOPE NOTE: clone-from-system is intentionally NOT exposed here (the dedicated
// standards UI / adopt flow owns that copy-down). The agent builds the library by
// reading system standards (glossary_list_system_standards) and creating equivalents.

const (
	userLevelGenre = "genre"
	userLevelKind  = "kind"
	userLevelAttr  = "attribute"
)

// RegisterUserTools adds every user-tier tool to the user/book MCP server.
func (s *Server) RegisterUserTools(srv *mcp.Server) {
	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_user_standards_read",
		Description: "Read YOUR personal standards library — your user-tier genres and kinds (reusable " +
			"across your books). Pass kind_code + genre_code to also list your attributes for that cell. " +
			"These are private to you; other users never see them.",
		Meta: lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeUser, nil, nil),
	}, s.toolUserStandardsRead)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_user_create",
		Description: "Create a genre, kind, or attribute in YOUR personal standards library (additive, " +
			"takes effect immediately). level=genre|kind|attribute + name (+ code, derived from name if " +
			"omitted). For an attribute: kind_code & genre_code identify which of YOUR kind×genre cells it " +
			"attaches to (both must already be your user-tier rows). " +
			"NOTE: superseded by glossary_ontology_upsert — kept for existing callers only.",
		InputSchema: closedSetSchemaFor[userCreateToolIn](map[string][]any{
			"level": enumLevels, "field_type": enumFieldTypes,
		}),
		Meta: lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, nil), lwmcp.VisibilityLegacy),
	}, s.toolUserCreate)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_user_patch",
		Description: "Edit one of YOUR user-tier genre/kind/attributes in place. level + code identify the " +
			"row (attribute also needs kind_code + genre_code). Pass the base_version you read from " +
			"glossary_user_standards_read so a concurrent edit is detected (409 on drift). Only supplied fields change. " +
			"NOTE: superseded by glossary_ontology_upsert — kept for existing callers only.",
		InputSchema: closedSetSchemaFor[userPatchToolIn](map[string][]any{
			"level": enumLevels, "field_type": enumFieldTypes,
		}),
		Meta: lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, nil), lwmcp.VisibilityLegacy),
	}, s.toolUserPatch)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_user_delete",
		Description: "Move one of YOUR user-tier genre/kind/attributes to the trash (soft-delete, REVERSIBLE " +
			"via glossary_user_restore). level + code (attribute also needs kind_code + genre_code). A genre " +
			"still linked to a kind or carrying attributes can't be trashed until those are removed. " +
			"NOTE: superseded by glossary_ontology_delete — kept for existing callers only.",
		InputSchema: closedSetSchemaFor[userDeleteToolIn](map[string][]any{"level": enumLevels}),
		Meta:        lwmcp.WithVisibility(lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, nil), lwmcp.VisibilityLegacy),
	}, s.toolUserDelete)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_user_restore",
		Description: "Restore one of YOUR user-tier genre/kind/attributes from the trash (undo a " +
			"glossary_user_delete). level + code (attribute also needs kind_code + genre_code).",
		InputSchema: closedSetSchemaFor[userDeleteToolIn](map[string][]any{"level": enumLevels}),
		// Direct, reversible write (undo a soft-delete) ⇒ Tier A, matching create/patch/delete.
		Meta: lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeUser, nil, nil),
	}, s.toolUserRestore)
}

// ── shared preamble ───────────────────────────────────────────────────────────

// userToolCaller resolves the caller identity — the only gate for user-tier tools
// (owner == caller; no book/grant lookup). Every query then filters owner_user_id.
func userToolCaller(ctx context.Context) (uuid.UUID, error) {
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return uuid.Nil, errors.New("missing caller identity")
	}
	return userID, nil
}

// ── owner-scoped code → id resolvers (live rows only) ─────────────────────────

func (s *Server) resolveUserGenreID(ctx context.Context, userID uuid.UUID, code string) (uuid.UUID, error) {
	var id uuid.UUID
	err := s.pool.QueryRow(ctx,
		`SELECT genre_id FROM user_genres
		 WHERE owner_user_id=$1 AND code=$2 AND deleted_at IS NULL AND permanently_deleted_at IS NULL`,
		userID, code).Scan(&id)
	return id, err
}

func (s *Server) resolveUserKindID(ctx context.Context, userID uuid.UUID, code string) (uuid.UUID, error) {
	var id uuid.UUID
	err := s.pool.QueryRow(ctx,
		`SELECT user_kind_id FROM user_kinds
		 WHERE owner_user_id=$1 AND code=$2 AND deleted_at IS NULL AND permanently_deleted_at IS NULL`,
		userID, code).Scan(&id)
	return id, err
}

// resolveUserAttrID resolves a user attribute by (kind_code, genre_code, code) within
// the caller's tier — attribute codes are unique only within a (kind × genre) cell.
func (s *Server) resolveUserAttrID(ctx context.Context, userID uuid.UUID, kindCode, genreCode, code string) (uuid.UUID, error) {
	kindID, err := s.resolveUserKindID(ctx, userID, kindCode)
	if err != nil {
		return uuid.Nil, err
	}
	genreID, err := s.resolveUserGenreID(ctx, userID, genreCode)
	if err != nil {
		return uuid.Nil, err
	}
	var id uuid.UUID
	err = s.pool.QueryRow(ctx,
		`SELECT attr_id FROM user_attributes
		 WHERE owner_user_id=$1 AND kind_id=$2 AND genre_id=$3 AND code=$4 AND deleted_at IS NULL`,
		userID, kindID, genreID, code).Scan(&id)
	return id, err
}

// ── read (R) ──────────────────────────────────────────────────────────────────

type userStandardsReadToolIn struct {
	KindCode  string `json:"kind_code,omitempty" jsonschema:"with genre_code, also list your attributes for that cell"`
	GenreCode string `json:"genre_code,omitempty" jsonschema:"with kind_code, also list your attributes for that cell"`
}

type userStandardsOut struct {
	Genres     []userGenreRow  `json:"genres"`
	Kinds      []userKindBrief `json:"kinds"`
	Attributes []userAttrRow   `json:"attributes"`
}

// userGenreRow / userAttrRow embed the rich resp + the base_version (content_hash)
// the agent passes back to glossary_user_patch for optimistic-concurrency (§12.6).
// Without it on the READ, a patch could only opt out of the 409 check.
type userGenreRow struct {
	genreResp
	BaseVersion string `json:"base_version"`
}

type userAttrRow struct {
	attributeResp
	BaseVersion string `json:"base_version"`
}

type userKindBrief struct {
	UserKindID  string  `json:"user_kind_id"`
	Code        string  `json:"code"`
	Name        string  `json:"name"`
	Description *string `json:"description,omitempty"`
	BaseVersion string  `json:"base_version"` // updated_at — pass to glossary_user_patch
}

func (s *Server) toolUserStandardsRead(ctx context.Context, _ *mcp.CallToolRequest, in userStandardsReadToolIn) (*mcp.CallToolResult, userStandardsOut, error) {
	userID, err := userToolCaller(ctx)
	if err != nil {
		return nil, userStandardsOut{}, err
	}
	out := userStandardsOut{Genres: []userGenreRow{}, Kinds: []userKindBrief{}, Attributes: []userAttrRow{}}

	grows, err := s.pool.Query(ctx, `
		SELECT genre_id::text, owner_user_id::text, code, name, icon, color, sort_order,
		       cloned_from_genre_id::text, content_hash, created_at, updated_at
		FROM user_genres
		WHERE owner_user_id=$1 AND deleted_at IS NULL AND permanently_deleted_at IS NULL
		ORDER BY sort_order, code`, userID)
	if err != nil {
		return nil, userStandardsOut{}, errors.New("genres query failed")
	}
	defer grows.Close()
	for grows.Next() {
		var row userGenreRow
		row.Tier = "user"
		if err := grows.Scan(&row.GenreID, &row.OwnerUserID, &row.Code, &row.Name, &row.Icon, &row.Color, &row.SortOrder,
			&row.ClonedFromGenreID, &row.BaseVersion, &row.CreatedAt, &row.UpdatedAt); err != nil {
			return nil, userStandardsOut{}, errors.New("genre scan failed")
		}
		out.Genres = append(out.Genres, row)
	}
	if err := grows.Err(); err != nil {
		return nil, userStandardsOut{}, errors.New("genre rows error")
	}

	krows, err := s.pool.Query(ctx, `
		SELECT user_kind_id::text, code, name, description, updated_at
		FROM user_kinds
		WHERE owner_user_id=$1 AND deleted_at IS NULL AND permanently_deleted_at IS NULL
		ORDER BY code`, userID)
	if err != nil {
		return nil, userStandardsOut{}, errors.New("kinds query failed")
	}
	defer krows.Close()
	for krows.Next() {
		var k userKindBrief
		var updatedAt time.Time
		if err := krows.Scan(&k.UserKindID, &k.Code, &k.Name, &k.Description, &updatedAt); err != nil {
			return nil, userStandardsOut{}, errors.New("kind scan failed")
		}
		k.BaseVersion = updatedAt.UTC().Format(time.RFC3339Nano)
		out.Kinds = append(out.Kinds, k)
	}
	if err := krows.Err(); err != nil {
		return nil, userStandardsOut{}, errors.New("kind rows error")
	}

	// Attributes only when a specific cell is named (they are keyed by kind × genre).
	kc, gc := strings.TrimSpace(in.KindCode), strings.TrimSpace(in.GenreCode)
	if kc != "" && gc != "" {
		kindID, kerr := s.resolveUserKindID(ctx, userID, kc)
		genreID, gerr := s.resolveUserGenreID(ctx, userID, gc)
		if isNoRows(kerr) || isNoRows(gerr) {
			return nil, out, nil // unknown cell → no attributes, not an error
		}
		if kerr != nil || gerr != nil {
			return nil, userStandardsOut{}, errors.New("failed to resolve the kind×genre cell")
		}
		arows, err := s.pool.Query(ctx,
			`SELECT `+attrDefCols+`, content_hash FROM user_attributes
			 WHERE owner_user_id=$1 AND kind_id=$2 AND genre_id=$3 AND deleted_at IS NULL
			 ORDER BY sort_order, code`, userID, kindID, genreID)
		if err != nil {
			return nil, userStandardsOut{}, errors.New("attributes query failed")
		}
		defer arows.Close()
		for arows.Next() {
			var row userAttrRow
			row.Tier = "user"
			if err := arows.Scan(&row.AttrID, &row.KindID, &row.GenreID, &row.Code, &row.Name, &row.Description,
				&row.FieldType, &row.IsRequired, &row.SortOrder, &row.Options, &row.AutoFillPrompt, &row.TranslationHint,
				&row.BaseVersion); err != nil {
				return nil, userStandardsOut{}, errors.New("attribute scan failed")
			}
			if row.Options == nil {
				row.Options = []string{}
			}
			out.Attributes = append(out.Attributes, row)
		}
		if err := arows.Err(); err != nil {
			return nil, userStandardsOut{}, errors.New("attribute rows error")
		}
	}
	return nil, out, nil
}

// ── create (W) ────────────────────────────────────────────────────────────────

type userCreateToolIn struct {
	Level       string   `json:"level" jsonschema:"genre | kind | attribute"`
	Code        string   `json:"code,omitempty" jsonschema:"machine code (derived from name if omitted)"`
	Name        string   `json:"name" jsonschema:"display name"`
	Description string   `json:"description,omitempty"`
	Icon        string   `json:"icon,omitempty"`
	Color       string   `json:"color,omitempty"`
	SortOrder   int      `json:"sort_order,omitempty"`
	IsPerson    bool     `json:"is_person,omitempty" jsonschema:"kind only: mark this kind a REAL person (colleague/self/client) — excludes its entities from AI wiki-gen + enrichment (carried into the book on adopt)"`
	KindCode    string   `json:"kind_code,omitempty" jsonschema:"attribute only: your user-tier kind it attaches to"`
	GenreCode   string   `json:"genre_code,omitempty" jsonschema:"attribute only: your user-tier genre cell"`
	FieldType       string   `json:"field_type,omitempty" jsonschema:"attribute only: text|textarea|select|number|date|tags|url|boolean — omit this argument for the default; do not send an empty string"`
	IsRequired      bool     `json:"is_required,omitempty" jsonschema:"attribute only"`
	Options         []string `json:"options,omitempty" jsonschema:"attribute only: options for a select field"`
	AutoFillPrompt  string   `json:"auto_fill_prompt,omitempty" jsonschema:"attribute only: how the AI auto-fills this attribute from chapter text"`
	TranslationHint string   `json:"translation_hint,omitempty" jsonschema:"attribute only: guidance injected when translating this attribute's value"`
}

type userWriteOut struct {
	Level       string `json:"level"`
	ID          string `json:"id"`
	Code        string `json:"code"`
	BaseVersion string `json:"base_version,omitempty"` // pass to a follow-up patch
	Status      string `json:"status"`
}

func (s *Server) toolUserCreate(ctx context.Context, _ *mcp.CallToolRequest, in userCreateToolIn) (*mcp.CallToolResult, userWriteOut, error) {
	userID, err := userToolCaller(ctx)
	if err != nil {
		return nil, userWriteOut{}, err
	}
	name := strings.TrimSpace(in.Name)
	if name == "" {
		return nil, userWriteOut{}, errors.New("name is required")
	}
	code := strings.TrimSpace(in.Code)
	if code == "" {
		code = slugify(name)
	}
	if code == "" {
		return nil, userWriteOut{}, errors.New("code could not be derived from name")
	}
	switch strings.TrimSpace(in.Level) {
	case userLevelGenre:
		return s.createUserGenreTool(ctx, userID, code, name, in)
	case userLevelKind:
		return s.createUserKindTool(ctx, userID, code, name, in)
	case userLevelAttr:
		return s.createUserAttrTool(ctx, userID, code, name, in)
	default:
		return nil, userWriteOut{}, errors.New("level must be genre, kind, or attribute")
	}
}

func (s *Server) createUserGenreTool(ctx context.Context, userID uuid.UUID, code, name string, in userCreateToolIn) (*mcp.CallToolResult, userWriteOut, error) {
	icon, color := in.Icon, in.Color
	if color == "" {
		color = "#6366f1"
	}
	var id uuid.UUID
	var hash string
	err := s.pool.QueryRow(ctx, `
		INSERT INTO user_genres (owner_user_id, code, name, icon, color, sort_order, content_hash)
		VALUES ($1,$2,$3,$4,$5,$6, md5($2||'|'||$3))
		RETURNING genre_id, content_hash`,
		userID, code, name, icon, color, in.SortOrder).Scan(&id, &hash)
	if err != nil {
		if isUniqueViolation(err) {
			return nil, userWriteOut{}, errors.New("a user genre with this code already exists")
		}
		return nil, userWriteOut{}, errors.New("create failed")
	}
	return nil, userWriteOut{Level: userLevelGenre, ID: id.String(), Code: code, BaseVersion: hash, Status: "created"}, nil
}

func (s *Server) createUserKindTool(ctx context.Context, userID uuid.UUID, code, name string, in userCreateToolIn) (*mcp.CallToolResult, userWriteOut, error) {
	icon, color := in.Icon, in.Color
	if icon == "" {
		icon = "box"
	}
	if color == "" {
		color = "#6366f1"
	}
	var id uuid.UUID
	var updatedAt time.Time
	err := s.pool.QueryRow(ctx, `
		INSERT INTO user_kinds (owner_user_id, code, name, description, icon, color, is_person)
		VALUES ($1,$2,$3,$4,$5,$6,$7)
		RETURNING user_kind_id, updated_at`,
		userID, code, name, optStr(in.Description), icon, color, in.IsPerson).Scan(&id, &updatedAt)
	if err != nil {
		if isUniqueViolation(err) {
			return nil, userWriteOut{}, errors.New("a user kind with this code already exists")
		}
		return nil, userWriteOut{}, errors.New("create failed")
	}
	return nil, userWriteOut{Level: userLevelKind, ID: id.String(), Code: code,
		BaseVersion: updatedAt.UTC().Format(time.RFC3339Nano), Status: "created"}, nil
}

func (s *Server) createUserAttrTool(ctx context.Context, userID uuid.UUID, code, name string, in userCreateToolIn) (*mcp.CallToolResult, userWriteOut, error) {
	kindCode, genreCode := strings.TrimSpace(in.KindCode), strings.TrimSpace(in.GenreCode)
	if kindCode == "" || genreCode == "" {
		return nil, userWriteOut{}, errors.New("kind_code and genre_code are required for an attribute")
	}
	fieldType := in.FieldType
	if fieldType == "" {
		fieldType = "text"
	}
	if !isValidFieldType(fieldType) {
		return nil, userWriteOut{}, errInvalidFieldType
	}
	kindID, kerr := s.resolveUserKindID(ctx, userID, kindCode)
	if isNoRows(kerr) {
		return nil, userWriteOut{}, errors.New("kind_code is not your user-tier kind (create it first)")
	} else if kerr != nil {
		return nil, userWriteOut{}, errors.New("failed to resolve kind_code")
	}
	genreID, gerr := s.resolveUserGenreID(ctx, userID, genreCode)
	if isNoRows(gerr) {
		return nil, userWriteOut{}, errors.New("genre_code is not your user-tier genre (create it first)")
	} else if gerr != nil {
		return nil, userWriteOut{}, errors.New("failed to resolve genre_code")
	}
	desc := optStr(in.Description)
	hash := attrContentHash(code, name, desc, fieldType, in.IsRequired, in.Options)
	var id uuid.UUID
	err := s.pool.QueryRow(ctx, `
		INSERT INTO user_attributes
		  (owner_user_id, kind_id, genre_id, code, name, description, field_type, is_required, sort_order, options, auto_fill_prompt, translation_hint, content_hash, merge_strategy)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
		RETURNING attr_id`,
		userID, kindID, genreID, code, name, desc, fieldType, in.IsRequired, in.SortOrder, in.Options, optStr(in.AutoFillPrompt), optStr(in.TranslationHint), hash, seedMergeStrategy(code, fieldType, in.IsRequired)).Scan(&id)
	if err != nil {
		if isUniqueViolation(err) {
			return nil, userWriteOut{}, errors.New("an attribute with this code already exists on this kind×genre")
		}
		return nil, userWriteOut{}, errors.New("create failed")
	}
	return nil, userWriteOut{Level: userLevelAttr, ID: id.String(), Code: code, BaseVersion: hash, Status: "created"}, nil
}

// ── patch (W, base-version) ───────────────────────────────────────────────────

type userPatchToolIn struct {
	Level       string    `json:"level" jsonschema:"genre | kind | attribute"`
	Code        string    `json:"code" jsonschema:"the row's code"`
	KindCode    string    `json:"kind_code,omitempty" jsonschema:"attribute only"`
	GenreCode   string    `json:"genre_code,omitempty" jsonschema:"attribute only"`
	BaseVersion string    `json:"base_version,omitempty" jsonschema:"the base_version you read; 409 if the row changed since"`
	Name        *string   `json:"name,omitempty"`
	Description *string   `json:"description,omitempty"`
	Icon        *string   `json:"icon,omitempty"`
	Color       *string   `json:"color,omitempty"`
	SortOrder   *int      `json:"sort_order,omitempty"`
	FieldType       *string   `json:"field_type,omitempty" jsonschema:"attribute only — omit this argument to leave it unchanged; do not send an empty string"`
	IsRequired      *bool     `json:"is_required,omitempty" jsonschema:"attribute only"`
	Options         *[]string `json:"options,omitempty" jsonschema:"attribute only"`
	AutoFillPrompt  *string   `json:"auto_fill_prompt,omitempty" jsonschema:"attribute only"`
	TranslationHint *string   `json:"translation_hint,omitempty" jsonschema:"attribute only"`
}

func (s *Server) toolUserPatch(ctx context.Context, _ *mcp.CallToolRequest, in userPatchToolIn) (*mcp.CallToolResult, userWriteOut, error) {
	userID, err := userToolCaller(ctx)
	if err != nil {
		return nil, userWriteOut{}, err
	}
	code := strings.TrimSpace(in.Code)
	if code == "" {
		return nil, userWriteOut{}, errors.New("code is required")
	}
	switch strings.TrimSpace(in.Level) {
	case userLevelGenre:
		return s.patchUserGenreTool(ctx, userID, code, in)
	case userLevelKind:
		return s.patchUserKindTool(ctx, userID, code, in)
	case userLevelAttr:
		return s.patchUserAttrTool(ctx, userID, code, in)
	default:
		return nil, userWriteOut{}, errors.New("level must be genre, kind, or attribute")
	}
}

func (s *Server) patchUserGenreTool(ctx context.Context, userID uuid.UUID, code string, in userPatchToolIn) (*mcp.CallToolResult, userWriteOut, error) {
	id, rerr := s.resolveUserGenreID(ctx, userID, code)
	if isNoRows(rerr) {
		return nil, userWriteOut{}, errors.New("no live user genre with that code")
	} else if rerr != nil {
		return nil, userWriteOut{}, errors.New("failed to resolve the genre")
	}
	var curHash string
	if err := s.pool.QueryRow(ctx, `SELECT content_hash FROM user_genres WHERE genre_id=$1`, id).Scan(&curHash); err != nil {
		return nil, userWriteOut{}, errors.New("the target no longer exists")
	}
	if cverr := compareBaseVersion(curHash, strings.TrimSpace(in.BaseVersion)); cverr != nil {
		return nil, userWriteOut{}, errUserPatchConflict(curHash)
	}
	fields := []updateField{}
	if in.Name != nil {
		fields = append(fields, updateField{"name", strings.TrimSpace(*in.Name)})
	}
	if in.Icon != nil {
		fields = append(fields, updateField{"icon", *in.Icon})
	}
	if in.Color != nil {
		fields = append(fields, updateField{"color", *in.Color})
	}
	if in.SortOrder != nil {
		fields = append(fields, updateField{"sort_order", *in.SortOrder})
	}
	if len(fields) == 0 {
		return nil, userWriteOut{}, errors.New("no editable fields supplied")
	}
	// Recompute content_hash = md5(code|name) so G5 Sync detects a name edit (code is
	// immutable). Done after the field UPDATE via the live row values.
	if err := s.applyUserUpdate(ctx, "user_genres", "genre_id", userID, id, fields, true); err != nil {
		return nil, userWriteOut{}, errors.New("update failed")
	}
	var newHash string
	if err := s.pool.QueryRow(ctx,
		`UPDATE user_genres SET content_hash = md5(code||'|'||name) WHERE genre_id=$1 AND owner_user_id=$2 RETURNING content_hash`,
		id, userID).Scan(&newHash); err != nil {
		return nil, userWriteOut{}, errors.New("content-hash refresh failed")
	}
	return nil, userWriteOut{Level: userLevelGenre, ID: id.String(), Code: code, BaseVersion: newHash, Status: "patched"}, nil
}

func (s *Server) patchUserKindTool(ctx context.Context, userID uuid.UUID, code string, in userPatchToolIn) (*mcp.CallToolResult, userWriteOut, error) {
	id, rerr := s.resolveUserKindID(ctx, userID, code)
	if isNoRows(rerr) {
		return nil, userWriteOut{}, errors.New("no live user kind with that code")
	} else if rerr != nil {
		return nil, userWriteOut{}, errors.New("failed to resolve the kind")
	}
	var curUpdated time.Time
	if err := s.pool.QueryRow(ctx, `SELECT updated_at FROM user_kinds WHERE user_kind_id=$1`, id).Scan(&curUpdated); err != nil {
		return nil, userWriteOut{}, errors.New("the target no longer exists")
	}
	if cverr := compareBaseVersion(curUpdated.UTC().Format(time.RFC3339Nano), strings.TrimSpace(in.BaseVersion)); cverr != nil {
		return nil, userWriteOut{}, errUserPatchConflict(curUpdated.UTC().Format(time.RFC3339Nano))
	}
	fields := []updateField{}
	if in.Name != nil {
		fields = append(fields, updateField{"name", strings.TrimSpace(*in.Name)})
	}
	if in.Description != nil {
		fields = append(fields, updateField{"description", in.Description})
	}
	if in.Icon != nil {
		fields = append(fields, updateField{"icon", *in.Icon})
	}
	if in.Color != nil {
		fields = append(fields, updateField{"color", *in.Color})
	}
	if len(fields) == 0 {
		return nil, userWriteOut{}, errors.New("no editable fields supplied")
	}
	if err := s.applyUserUpdate(ctx, "user_kinds", "user_kind_id", userID, id, fields, true); err != nil {
		return nil, userWriteOut{}, errors.New("update failed")
	}
	var newUpdated time.Time
	if err := s.pool.QueryRow(ctx, `SELECT updated_at FROM user_kinds WHERE user_kind_id=$1`, id).Scan(&newUpdated); err != nil {
		return nil, userWriteOut{}, errors.New("reload failed")
	}
	return nil, userWriteOut{Level: userLevelKind, ID: id.String(), Code: code,
		BaseVersion: newUpdated.UTC().Format(time.RFC3339Nano), Status: "patched"}, nil
}

func (s *Server) patchUserAttrTool(ctx context.Context, userID uuid.UUID, code string, in userPatchToolIn) (*mcp.CallToolResult, userWriteOut, error) {
	kindCode, genreCode := strings.TrimSpace(in.KindCode), strings.TrimSpace(in.GenreCode)
	if kindCode == "" || genreCode == "" {
		return nil, userWriteOut{}, errors.New("kind_code and genre_code are required to patch an attribute")
	}
	if in.FieldType != nil && !isValidFieldType(*in.FieldType) {
		return nil, userWriteOut{}, errInvalidFieldType
	}
	id, rerr := s.resolveUserAttrID(ctx, userID, kindCode, genreCode, code)
	if isNoRows(rerr) {
		return nil, userWriteOut{}, errors.New("no live user attribute with that code in this kind×genre")
	} else if rerr != nil {
		return nil, userWriteOut{}, errors.New("failed to resolve the attribute")
	}
	var curHash string
	if err := s.pool.QueryRow(ctx, `SELECT content_hash FROM user_attributes WHERE attr_id=$1`, id).Scan(&curHash); err != nil {
		return nil, userWriteOut{}, errors.New("the target no longer exists")
	}
	if cverr := compareBaseVersion(curHash, strings.TrimSpace(in.BaseVersion)); cverr != nil {
		return nil, userWriteOut{}, errUserPatchConflict(curHash)
	}
	fields := []updateField{}
	if in.Name != nil {
		fields = append(fields, updateField{"name", strings.TrimSpace(*in.Name)})
	}
	if in.Description != nil {
		fields = append(fields, updateField{"description", in.Description})
	}
	if in.FieldType != nil {
		fields = append(fields, updateField{"field_type", *in.FieldType})
	}
	if in.IsRequired != nil {
		fields = append(fields, updateField{"is_required", *in.IsRequired})
	}
	if in.SortOrder != nil {
		fields = append(fields, updateField{"sort_order", *in.SortOrder})
	}
	if in.Options != nil {
		fields = append(fields, updateField{"options", *in.Options})
	}
	if in.AutoFillPrompt != nil {
		fields = append(fields, updateField{"auto_fill_prompt", in.AutoFillPrompt})
	}
	if in.TranslationHint != nil {
		fields = append(fields, updateField{"translation_hint", in.TranslationHint})
	}
	if len(fields) == 0 {
		return nil, userWriteOut{}, errors.New("no editable fields supplied")
	}
	// user_attributes has NO updated_at column (only created_at/deleted_at), so do
	// not touch it here — unlike user_genres/user_kinds.
	if err := s.applyUserUpdate(ctx, "user_attributes", "attr_id", userID, id, fields, false); err != nil {
		return nil, userWriteOut{}, errors.New("update failed")
	}
	// Recompute content_hash from post-update fields (D-GKA-HASH-REFRESH).
	var a attributeResp
	if err := s.pool.QueryRow(ctx, `SELECT `+attrDefCols+` FROM user_attributes WHERE attr_id=$1`, id).
		Scan(&a.AttrID, &a.KindID, &a.GenreID, &a.Code, &a.Name, &a.Description,
			&a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options, &a.AutoFillPrompt, &a.TranslationHint); err != nil {
		return nil, userWriteOut{}, errors.New("reload failed")
	}
	newHash := attrContentHash(a.Code, a.Name, a.Description, a.FieldType, a.IsRequired, a.Options)
	if _, err := s.pool.Exec(ctx, `UPDATE user_attributes SET content_hash=$1 WHERE attr_id=$2 AND owner_user_id=$3`, newHash, id, userID); err != nil {
		return nil, userWriteOut{}, errors.New("content-hash refresh failed")
	}
	return nil, userWriteOut{Level: userLevelAttr, ID: id.String(), Code: code, BaseVersion: newHash, Status: "patched"}, nil
}

// errUserPatchConflict builds the user-tier 409 with the row's CURRENT
// base_version embedded, so the model retries in ONE step (W0 #1a) instead of
// re-reading the whole standards library (or looping a hallucinated value).
func errUserPatchConflict(current string) error {
	return fmt.Errorf(
		"the row changed since you read it (409) — its current base_version is %s; retry the same patch with base_version=%q",
		current, current)
}

// applyUserUpdate runs an owner-scoped UPDATE of the validated fields. table/idCol are
// internal constants (never request input) → no injection; owner_user_id in the WHERE
// is the tenancy gate. touchUpdatedAt adds `updated_at = now()` — true for user_genres/
// user_kinds, FALSE for user_attributes (which has no updated_at column).
func (s *Server) applyUserUpdate(ctx context.Context, table, idCol string, userID, id uuid.UUID, fields []updateField, touchUpdatedAt bool) error {
	set := make([]string, 0, len(fields)+1)
	args := make([]any, 0, len(fields)+2)
	n := 1
	for _, f := range fields {
		set = append(set, fmt.Sprintf("%s = $%d", f.col, n))
		args = append(args, f.val)
		n++
	}
	if touchUpdatedAt {
		set = append(set, "updated_at = now()")
	}
	q := fmt.Sprintf("UPDATE %s SET %s WHERE %s = $%d AND owner_user_id = $%d AND deleted_at IS NULL",
		table, strings.Join(set, ", "), idCol, n, n+1)
	args = append(args, id, userID)
	tag, err := s.pool.Exec(ctx, q, args...)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return errors.New("not found")
	}
	return nil
}

// ── delete (W, soft → trash) / restore (W) ────────────────────────────────────

type userDeleteToolIn struct {
	Level     string `json:"level" jsonschema:"genre | kind | attribute"`
	Code      string `json:"code" jsonschema:"the row's code"`
	KindCode  string `json:"kind_code,omitempty" jsonschema:"attribute only"`
	GenreCode string `json:"genre_code,omitempty" jsonschema:"attribute only"`
}

func (s *Server) toolUserDelete(ctx context.Context, _ *mcp.CallToolRequest, in userDeleteToolIn) (*mcp.CallToolResult, userWriteOut, error) {
	return s.userTrashTransition(ctx, in, true)
}

func (s *Server) toolUserRestore(ctx context.Context, _ *mcp.CallToolRequest, in userDeleteToolIn) (*mcp.CallToolResult, userWriteOut, error) {
	return s.userTrashTransition(ctx, in, false)
}

// userTrashTransition soft-deletes (trash=true) or restores (trash=false) a user-tier
// row, code-addressed and owner-scoped. Restore resolves among TRASHED rows; delete
// among LIVE rows (a genre still referenced can't be trashed — 409-style guard).
func (s *Server) userTrashTransition(ctx context.Context, in userDeleteToolIn, trash bool) (*mcp.CallToolResult, userWriteOut, error) {
	userID, err := userToolCaller(ctx)
	if err != nil {
		return nil, userWriteOut{}, err
	}
	code := strings.TrimSpace(in.Code)
	if code == "" {
		return nil, userWriteOut{}, errors.New("code is required")
	}
	level := strings.TrimSpace(in.Level)
	status := "restored"
	if trash {
		status = "trashed"
	}
	switch level {
	case userLevelGenre:
		if trash {
			if err := s.userGenreDeletable(ctx, userID, code); err != nil {
				return nil, userWriteOut{}, err
			}
		}
		id, err := s.toggleUserTrash(ctx, "user_genres", "genre_id", userID, code, trash, true)
		return userTrashResult(userLevelGenre, code, id, status, err)
	case userLevelKind:
		id, err := s.toggleUserTrash(ctx, "user_kinds", "user_kind_id", userID, code, trash, true)
		return userTrashResult(userLevelKind, code, id, status, err)
	case userLevelAttr:
		return s.userAttrTrash(ctx, userID, in, trash, status)
	default:
		return nil, userWriteOut{}, errors.New("level must be genre, kind, or attribute")
	}
}

// userGenreDeletable enforces the same in-use guard the HTTP delete uses: a genre
// linked to a user-kind or carrying live attributes can't be trashed.
func (s *Server) userGenreDeletable(ctx context.Context, userID uuid.UUID, code string) error {
	id, rerr := s.resolveUserGenreID(ctx, userID, code)
	if isNoRows(rerr) {
		return errors.New("no live user genre with that code")
	} else if rerr != nil {
		return errors.New("failed to resolve the genre")
	}
	var refs int
	if err := s.pool.QueryRow(ctx,
		`SELECT (SELECT COUNT(*) FROM user_kind_genres WHERE genre_id=$1)
		      + (SELECT COUNT(*) FROM user_attributes WHERE genre_id=$1 AND deleted_at IS NULL)`,
		id).Scan(&refs); err != nil {
		return errors.New("reference check failed")
	}
	if refs > 0 {
		return fmt.Errorf("%d kind-links/attributes reference this genre; remove them first", refs)
	}
	return nil
}

// toggleUserTrash flips deleted_at for a code-addressed owner-scoped row. hasPurgeCol
// adds the permanently_deleted_at IS NULL guard (genres/kinds have it; attributes don't).
func (s *Server) toggleUserTrash(ctx context.Context, table, idCol string, userID uuid.UUID, code string, trash, hasPurgeCol bool) (uuid.UUID, error) {
	purge := ""
	if hasPurgeCol {
		purge = " AND permanently_deleted_at IS NULL"
	}
	var setExpr, delGuard string
	if trash {
		setExpr, delGuard = "deleted_at = now()", "deleted_at IS NULL"
	} else {
		setExpr, delGuard = "deleted_at = NULL", "deleted_at IS NOT NULL"
	}
	q := fmt.Sprintf(
		"UPDATE %s SET %s, updated_at = now() WHERE code=$1 AND owner_user_id=$2 AND %s%s RETURNING %s",
		table, setExpr, delGuard, purge, idCol)
	var id uuid.UUID
	err := s.pool.QueryRow(ctx, q, code, userID).Scan(&id)
	return id, err
}

func (s *Server) userAttrTrash(ctx context.Context, userID uuid.UUID, in userDeleteToolIn, trash bool, status string) (*mcp.CallToolResult, userWriteOut, error) {
	kindCode, genreCode := strings.TrimSpace(in.KindCode), strings.TrimSpace(in.GenreCode)
	if kindCode == "" || genreCode == "" {
		return nil, userWriteOut{}, errors.New("kind_code and genre_code are required for an attribute")
	}
	kindID, kerr := s.resolveUserKindID(ctx, userID, kindCode)
	if isNoRows(kerr) {
		return nil, userWriteOut{}, errors.New("kind_code is not your user-tier kind")
	} else if kerr != nil {
		return nil, userWriteOut{}, errors.New("failed to resolve kind_code")
	}
	genreID, gerr := s.resolveUserGenreID(ctx, userID, genreCode)
	if isNoRows(gerr) {
		return nil, userWriteOut{}, errors.New("genre_code is not your user-tier genre")
	} else if gerr != nil {
		return nil, userWriteOut{}, errors.New("failed to resolve genre_code")
	}
	delGuard := "deleted_at IS NULL"
	setExpr := "deleted_at = now()"
	if !trash {
		delGuard, setExpr = "deleted_at IS NOT NULL", "deleted_at = NULL"
	}
	q := fmt.Sprintf(
		`UPDATE user_attributes SET %s WHERE owner_user_id=$1 AND kind_id=$2 AND genre_id=$3 AND code=$4 AND %s RETURNING attr_id`,
		setExpr, delGuard)
	var id uuid.UUID
	err := s.pool.QueryRow(ctx, q, userID, kindID, genreID, strings.TrimSpace(in.Code)).Scan(&id)
	return userTrashResult(userLevelAttr, strings.TrimSpace(in.Code), id, status, err)
}

func userTrashResult(level, code string, id uuid.UUID, status string, err error) (*mcp.CallToolResult, userWriteOut, error) {
	if isNoRows(err) {
		if status == "restored" {
			return nil, userWriteOut{}, fmt.Errorf("no trashed %s with that code to restore", level)
		}
		return nil, userWriteOut{}, fmt.Errorf("no live %s with that code to trash", level)
	}
	if err != nil {
		return nil, userWriteOut{}, errors.New("operation failed")
	}
	return nil, userWriteOut{Level: level, ID: id.String(), Code: code, Status: status}, nil
}
