package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	lwmcp "github.com/loreweave/loreweave_mcp"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// T4 — System-tier admin MCP tools. Registered on the SEPARATE /mcp/admin server
// (admin_mcp_server.go) only — they never appear on /mcp (INV-T6). Every write is
// class C: the tool PROPOSES (mints an authorityAdmin confirm token + preview, no
// write); a human admin confirms via the RS256-gated /v1/glossary/actions/admin/confirm.
// There is deliberately NO admin tool that writes directly — the LLM can never mutate
// the shared System tier (the LOCKED tenancy rule: human admin is the authority).
//
// Authority = the RS256 admin token verified at the transport (adminSubFromCtx), NOT
// X-User-Id (INV-T2). Tools are code-addressed (System codes are globally unique).

// RegisterAdminTools adds every System-tier admin tool to the admin MCP server.
func (s *Server) RegisterAdminTools(srv *mcp.Server) {
	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_admin_standards_read",
		Description: "Read the SYSTEM standards catalogue you administer: system genres + kinds (and, with " +
			"kind_code + genre_code, the attributes for that cell). These are the platform-wide defaults every " +
			"book can adopt. Read before proposing any System change.",
		// System-tier read, no scope key (addressed by code, System-wide).
		Meta: lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeNone, nil, nil),
	}, s.toolAdminStandardsRead)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_admin_propose_create",
		Description: "Propose CREATING a System-tier genre, kind, or attribute (the shared platform defaults). " +
			"High-impact and shared across ALL users — it does NOT write; it returns a confirm_token + preview " +
			"a human admin must confirm. level=genre|kind|attribute + name (+ for attribute: kind_code & genre_code).",
		InputSchema: closedSetSchemaFor[adminCreateToolIn](map[string][]any{
			"level": enumLevels, "field_type": enumFieldTypes,
		}),
		// Mints an admin confirm_token (no direct write) ⇒ Tier W. System-tier ⇒ no scope key.
		Meta: lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeNone, nil, nil),
	}, s.toolAdminProposeCreate)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_admin_propose_patch",
		Description: "Propose EDITING a System-tier genre/kind/attribute in place. level + code identify the row " +
			"(attribute also needs kind_code + genre_code). Returns a confirm_token + preview a human admin confirms. " +
			"Only the fields you supply change. The edit refreshes content_hash so adopted books see it via Sync.",
		InputSchema: closedSetSchemaFor[adminPatchToolIn](map[string][]any{
			"level": enumLevels, "field_type": enumFieldTypes,
		}),
		Meta: lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeNone, nil, nil),
	}, s.toolAdminProposePatch)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_admin_propose_delete",
		Description: "Propose DELETING a System-tier genre/kind/attribute. level + code (attribute also needs " +
			"kind_code + genre_code). High-impact, shared — returns a confirm_token + preview a human admin confirms. " +
			"`universal` genre and `unknown` kind are never deletable. Deletes are SOFT — the row moves to the recycle " +
			"bin and can be restored with glossary_admin_propose_restore.",
		InputSchema: closedSetSchemaFor[adminDeleteToolIn](map[string][]any{"level": enumLevels}),
		Meta:        lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeNone, nil, nil),
	}, s.toolAdminProposeDelete)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_admin_propose_restore",
		Description: "Propose RESTORING a soft-deleted System-tier genre/kind/attribute from the recycle bin. " +
			"level + code (attribute also needs kind_code + genre_code). Returns a confirm_token + preview a human " +
			"admin confirms. Only works on a row currently in the recycle bin; restoring an attribute requires its " +
			"parent kind & genre to be live (restore those first).",
		InputSchema: closedSetSchemaFor[adminDeleteToolIn](map[string][]any{"level": enumLevels}),
		Meta:        lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeNone, nil, nil),
	}, s.toolAdminProposeRestore)
}

const (
	adminLevelGenre = "genre"
	adminLevelKind  = "kind"
	adminLevelAttr  = "attribute"
)

