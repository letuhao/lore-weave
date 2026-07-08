package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// Class-C propose MCP tools (gateway-routed). Each MINTS a generalized action
// confirm token (no write) + returns a confirm-card payload (spec §13.6) the LLM
// hands to the glossary_confirm_action frontend tool; a human reviews and confirms,
// which calls the token-gated /v1/glossary/actions/{confirm,preview} endpoints.
// There is deliberately NO MCP tool that performs the write directly — a buggy or
// compromised consumer routing through the gateway can mint but never mutate.

// previewRow is one line of a confirm card's human-readable preview.
type previewRow struct {
	Label string `json:"label"`
	Value string `json:"value"`
	Note  string `json:"note,omitempty"`
	// OpID + Destructive are set for execute_plan previews (one row per plan op): the
	// FE renders an opt-in enable toggle, keyed by OpID, on each Destructive row and
	// sends the checked ids back as enabled_ops at confirm (§4 G1). Empty/false for
	// non-plan single-action previews (unchanged).
	OpID        string `json:"op_id,omitempty"`
	Destructive bool   `json:"destructive,omitempty"`
}

// confirmCardOut is the propose result fed to the LLM and rendered by the FE
// confirm card (descriptor-keyed). preview_rows are the at-mint snapshot; the FE
// re-fetches current-state rows via /actions/preview before the human confirms.
type confirmCardOut struct {
	ConfirmToken string       `json:"confirm_token"`
	Descriptor   string       `json:"descriptor"`
	Authority    string       `json:"authority"`
	Title        string       `json:"title"`
	PreviewRows  []previewRow `json:"preview_rows"`
	Destructive  bool         `json:"destructive"`
	ExpiresAt    string       `json:"expires_at"`
	// Warning (external MCP discoverability audit #11) — set when the propose call is a
	// genuine no-op (a valid, confirmable token that would change nothing). Without this,
	// a caller that doesn't read preview_rows' counts closely could confirm a token that
	// accomplishes nothing and believe an action succeeded.
	Warning string `json:"warning,omitempty"`
}

// mintGrantActionCard marshals params, mints a grant-authority action token bound
// to user+book+descriptor+jti, and returns the confirm card. An empty token means
// the JWT secret is missing (fail closed — no proposal can proceed).
func (s *Server) mintGrantActionCard(userID, bookID uuid.UUID, descriptor, title string, params any, rows []previewRow, destructive bool) (*mcp.CallToolResult, confirmCardOut, error) {
	raw, err := json.Marshal(params)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("failed to encode proposal")
	}
	now := time.Now()
	token := mintActionToken(s.cfg.JWTSecret, actionClaims{
		JTI: uuid.NewString(), Authority: authorityGrant, UserID: userID,
		BookID: bookID, Descriptor: descriptor, Params: raw,
	}, now)
	if token == "" {
		return nil, confirmCardOut{}, errors.New("confirmation is unavailable")
	}
	return nil, confirmCardOut{
		ConfirmToken: token, Descriptor: descriptor, Authority: authorityGrant,
		Title: title, PreviewRows: rows, Destructive: destructive,
		ExpiresAt: now.Add(actionTokenTTL).UTC().Format(time.RFC3339),
	}, nil
}

// ── schema create (migrated from the retired schema-confirm path) ─────────────

type proposeKindToolIn struct {
	BookID      string   `json:"book_id" jsonschema:"the book whose schema to extend (UUID; ownership-checked)"`
	Code        string   `json:"code" jsonschema:"machine code for the kind, e.g. power_system"`
	Name        string   `json:"name" jsonschema:"display name, e.g. Power System"`
	Description string   `json:"description,omitempty" jsonschema:"optional description"`
	Icon        string   `json:"icon,omitempty"`
	Color       string   `json:"color,omitempty"`
	GenreTags   []string `json:"genre_tags,omitempty"`
	// F3b — propose the kind's defining attributes in the SAME call; they are
	// created atomically with the kind on one confirm. Strongly recommended: a
	// kind with no attributes can't describe anything (and extraction needs each
	// attribute's description as its instruction).
	Attributes []proposeKindAttrIn `json:"attributes,omitempty" jsonschema:"the kind's defining attributes (each needs a clear description for extraction)"`
}

type proposeKindAttrIn struct {
	Code        string   `json:"code" jsonschema:"machine code, e.g. weaknesses"`
	Name        string   `json:"name" jsonschema:"display name"`
	Description string   `json:"description,omitempty" jsonschema:"what this attribute captures — used by extraction as the instruction"`
	FieldType   string   `json:"field_type,omitempty" jsonschema:"text|textarea|select|number|date|tags|url|boolean (default text)"`
	IsRequired  bool     `json:"is_required,omitempty"`
	Options     []string `json:"options,omitempty" jsonschema:"options for a select field"`
}

type proposeAttrToolIn struct {
	BookID      string   `json:"book_id" jsonschema:"the book whose schema to extend (UUID; ownership-checked)"`
	KindCode    string   `json:"kind_code" jsonschema:"the kind to add the attribute to (code — see glossary_book_ontology_read)"`
	Code        string   `json:"code" jsonschema:"machine code for the attribute, e.g. cultivation_realm"`
	Name        string   `json:"name" jsonschema:"display name"`
	FieldType   string   `json:"field_type,omitempty" jsonschema:"text|textarea|select|number|date|tags|url|boolean (default text)"`
	IsRequired  bool     `json:"is_required,omitempty"`
	Options     []string `json:"options,omitempty" jsonschema:"options for a select field"`
	Description string   `json:"description,omitempty"`
}

func (s *Server) toolProposeNewKind(ctx context.Context, _ *mcp.CallToolRequest, in proposeKindToolIn) (*mcp.CallToolResult, confirmCardOut, error) {
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, confirmCardOut{}, errors.New("missing caller identity")
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("book_id must be a UUID")
	}
	code := strings.TrimSpace(in.Code)
	name := strings.TrimSpace(in.Name)
	if code == "" || name == "" {
		return nil, confirmCardOut{}, errors.New("code and name are required")
	}
	if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantManage); err != nil {
		return nil, confirmCardOut{}, uniformOwnershipError(err)
	}
	var desc *string
	if d := strings.TrimSpace(in.Description); d != "" {
		desc = &d
	}
	// F3b — fold the proposed attributes into the create-spec (created atomically
	// with the kind on confirm). Validate each field_type up front + dedup by code
	// so a doomed proposal never reaches a confirm card.
	attrs := make([]kindAttrSpec, 0, len(in.Attributes))
	seen := map[string]bool{"name": true} // `name` is auto-seeded
	for _, a := range in.Attributes {
		ac := strings.TrimSpace(a.Code)
		an := strings.TrimSpace(a.Name)
		if ac == "" || an == "" {
			return nil, confirmCardOut{}, errors.New("each attribute needs a code and a name")
		}
		if a.FieldType != "" && !isValidFieldType(a.FieldType) {
			return nil, confirmCardOut{}, errors.New("invalid field_type: " + a.FieldType +
				" (text|textarea|select|number|date|tags|url|boolean)")
		}
		if seen[ac] {
			continue
		}
		seen[ac] = true
		var ad *string
		if d := strings.TrimSpace(a.Description); d != "" {
			ad = &d
		}
		attrs = append(attrs, kindAttrSpec{
			Code: ac, Name: an, Description: ad, FieldType: a.FieldType,
			IsRequired: a.IsRequired, Options: a.Options,
		})
	}
	params := kindCreateParams{Code: code, Name: name, Description: desc, Icon: in.Icon, Color: in.Color, GenreTags: in.GenreTags, Attributes: attrs}
	rows := []previewRow{{Label: "code", Value: code}, {Label: "name", Value: name}}
	for _, a := range attrs {
		rows = append(rows, previewRow{Label: "+ attribute", Value: a.Code, Note: a.FieldTypeOrDefault()})
	}
	title := fmt.Sprintf("Create kind %q (code: %s)", name, code)
	if len(attrs) > 0 {
		title = fmt.Sprintf("Create kind %q + %d attribute(s)", name, len(attrs))
	}
	return s.mintGrantActionCard(userID, bookID, descSchemaCreateKind, title, params, rows, false)
}

// ── batch schema create — the WHOLE ontology on ONE confirm ──────────────────

type proposeKindsToolIn struct {
	BookID string              `json:"book_id" jsonschema:"the book whose schema to extend (UUID; ownership-checked)"`
	Kinds  []proposeKindItemIn `json:"kinds" jsonschema:"the kinds to create — EACH with its defining attributes; ALL land together on ONE confirm card"`
}