// mintAdminActionCard mints an authorityAdmin confirm token bound to the admin subject
// + descriptor + jti, and returns the confirm card. An empty token = the JWT secret is
// missing (fail closed). Authority shows as "admin" so the FE routes it to the admin
// confirm endpoint.
func (s *Server) mintAdminActionCard(adminSub, descriptor, title string, params any, rows []previewRow, destructive bool) (*mcp.CallToolResult, confirmCardOut, error) {
	raw, err := json.Marshal(params)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("failed to encode proposal")
	}
	now := time.Now()
	token := mintActionToken(s.cfg.JWTSecret, actionClaims{
		JTI: uuid.NewString(), Authority: authorityAdmin, AdminSub: adminSub,
		Descriptor: descriptor, Params: raw,
	}, now)
	if token == "" {
		return nil, confirmCardOut{}, errors.New("confirmation is unavailable")
	}
	return nil, confirmCardOut{
		ConfirmToken: token, Descriptor: descriptor, Authority: authorityAdmin,
		Title: title, PreviewRows: rows, Destructive: destructive,
		ExpiresAt: now.Add(actionTokenTTL).UTC().Format(time.RFC3339),
	}, nil
}

// ── read (R) ──────────────────────────────────────────────────────────────────

type adminStandardsReadToolIn struct {
	KindCode  string `json:"kind_code,omitempty" jsonschema:"with genre_code, also list System attributes for that cell"`
	GenreCode string `json:"genre_code,omitempty" jsonschema:"with kind_code, also list System attributes for that cell"`
}

type adminStandardsOut struct {
	Genres     []genreResp      `json:"genres"`
	Kinds      []systemKindResp `json:"kinds"`
	Attributes []attributeResp  `json:"attributes"`
}

func (s *Server) toolAdminStandardsRead(ctx context.Context, _ *mcp.CallToolRequest, in adminStandardsReadToolIn) (*mcp.CallToolResult, adminStandardsOut, error) {
	if _, ok := adminSubFromCtx(ctx); !ok {
		return nil, adminStandardsOut{}, errors.New("missing admin identity")
	}
	out := adminStandardsOut{Genres: []genreResp{}, Kinds: []systemKindResp{}, Attributes: []attributeResp{}}

	grows, err := s.pool.Query(ctx, `SELECT genre_id::text, code, name, icon, color, sort_order, created_at, updated_at
		FROM system_genres WHERE deprecated_at IS NULL ORDER BY sort_order, code`)
	if err != nil {
		return nil, adminStandardsOut{}, errors.New("system genres query failed")
	}
	defer grows.Close()
	for grows.Next() {
		var g genreResp
		g.Tier = "system"
		if err := grows.Scan(&g.GenreID, &g.Code, &g.Name, &g.Icon, &g.Color, &g.SortOrder, &g.CreatedAt, &g.UpdatedAt); err != nil {
			return nil, adminStandardsOut{}, errors.New("genre scan failed")
		}
		out.Genres = append(out.Genres, g)
	}
	if err := grows.Err(); err != nil {
		return nil, adminStandardsOut{}, errors.New("genre rows error")
	}

	krows, err := s.pool.Query(ctx, `SELECT kind_id::text, code, name, description, icon, color, is_hidden, sort_order
		FROM system_kinds WHERE deprecated_at IS NULL ORDER BY sort_order, code`)
	if err != nil {
		return nil, adminStandardsOut{}, errors.New("system kinds query failed")
	}
	defer krows.Close()
	for krows.Next() {
		k := systemKindResp{Tier: "system"}
		if err := krows.Scan(&k.KindID, &k.Code, &k.Name, &k.Description, &k.Icon, &k.Color, &k.IsHidden, &k.SortOrder); err != nil {
			return nil, adminStandardsOut{}, errors.New("kind scan failed")
		}
		out.Kinds = append(out.Kinds, k)
	}
	if err := krows.Err(); err != nil {
		return nil, adminStandardsOut{}, errors.New("kind rows error")
	}

	kc, gc := strings.TrimSpace(in.KindCode), strings.TrimSpace(in.GenreCode)
	if kc != "" && gc != "" {
		kindID, kerr := s.resolveSystemKindID(ctx, kc)
		genreID, gerr := s.resolveSystemGenreID(ctx, gc)
		if isNoRows(kerr) || isNoRows(gerr) {
			return nil, out, nil // unknown cell → no attributes, not an error
		}
		if kerr != nil || gerr != nil {
			return nil, adminStandardsOut{}, errors.New("failed to resolve the kind×genre cell")
		}
		arows, err := s.pool.Query(ctx, `SELECT `+attrDefCols+` FROM system_attributes
			WHERE kind_id=$1 AND genre_id=$2 AND deprecated_at IS NULL ORDER BY sort_order, code`, kindID, genreID)
		if err != nil {
			return nil, adminStandardsOut{}, errors.New("system attributes query failed")
		}
		defer arows.Close()
		for arows.Next() {
			var a attributeResp
			a.Tier = "system"
			if err := arows.Scan(&a.AttrID, &a.KindID, &a.GenreID, &a.Code, &a.Name, &a.Description,
				&a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options, &a.AutoFillPrompt, &a.TranslationHint); err != nil {
				return nil, adminStandardsOut{}, errors.New("attribute scan failed")
			}
			if a.Options == nil {
				a.Options = []string{}
			}
			out.Attributes = append(out.Attributes, a)
		}
		if err := arows.Err(); err != nil {
			return nil, adminStandardsOut{}, errors.New("attribute rows error")
		}
	}
	return nil, out, nil
}

// ── propose create / patch / delete (C) ───────────────────────────────────────

type adminCreateToolIn struct {
	Level       string   `json:"level" jsonschema:"genre | kind | attribute"`
	Code        string   `json:"code,omitempty" jsonschema:"machine code (derived from name if omitted)"`
	Name        string   `json:"name" jsonschema:"display name"`
	Description string   `json:"description,omitempty"`
	Icon        string   `json:"icon,omitempty"`
	Color       string   `json:"color,omitempty"`
	SortOrder   int      `json:"sort_order,omitempty"`
	IsHidden    bool     `json:"is_hidden,omitempty" jsonschema:"kind only"`
	KindCode    string   `json:"kind_code,omitempty" jsonschema:"attribute only: the System kind it attaches to"`
	GenreCode   string   `json:"genre_code,omitempty" jsonschema:"attribute only: the System genre cell"`
	FieldType       string   `json:"field_type,omitempty" jsonschema:"attribute only: text|textarea|select|number|date|tags|url|boolean"`
	IsRequired      bool     `json:"is_required,omitempty" jsonschema:"attribute only"`
	Options         []string `json:"options,omitempty" jsonschema:"attribute only"`
	AutoFillPrompt  string   `json:"auto_fill_prompt,omitempty" jsonschema:"attribute only: how the AI auto-fills this attribute from chapter text"`
	TranslationHint string   `json:"translation_hint,omitempty" jsonschema:"attribute only: guidance injected when translating this attribute's value"`
}