type proposeKindItemIn struct {
	Code        string              `json:"code" jsonschema:"machine code for the kind, e.g. cultivation_realm"`
	Name        string              `json:"name" jsonschema:"display name, e.g. Cultivation Realm"`
	Description string              `json:"description,omitempty" jsonschema:"optional description"`
	Icon        string              `json:"icon,omitempty"`
	Color       string              `json:"color,omitempty"`
	Attributes  []proposeKindAttrIn `json:"attributes,omitempty" jsonschema:"the kind's defining attributes (each needs a clear description for extraction)"`
}

// toolProposeKinds proposes MANY kinds (each with its attributes) on a SINGLE
// confirm card — the user builds a whole ontology with one approval instead of one
// click per kind. The effect creates them idempotently (skip-on-conflict), so a
// re-confirm after a partial batch fills only the missing kinds.
func (s *Server) toolProposeKinds(ctx context.Context, _ *mcp.CallToolRequest, in proposeKindsToolIn) (*mcp.CallToolResult, confirmCardOut, error) {
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, confirmCardOut{}, errors.New("missing caller identity")
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("book_id must be a UUID")
	}
	if len(in.Kinds) == 0 {
		return nil, confirmCardOut{}, errors.New("kinds must not be empty")
	}
	if len(in.Kinds) > 20 {
		return nil, confirmCardOut{}, errors.New("at most 20 kinds per batch — split into multiple proposals")
	}
	if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantManage); err != nil {
		return nil, confirmCardOut{}, uniformOwnershipError(err)
	}

	kinds := make([]kindCreateParams, 0, len(in.Kinds))
	rows := make([]previewRow, 0, len(in.Kinds))
	seenKind := map[string]bool{}
	for _, k := range in.Kinds {
		code := strings.TrimSpace(k.Code)
		name := strings.TrimSpace(k.Name)
		if code == "" || name == "" {
			return nil, confirmCardOut{}, errors.New("each kind needs a code and a name")
		}
		if seenKind[code] {
			return nil, confirmCardOut{}, errors.New("duplicate kind code in batch: " + code)
		}
		seenKind[code] = true
		var desc *string
		if d := strings.TrimSpace(k.Description); d != "" {
			desc = &d
		}
		attrs := make([]kindAttrSpec, 0, len(k.Attributes))
		seenAttr := map[string]bool{"name": true} // `name` is auto-seeded
		for _, a := range k.Attributes {
			ac := strings.TrimSpace(a.Code)
			an := strings.TrimSpace(a.Name)
			if ac == "" || an == "" {
				return nil, confirmCardOut{}, errors.New("each attribute needs a code and a name (kind " + code + ")")
			}
			if a.FieldType != "" && !isValidFieldType(a.FieldType) {
				return nil, confirmCardOut{}, errors.New("invalid field_type: " + a.FieldType + " (kind " + code + ")")
			}
			if seenAttr[ac] {
				continue
			}
			seenAttr[ac] = true
			var ad *string
			if d := strings.TrimSpace(a.Description); d != "" {
				ad = &d
			}
			attrs = append(attrs, kindAttrSpec{Code: ac, Name: an, Description: ad, FieldType: a.FieldType, IsRequired: a.IsRequired, Options: a.Options})
		}
		kinds = append(kinds, kindCreateParams{Code: code, Name: name, Description: desc, Icon: k.Icon, Color: k.Color, Attributes: attrs})
		rows = append(rows, previewRow{Label: "kind", Value: code, Note: fmt.Sprintf("%s · %d attribute(s)", name, len(attrs))})
	}

	params := kindsBatchParams{Kinds: kinds}
	title := fmt.Sprintf("Create %d kind(s) with their attributes", len(kinds))
	return s.mintGrantActionCard(userID, bookID, descSchemaCreateKinds, title, params, rows, false)
}

// FieldTypeOrDefault returns the spec's field type, defaulting to "text" for the
// confirm-card preview note.
func (a kindAttrSpec) FieldTypeOrDefault() string {
	if a.FieldType == "" {
		return "text"
	}
	return a.FieldType
}