func (s *Server) toolAdminProposeCreate(ctx context.Context, _ *mcp.CallToolRequest, in adminCreateToolIn) (*mcp.CallToolResult, confirmCardOut, error) {
	adminSub, ok := adminSubFromCtx(ctx)
	if !ok {
		return nil, confirmCardOut{}, errors.New("missing admin identity")
	}
	level := strings.TrimSpace(in.Level)
	name := strings.TrimSpace(in.Name)
	if name == "" {
		return nil, confirmCardOut{}, errors.New("name is required")
	}
	if level == adminLevelAttr {
		if strings.TrimSpace(in.KindCode) == "" || strings.TrimSpace(in.GenreCode) == "" {
			return nil, confirmCardOut{}, errors.New("kind_code and genre_code are required for an attribute")
		}
		if in.FieldType != "" && !isValidFieldType(in.FieldType) {
			return nil, confirmCardOut{}, errInvalidFieldType
		}
		// Mint-time validation (§11 #8): the kind×genre cell must exist now.
		if _, err := s.resolveSystemKindID(ctx, strings.TrimSpace(in.KindCode)); isNoRows(err) {
			return nil, confirmCardOut{}, errors.New("no System kind with that kind_code")
		} else if err != nil {
			return nil, confirmCardOut{}, errors.New("failed to resolve kind_code")
		}
		if _, err := s.resolveSystemGenreID(ctx, strings.TrimSpace(in.GenreCode)); isNoRows(err) {
			return nil, confirmCardOut{}, errors.New("no System genre with that genre_code")
		} else if err != nil {
			return nil, confirmCardOut{}, errors.New("failed to resolve genre_code")
		}
	} else if level != adminLevelGenre && level != adminLevelKind {
		return nil, confirmCardOut{}, errors.New("level must be genre, kind, or attribute")
	}
	p := systemActionParams{
		Level: level, Code: strings.TrimSpace(in.Code), Name: name, Description: in.Description,
		Icon: in.Icon, Color: in.Color, SortOrder: in.SortOrder, IsHidden: in.IsHidden,
		KindCode: strings.TrimSpace(in.KindCode), GenreCode: strings.TrimSpace(in.GenreCode),
		FieldType: in.FieldType, IsRequired: in.IsRequired, Options: in.Options,
		AutoFillPrompt: in.AutoFillPrompt, TranslationHint: in.TranslationHint,
	}
	rows := []previewRow{{Label: "level", Value: level}, {Label: "name", Value: name}}
	if p.Code != "" {
		rows = append(rows, previewRow{Label: "code", Value: p.Code})
	}
	return s.mintAdminActionCard(adminSub, descSystemCreate,
		fmt.Sprintf("Create System %s %q", level, name), p, rows, false)
}

type adminPatchToolIn struct {
	Level       string    `json:"level" jsonschema:"genre | kind | attribute"`
	Code        string    `json:"code" jsonschema:"the row's code"`
	KindCode    string    `json:"kind_code,omitempty" jsonschema:"attribute only"`
	GenreCode   string    `json:"genre_code,omitempty" jsonschema:"attribute only"`
	Name        *string   `json:"name,omitempty"`
	Description *string   `json:"description,omitempty"`
	Icon        *string   `json:"icon,omitempty"`
	Color       *string   `json:"color,omitempty"`
	SortOrder   *int      `json:"sort_order,omitempty"`
	IsHidden    *bool     `json:"is_hidden,omitempty" jsonschema:"kind only"`
	FieldType       *string   `json:"field_type,omitempty" jsonschema:"attribute only"`
	IsRequired      *bool     `json:"is_required,omitempty" jsonschema:"attribute only"`
	Options         *[]string `json:"options,omitempty" jsonschema:"attribute only"`
	AutoFillPrompt  *string   `json:"auto_fill_prompt,omitempty" jsonschema:"attribute only"`
	TranslationHint *string   `json:"translation_hint,omitempty" jsonschema:"attribute only"`
}

func (s *Server) toolAdminProposePatch(ctx context.Context, _ *mcp.CallToolRequest, in adminPatchToolIn) (*mcp.CallToolResult, confirmCardOut, error) {
	adminSub, ok := adminSubFromCtx(ctx)
	if !ok {
		return nil, confirmCardOut{}, errors.New("missing admin identity")
	}
	level := strings.TrimSpace(in.Level)
	code := strings.TrimSpace(in.Code)
	if code == "" {
		return nil, confirmCardOut{}, errors.New("code is required")
	}
	if level == adminLevelAttr && in.FieldType != nil && !isValidFieldType(*in.FieldType) {
		return nil, confirmCardOut{}, errInvalidFieldType
	}
	if err := s.adminProposeResolvable(ctx, level, code, in.KindCode, in.GenreCode); err != nil {
		return nil, confirmCardOut{}, err
	}
	p := systemActionParams{
		Level: level, Code: code, KindCode: strings.TrimSpace(in.KindCode), GenreCode: strings.TrimSpace(in.GenreCode),
		PatchName: in.Name, PatchDescription: in.Description, PatchIcon: in.Icon, PatchColor: in.Color,
		PatchSortOrder: in.SortOrder, PatchIsHidden: in.IsHidden, PatchFieldType: in.FieldType,
		PatchIsRequired: in.IsRequired, PatchOptions: in.Options,
		PatchAutoFillPrompt: in.AutoFillPrompt, PatchTranslationHint: in.TranslationHint,
	}
	rows := []previewRow{{Label: "level", Value: level}, {Label: "code", Value: code}}
	res, out, err := s.mintAdminActionCard(adminSub, descSystemPatch,
		fmt.Sprintf("Edit System %s %q", level, code), p, rows, false)
	// External MCP discoverability audit #11 — every Patch* field is a pointer (nil =
	// unchanged, per systemActionParams' doc comment). If none were supplied, the patch
	// changes nothing (effectSystemPatch/patchSystem*Core have nothing to apply).
	if err == nil && in.Name == nil && in.Description == nil && in.Icon == nil && in.Color == nil &&
		in.SortOrder == nil && in.IsHidden == nil && in.FieldType == nil && in.IsRequired == nil &&
		in.Options == nil && in.AutoFillPrompt == nil && in.TranslationHint == nil {
		out.Warning = "no fields were given to patch — this will change nothing"
	}
	return res, out, err
}

type adminDeleteToolIn struct {
	Level     string `json:"level" jsonschema:"genre | kind | attribute"`
	Code      string `json:"code" jsonschema:"the row's code"`
	KindCode  string `json:"kind_code,omitempty" jsonschema:"attribute only"`
	GenreCode string `json:"genre_code,omitempty" jsonschema:"attribute only"`
}

func (s *Server) toolAdminProposeDelete(ctx context.Context, _ *mcp.CallToolRequest, in adminDeleteToolIn) (*mcp.CallToolResult, confirmCardOut, error) {
	adminSub, ok := adminSubFromCtx(ctx)
	if !ok {
		return nil, confirmCardOut{}, errors.New("missing admin identity")
	}
	level := strings.TrimSpace(in.Level)
	code := strings.TrimSpace(in.Code)
	if code == "" {
		return nil, confirmCardOut{}, errors.New("code is required")
	}
	if err := s.adminProposeResolvable(ctx, level, code, in.KindCode, in.GenreCode); err != nil {
		return nil, confirmCardOut{}, err
	}
	p := systemActionParams{Level: level, Code: code, KindCode: strings.TrimSpace(in.KindCode), GenreCode: strings.TrimSpace(in.GenreCode)}
	rows := []previewRow{{Label: "level", Value: level}, {Label: "code", Value: code}, {Label: "action", Value: "delete", Note: "shared System default"}}
	return s.mintAdminActionCard(adminSub, descSystemDelete,
		fmt.Sprintf("Delete System %s %q", level, code), p, rows, true)
}