func (s *Server) toolProposeNewAttribute(ctx context.Context, _ *mcp.CallToolRequest, in proposeAttrToolIn) (*mcp.CallToolResult, confirmCardOut, error) {
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, confirmCardOut{}, errors.New("missing caller identity")
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("book_id must be a UUID")
	}
	code := strings.TrimSpace(in.Code)
	name := strings.TrimSpace(in.Name)
	kindCode := strings.TrimSpace(in.KindCode)
	if code == "" || name == "" || kindCode == "" {
		return nil, confirmCardOut{}, errors.New("kind_code, code and name are required")
	}
	if in.FieldType != "" && !isValidFieldType(in.FieldType) {
		return nil, confirmCardOut{}, errors.New("invalid field_type: " + in.FieldType +
			" (text|textarea|select|number|date|tags|url|boolean)")
	}
	if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantManage); err != nil {
		return nil, confirmCardOut{}, uniformOwnershipError(err)
	}
	kindMap, err := s.loadKindMap(ctx, bookID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("failed to resolve kinds")
	}
	kindID, ok := kindMap[kindCode]
	if !ok {
		return nil, confirmCardOut{}, errors.New("unknown kind: " + kindCode)
	}
	var desc *string
	if d := strings.TrimSpace(in.Description); d != "" {
		desc = &d
	}
	params := attrCreateParams{
		KindID: kindID.String(), Code: code, Name: name, Description: desc,
		FieldType: in.FieldType, IsRequired: in.IsRequired, Options: in.Options,
	}
	rows := []previewRow{{Label: "kind", Value: kindCode}, {Label: "code", Value: code}, {Label: "name", Value: name}}
	return s.mintGrantActionCard(userID, bookID, descSchemaCreateAttr,
		fmt.Sprintf("Add attribute %q (code: %s) to kind %q", name, code, kindCode), params, rows, false)
}

// ── book_delete (the CP-1 canary — destructive cascade, class C) ──────────────

type bookDeleteToolIn struct {
	BookID    string `json:"book_id" jsonschema:"the book to delete from (UUID)"`
	Level     string `json:"level" jsonschema:"what to delete: genre | kind | attribute"`
	Code      string `json:"code" jsonschema:"the code of the genre/kind, or (for level=attribute) the attribute's own code"`
	KindCode  string `json:"kind_code,omitempty" jsonschema:"for level=attribute: the kind code the attribute belongs to"`
	GenreCode string `json:"genre_code,omitempty" jsonschema:"for level=attribute: the genre code the attribute belongs to"`
}

func (s *Server) toolBookDelete(ctx context.Context, _ *mcp.CallToolRequest, in bookDeleteToolIn) (*mcp.CallToolResult, confirmCardOut, error) {
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, confirmCardOut{}, errors.New("missing caller identity")
	}
	bookID, err := uuid.Parse(in.BookID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("book_id must be a UUID")
	}
	level := strings.TrimSpace(in.Level)
	code := strings.TrimSpace(in.Code)
	if code == "" {
		return nil, confirmCardOut{}, errors.New("code is required")
	}
	p := bookDeleteParams{Level: level, Code: code,
		KindCode: strings.TrimSpace(in.KindCode), GenreCode: strings.TrimSpace(in.GenreCode)}
	switch level {
	case deleteLevelGenre, deleteLevelKind:
	case deleteLevelAttr:
		if p.KindCode == "" || p.GenreCode == "" {
			return nil, confirmCardOut{}, errors.New("kind_code and genre_code are required to delete an attribute")
		}
	default:
		return nil, confirmCardOut{}, errors.New("level must be genre, kind, or attribute")
	}
	if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantManage); err != nil {
		return nil, confirmCardOut{}, uniformOwnershipError(err)
	}
	// Mint-time validation (§11 #8): reject a doomed proposal up front so the agent
	// never shows a confirm card destined to 4xx. (Confirm-time re-validation still runs.)
	targetID, err := s.resolveDeleteTarget(ctx, bookID, p)
	if isNoRows(err) {
		return nil, confirmCardOut{}, fmt.Errorf("no live %s with that code in this book", level)
	}
	if err != nil {
		return nil, confirmCardOut{}, errors.New("failed to resolve the target")
	}
	rows, err := s.bookDeleteCascadeRows(ctx, bookID, level, targetID)
	if err != nil {
		return nil, confirmCardOut{}, errors.New("failed to preview the cascade")
	}
	return s.mintGrantActionCard(userID, bookID, descBookDelete,
		fmt.Sprintf("Delete %s %q (and cascade)", level, code), p, rows, true)
}