// toolAdminProposeRestore proposes restoring a soft-deleted System row (G-C8). Reuses the
// delete tool's input shape (level/code + kind_code/genre_code for attrs). Mint-time it
// asserts the row is currently in the recycle bin; confirm-time the restore core enforces
// the parent-liveness guard.
func (s *Server) toolAdminProposeRestore(ctx context.Context, _ *mcp.CallToolRequest, in adminDeleteToolIn) (*mcp.CallToolResult, confirmCardOut, error) {
	adminSub, ok := adminSubFromCtx(ctx)
	if !ok {
		return nil, confirmCardOut{}, errors.New("missing admin identity")
	}
	level := strings.TrimSpace(in.Level)
	code := strings.TrimSpace(in.Code)
	if code == "" {
		return nil, confirmCardOut{}, errors.New("code is required")
	}
	if err := s.adminProposeRestorable(ctx, level, code, in.KindCode, in.GenreCode); err != nil {
		return nil, confirmCardOut{}, err
	}
	p := systemActionParams{Level: level, Code: code, KindCode: strings.TrimSpace(in.KindCode), GenreCode: strings.TrimSpace(in.GenreCode)}
	rows := []previewRow{{Label: "level", Value: level}, {Label: "code", Value: code}, {Label: "action", Value: "restore", Note: "from recycle bin"}}
	return s.mintAdminActionCard(adminSub, descSystemRestore,
		fmt.Sprintf("Restore System %s %q", level, code), p, rows, false)
}

// adminProposeRestorable validates (mint-time) that the addressed System row exists AND is
// currently soft-deleted (in the recycle bin). Restoring a live row is a no-op the agent
// should not propose. Confirm-time re-validation still runs in the restore core.
func (s *Server) adminProposeRestorable(ctx context.Context, level, code, kindCode, genreCode string) error {
	var deprecated bool
	var err error
	switch level {
	case adminLevelGenre:
		err = s.pool.QueryRow(ctx, `SELECT deprecated_at IS NOT NULL FROM system_genres WHERE code=$1`, code).Scan(&deprecated)
	case adminLevelKind:
		err = s.pool.QueryRow(ctx, `SELECT deprecated_at IS NOT NULL FROM system_kinds WHERE code=$1`, code).Scan(&deprecated)
	case adminLevelAttr:
		kc, gc := strings.TrimSpace(kindCode), strings.TrimSpace(genreCode)
		if kc == "" || gc == "" {
			return errors.New("kind_code and genre_code are required for an attribute")
		}
		id, rerr := s.resolveSystemAttrID(ctx, kc, gc, code)
		if isNoRows(rerr) {
			return fmt.Errorf("no System %s with that code", level)
		}
		if rerr != nil {
			return errors.New("failed to resolve the target")
		}
		err = s.pool.QueryRow(ctx, `SELECT deprecated_at IS NOT NULL FROM system_attributes WHERE attr_id=$1`, id).Scan(&deprecated)
	default:
		return errors.New("level must be genre, kind, or attribute")
	}
	if isNoRows(err) {
		return fmt.Errorf("no System %s with that code", level)
	}
	if err != nil {
		return errors.New("failed to resolve the target")
	}
	if !deprecated {
		return fmt.Errorf("System %s %q is not in the recycle bin", level, code)
	}
	return nil
}

// adminProposeResolvable validates (mint-time, §11 #8) that the addressed System row
// exists now, so the agent never shows a card destined to 4xx. Confirm-time
// re-resolution still runs in the effect.
func (s *Server) adminProposeResolvable(ctx context.Context, level, code, kindCode, genreCode string) error {
	var err error
	switch level {
	case adminLevelGenre:
		_, err = s.resolveSystemGenreID(ctx, code)
	case adminLevelKind:
		_, err = s.resolveSystemKindID(ctx, code)
	case adminLevelAttr:
		if strings.TrimSpace(kindCode) == "" || strings.TrimSpace(genreCode) == "" {
			return errors.New("kind_code and genre_code are required for an attribute")
		}
		_, err = s.resolveSystemAttrID(ctx, strings.TrimSpace(kindCode), strings.TrimSpace(genreCode), code)
	default:
		return errors.New("level must be genre, kind, or attribute")
	}
	if isNoRows(err) {
		return fmt.Errorf("no System %s with that code", level)
	}
	if err != nil {
		return errors.New("failed to resolve the target")
	}
	return nil
}
