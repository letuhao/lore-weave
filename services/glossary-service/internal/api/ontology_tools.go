package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/google/jsonschema-go/jsonschema"
	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
	lwmcp "github.com/loreweave/loreweave_mcp"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// T-ONTO — the consolidated create/update/delete tools (tool-catalog-simplification
// spec, docs/specs/2026-07-06-tool-catalog-simplification.md). Orchestration only —
// every write reuses the SAME per-level cores as the legacy single-purpose tools
// (book_ontology_core.go, book_tools.go's patch resolver, user_tools.go's create/
// patch/trash helpers) so the write paths can never diverge (§6/§8 of the spec).
//
// §3.1: create+update merge into ONE tool via an implicit discriminator
// (base_version absent ⇒ create, present ⇒ update) — no action enum. Delete stays
// its OWN tool because book-tier delete is confirm-gated and user-tier delete is
// direct+reversible (a confirmed safety-behavior asymmetry, not hypothetical —
// CAT-2 in docs/standards/mcp-tool-io.md names this exact failure mode).

// RegisterOntologyTools adds the two consolidated tools. Registered separately from
// RegisterBookTools/RegisterUserTools (append-only convention) since both tools span
// BOTH tiers via `scope`.
func (s *Server) RegisterOntologyTools(srv *mcp.Server) {
	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_ontology_upsert",
		Description: "Create or update book- or user-tier ontology rows (genre, kind, or " +
			"attribute) — WRITES IMMEDIATELY, no confirmation (Tier A). One call may mix " +
			"creates and updates freely. Omit base_version on an item to create it; include " +
			"the current base_version to update it with optimistic locking. Accepts 1-50 " +
			"items; each item succeeds or fails independently. (For a human-confirmed proposal " +
			"of a single new attribute instead, use glossary_propose_new_attribute.)",
		InputSchema: ontologyUpsertSchema(),
		Meta: lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeBook, nil, []string{
			"add a kind", "add a genre", "add an attribute", "edit a kind", "rename a kind", "new entity type",
		}),
	}, s.toolOntologyUpsert)

	lwmcp.RegisterTool(srv, &mcp.Tool{
		Name: "glossary_ontology_delete",
		Description: "Delete book- or user-tier ontology row(s). scope=book mints a confirm " +
			"token — a human must approve before the delete executes; returns {confirm_token, " +
			"preview}. scope=user executes immediately as a reversible soft-delete (undo via " +
			"glossary_user_restore); returns {results}. Deleting an already-deleted row is a " +
			"no-op, not an error.",
		InputSchema: ontologyDeleteSchema(),
		// _meta.tier is ONE value covering two behaviorally-different branches (book=confirm-
		// gated, user=direct) — pick the more cautious bucket (W) uniformly; the actual
		// confirm requirement is enforced server-side regardless (spec §8.9).
		Meta: lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, []string{
			"remove a kind", "delete a genre", "trash an attribute",
		}),
	}, s.toolOntologyDelete)
}

func ontologyUpsertSchema() *jsonschema.Schema {
	s := closedSetSchemaFor[ontologyUpsertToolIn](map[string][]any{
		"scope":              {"book", "user"},
		"items[].level":      enumLevels,
		"items[].field_type": enumFieldTypes,
	})
	itemsNode := schemaPropAt(s, "items")
	one, fifty := 1, 50
	itemsNode.MinItems = &one
	itemsNode.MaxItems = &fifty
	return s
}

func ontologyDeleteSchema() *jsonschema.Schema {
	s := closedSetSchemaFor[ontologyDeleteToolIn](map[string][]any{
		"scope":         {"book", "user"},
		"items[].level": enumLevels,
	})
	itemsNode := schemaPropAt(s, "items")
	one, fifty := 1, 50
	itemsNode.MinItems = &one
	itemsNode.MaxItems = &fifty
	return s
}

// ── glossary_ontology_upsert ──────────────────────────────────────────────────

type ontologyUpsertItemIn struct {
	Level           string    `json:"level" jsonschema:"REQUIRED discriminator: genre | kind | attribute"`
	Code            string    `json:"code,omitempty" jsonschema:"machine code (derived from name on create if omitted)"`
	BaseVersion     string    `json:"base_version,omitempty" jsonschema:"omit to CREATE; include the base_version you read to UPDATE with optimistic locking"`
	Name            *string   `json:"name,omitempty" jsonschema:"display name (required on create)"`
	Description     *string   `json:"description,omitempty"`
	Icon            *string   `json:"icon,omitempty"`
	Color           *string   `json:"color,omitempty"`
	SortOrder       *int      `json:"sort_order,omitempty"`
	IsHidden        *bool     `json:"is_hidden,omitempty" jsonschema:"kind only"`
	KindCode        string    `json:"kind_code,omitempty" jsonschema:"attribute only: the kind it attaches to"`
	GenreCode       string    `json:"genre_code,omitempty" jsonschema:"attribute only: the genre cell"`
	FieldType       *string   `json:"field_type,omitempty" jsonschema:"attribute only"`
	IsRequired      *bool     `json:"is_required,omitempty" jsonschema:"attribute only"`
	Options         *[]string `json:"options,omitempty" jsonschema:"attribute only: options for a select field"`
	AutoFillPrompt  *string   `json:"auto_fill_prompt,omitempty" jsonschema:"attribute only"`
	TranslationHint *string   `json:"translation_hint,omitempty" jsonschema:"attribute only"`
}

type ontologyUpsertToolIn struct {
	Scope  string                 `json:"scope" jsonschema:"REQUIRED: book | user — which tenancy tier to write to"`
	BookID string                 `json:"book_id,omitempty" jsonschema:"required when scope=book; omit when scope=user"`
	Items  []ontologyUpsertItemIn `json:"items" jsonschema:"1-50 items; each independently created or updated by base_version presence"`
}

type ontologyItemResult struct {
	Level   string `json:"level"`
	Code    string `json:"code"`
	Status  string `json:"status"` // created | updated | error
	Version string `json:"version,omitempty"`
	Error   string `json:"error,omitempty"`
}

type ontologySummary struct {
	Created int `json:"created"`
	Updated int `json:"updated"`
	Failed  int `json:"failed"`
}

type ontologyUpsertOut struct {
	Results []ontologyItemResult `json:"results"`
	Summary ontologySummary      `json:"summary"`
}

func (s *Server) toolOntologyUpsert(ctx context.Context, _ *mcp.CallToolRequest, in ontologyUpsertToolIn) (*mcp.CallToolResult, ontologyUpsertOut, error) {
	scope := strings.TrimSpace(in.Scope)
	if scope != "book" && scope != "user" {
		return nil, ontologyUpsertOut{}, errors.New("scope must be book or user")
	}
	if len(in.Items) == 0 {
		return nil, ontologyUpsertOut{}, errors.New("items must have at least one entry")
	}
	// §8.2 — reject an exact duplicate (level, code) within the SAME call up front,
	// rather than an ordering-dependent partial result. Only checked when Code is
	// explicitly supplied: an omitted code (create-only — derived from Name server-
	// side, e.g. by slugify) isn't known yet at this point, so two DIFFERENT items
	// both omitting code (e.g. Name="Sect" and Name="Faction") must NOT collide here
	// on the shared empty-string key — a review-impl-caught false positive that
	// blocked the exact "batch-create several new kinds by name only" use case the
	// schema's own description advertises ("code derived from name on create if
	// omitted"). A genuine same-derived-code collision is still caught per-item by
	// the normal unique-constraint error on the second INSERT (CAT-3: per-item
	// result, not a whole-batch rejection).
	seen := map[string]bool{}
	for _, it := range in.Items {
		code := strings.TrimSpace(it.Code)
		if code == "" {
			continue
		}
		key := strings.TrimSpace(it.Level) + "|" + code
		if seen[key] {
			return nil, ontologyUpsertOut{}, fmt.Errorf("duplicate level+code %q in this batch — split into separate calls", key)
		}
		seen[key] = true
	}

	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, ontologyUpsertOut{}, errors.New("missing caller identity")
	}

	var bookID uuid.UUID
	if scope == "book" {
		var err error
		bookID, err = uuid.Parse(strings.TrimSpace(in.BookID))
		if err != nil {
			return nil, ontologyUpsertOut{}, errors.New("book_id must be a UUID when scope=book")
		}
		if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantManage); err != nil {
			return nil, ontologyUpsertOut{}, uniformOwnershipError(err)
		}
	}

	out := ontologyUpsertOut{Results: make([]ontologyItemResult, 0, len(in.Items))}
	for _, it := range in.Items {
		res := s.upsertOneOntologyItem(ctx, scope, bookID, userID, it)
		out.Results = append(out.Results, res)
		switch res.Status {
		case "created":
			out.Summary.Created++
		case "updated":
			out.Summary.Updated++
		default:
			out.Summary.Failed++
		}
	}
	return nil, out, nil
}

func (s *Server) upsertOneOntologyItem(ctx context.Context, scope string, bookID, userID uuid.UUID, it ontologyUpsertItemIn) ontologyItemResult {
	level := strings.TrimSpace(it.Level)
	code := strings.TrimSpace(it.Code)
	res := ontologyItemResult{Level: level, Code: code}
	if level != bookLevelGenre && level != bookLevelKind && level != bookLevelAttr {
		res.Status, res.Error = "error", "level must be genre, kind, or attribute"
		return res
	}
	isUpdate := strings.TrimSpace(it.BaseVersion) != ""
	var newVersion, newCode string
	var err error
	if scope == "book" {
		if isUpdate {
			newVersion, err = s.upsertBookPatchOne(ctx, bookID, it)
			newCode = code
		} else {
			newVersion, newCode, err = s.upsertBookCreateOne(ctx, bookID, it)
		}
	} else {
		if isUpdate {
			newVersion, err = s.upsertUserPatchOne(ctx, userID, it)
			newCode = code
		} else {
			newVersion, newCode, err = s.upsertUserCreateOne(ctx, userID, it)
		}
	}
	if newCode != "" {
		res.Code = newCode
	}
	if err != nil {
		res.Status, res.Error = "error", err.Error()
		return res
	}
	res.Version = newVersion
	if isUpdate {
		res.Status = "updated"
	} else {
		res.Status = "created"
	}
	return res
}

// upsertBookCreateOne reuses the shared book-tier create cores (book_ontology_core.go)
// — the same ones book_tools.go's (legacy) toolBookCreate calls.
func (s *Server) upsertBookCreateOne(ctx context.Context, bookID uuid.UUID, it ontologyUpsertItemIn) (version, code string, err error) {
	level := strings.TrimSpace(it.Level)
	name := strings.TrimSpace(strOrEmpty(it.Name))
	if name == "" {
		return "", "", errors.New("name is required to create")
	}
	code = strings.TrimSpace(it.Code)
	desc := optStr(strOrEmpty(it.Description))
	switch level {
	case bookLevelGenre:
		g, cerr := s.createBookGenreCore(ctx, bookID, bookGenreCreateParams{
			Code: code, Name: name, Icon: strOrEmpty(it.Icon), Color: strOrEmpty(it.Color), SortOrder: intOrZero(it.SortOrder),
		})
		if cerr != nil {
			return "", code, bookCreateToolErr(cerr, firstNonEmpty(code, name))
		}
		return g.BaseVersion, g.Code, nil
	case bookLevelKind:
		k, cerr := s.createBookKindCore(ctx, bookID, bookKindCreateParams{
			Code: code, Name: name, Description: desc, Icon: strOrEmpty(it.Icon), Color: strOrEmpty(it.Color),
			SortOrder: intOrZero(it.SortOrder), IsHidden: boolOrFalse(it.IsHidden),
		})
		if cerr != nil {
			return "", code, bookCreateToolErr(cerr, firstNonEmpty(code, name))
		}
		return k.BaseVersion, k.Code, nil
	case bookLevelAttr:
		kindID, gErr := s.resolveBookKindID(ctx, bookID, strings.TrimSpace(it.KindCode))
		if isNoRows(gErr) {
			return "", code, errors.New("no live kind with that kind_code in this book")
		} else if gErr != nil {
			return "", code, errors.New("failed to resolve kind_code")
		}
		genreID, ge := s.resolveBookGenreID(ctx, bookID, strings.TrimSpace(it.GenreCode))
		if isNoRows(ge) {
			return "", code, errors.New("no live genre with that genre_code in this book")
		} else if ge != nil {
			return "", code, errors.New("failed to resolve genre_code")
		}
		a, cerr := s.createBookAttributeCore(ctx, bookID, bookAttrCreateParams{
			KindID: kindID, GenreID: genreID, Code: code, Name: name, Description: desc,
			FieldType: strOrEmpty(it.FieldType), IsRequired: boolOrFalse(it.IsRequired), SortOrder: intOrZero(it.SortOrder),
			Options: sliceOrNil(it.Options), AutoFillPrompt: optStr(strOrEmpty(it.AutoFillPrompt)), TranslationHint: optStr(strOrEmpty(it.TranslationHint)),
		})
		if cerr != nil {
			return "", code, bookCreateToolErr(cerr, firstNonEmpty(code, name))
		}
		return a.BaseVersion, a.Code, nil
	default:
		return "", code, errors.New("level must be genre, kind, or attribute")
	}
}

// upsertBookPatchOne reuses resolveBookPatch/bookRowVersions/compareBaseVersion —
// the same functions book_tools.go's (legacy) toolBookPatch calls, including its
// base_version-hallucination shim (W0 #1).
func (s *Server) upsertBookPatchOne(ctx context.Context, bookID uuid.UUID, it ontologyUpsertItemIn) (version string, err error) {
	level := strings.TrimSpace(it.Level)
	if level == bookLevelAttr && it.FieldType != nil && !isValidFieldType(*it.FieldType) {
		return "", errInvalidFieldType
	}
	patchIn := bookPatchToolIn{
		BookID: bookID.String(), Level: level, Code: strings.TrimSpace(it.Code),
		KindCode: strings.TrimSpace(it.KindCode), GenreCode: strings.TrimSpace(it.GenreCode),
		BaseVersion: strings.TrimSpace(it.BaseVersion),
		Name: it.Name, Description: it.Description, Icon: it.Icon, Color: it.Color,
		SortOrder: it.SortOrder, IsHidden: it.IsHidden, FieldType: it.FieldType, IsRequired: it.IsRequired,
		Options: it.Options, AutoFillPrompt: it.AutoFillPrompt, TranslationHint: it.TranslationHint,
	}
	table, idCol, id, fields, perr := s.resolveBookPatch(ctx, bookID, level, patchIn)
	if perr != nil {
		return "", perr
	}
	curTime, createdAt, verr := s.bookRowVersions(ctx, table, idCol, bookID, id)
	if verr != nil {
		return "", errors.New("the target no longer exists")
	}
	cur := formatBaseVersion(curTime)
	base := patchIn.BaseVersion
	if base != "" {
		if t, terr := time.Parse(time.RFC3339Nano, base); terr != nil || t.Before(createdAt) {
			base = "" // hallucination shim, same as toolBookPatch (W0 #1)
		}
	}
	if cverr := compareBaseVersion(cur, base); cverr != nil {
		return "", fmt.Errorf(
			"the row changed since you read it (409) — its current base_version is %s; retry with base_version=%q",
			cur, cur)
	}
	if len(fields) == 0 {
		return "", errors.New("no editable fields supplied")
	}
	if err := s.applyBookUpdate(ctx, table, idCol, bookID, id, fields); err != nil {
		return "", errors.New("update failed")
	}
	newVer, _ := s.bookRowVersion(ctx, table, idCol, bookID, id)
	return newVer, nil
}

// upsertUserCreateOne reuses the SAME create-tool functions user_tools.go's
// (legacy) toolUserCreate dispatches to.
func (s *Server) upsertUserCreateOne(ctx context.Context, userID uuid.UUID, it ontologyUpsertItemIn) (version, code string, err error) {
	level := strings.TrimSpace(it.Level)
	name := strings.TrimSpace(strOrEmpty(it.Name))
	if name == "" {
		return "", "", errors.New("name is required to create")
	}
	code = strings.TrimSpace(it.Code)
	if code == "" {
		code = slugify(name)
	}
	if code == "" {
		return "", "", errors.New("code could not be derived from name")
	}
	in := userCreateToolIn{
		Level: level, Code: code, Name: name, Description: strOrEmpty(it.Description),
		Icon: strOrEmpty(it.Icon), Color: strOrEmpty(it.Color), SortOrder: intOrZero(it.SortOrder),
		KindCode: strings.TrimSpace(it.KindCode), GenreCode: strings.TrimSpace(it.GenreCode),
		FieldType: strOrEmpty(it.FieldType), IsRequired: boolOrFalse(it.IsRequired),
		Options: sliceOrNil(it.Options), AutoFillPrompt: strOrEmpty(it.AutoFillPrompt), TranslationHint: strOrEmpty(it.TranslationHint),
	}
	var out userWriteOut
	switch level {
	case userLevelGenre:
		_, out, err = s.createUserGenreTool(ctx, userID, code, name, in)
	case userLevelKind:
		_, out, err = s.createUserKindTool(ctx, userID, code, name, in)
	case userLevelAttr:
		_, out, err = s.createUserAttrTool(ctx, userID, code, name, in)
	default:
		return "", code, errors.New("level must be genre, kind, or attribute")
	}
	if err != nil {
		return "", code, err
	}
	return out.BaseVersion, out.Code, nil
}

// upsertUserPatchOne reuses the SAME patch-tool functions user_tools.go's (legacy)
// toolUserPatch dispatches to — the optional fields are already the same pointer
// shape, so they pass straight through.
func (s *Server) upsertUserPatchOne(ctx context.Context, userID uuid.UUID, it ontologyUpsertItemIn) (version string, err error) {
	level := strings.TrimSpace(it.Level)
	code := strings.TrimSpace(it.Code)
	if code == "" {
		return "", errors.New("code is required")
	}
	if level == userLevelAttr && it.FieldType != nil && !isValidFieldType(*it.FieldType) {
		return "", errInvalidFieldType
	}
	in := userPatchToolIn{
		Level: level, Code: code, KindCode: strings.TrimSpace(it.KindCode), GenreCode: strings.TrimSpace(it.GenreCode),
		BaseVersion: strings.TrimSpace(it.BaseVersion),
		Name: it.Name, Description: it.Description, Icon: it.Icon, Color: it.Color, SortOrder: it.SortOrder,
		FieldType: it.FieldType, IsRequired: it.IsRequired, Options: it.Options,
		AutoFillPrompt: it.AutoFillPrompt, TranslationHint: it.TranslationHint,
	}
	var out userWriteOut
	switch level {
	case userLevelGenre:
		_, out, err = s.patchUserGenreTool(ctx, userID, code, in)
	case userLevelKind:
		_, out, err = s.patchUserKindTool(ctx, userID, code, in)
	case userLevelAttr:
		_, out, err = s.patchUserAttrTool(ctx, userID, code, in)
	default:
		return "", errors.New("level must be genre, kind, or attribute")
	}
	if err != nil {
		return "", err
	}
	return out.BaseVersion, nil
}

// ── glossary_ontology_delete ──────────────────────────────────────────────────

type ontologyDeleteItemIn struct {
	Level     string `json:"level" jsonschema:"genre | kind | attribute"`
	Code      string `json:"code"`
	KindCode  string `json:"kind_code,omitempty" jsonschema:"attribute only"`
	GenreCode string `json:"genre_code,omitempty" jsonschema:"attribute only"`
}

type ontologyDeleteToolIn struct {
	Scope  string                 `json:"scope" jsonschema:"book | user"`
	BookID string                 `json:"book_id,omitempty" jsonschema:"required when scope=book"`
	Items  []ontologyDeleteItemIn `json:"items"`
}

type ontologyDeleteItemResult struct {
	Level  string `json:"level"`
	Code   string `json:"code"`
	Status string `json:"status"` // trashed | already_trashed | error
	Error  string `json:"error,omitempty"`
}

type ontologyDeleteSummary struct {
	Trashed int `json:"trashed"`
	Failed  int `json:"failed"`
}

// ontologyDeleteOut's shape genuinely differs by `scope` (CAT-2: a merge across
// branches with different safety behavior must branch explicitly) — book mints a
// confirm token, user executes directly. Both are documented in the tool
// description; only the fields for the taken branch are populated.
type ontologyDeleteOut struct {
	ConfirmToken string                     `json:"confirm_token,omitempty"`
	Preview      []previewRow               `json:"preview,omitempty"`
	Results      []ontologyDeleteItemResult `json:"results,omitempty"`
	Summary      *ontologyDeleteSummary     `json:"summary,omitempty"`
	// Warning (external MCP discoverability audit #11, scope=book branch only) — set
	// when EVERY item in the batch already resolved to "already removed" at mint time,
	// so confirming the minted token is guaranteed to delete nothing.
	Warning string `json:"warning,omitempty"`
}

func (s *Server) toolOntologyDelete(ctx context.Context, _ *mcp.CallToolRequest, in ontologyDeleteToolIn) (*mcp.CallToolResult, ontologyDeleteOut, error) {
	scope := strings.TrimSpace(in.Scope)
	if scope != "book" && scope != "user" {
		return nil, ontologyDeleteOut{}, errors.New("scope must be book or user")
	}
	if len(in.Items) == 0 {
		return nil, ontologyDeleteOut{}, errors.New("items must have at least one entry")
	}
	for _, it := range in.Items {
		if strings.TrimSpace(it.Level) == "" || strings.TrimSpace(it.Code) == "" {
			return nil, ontologyDeleteOut{}, errors.New("every item needs level and code")
		}
	}
	userID, ok := userIDFromCtx(ctx)
	if !ok {
		return nil, ontologyDeleteOut{}, errors.New("missing caller identity")
	}

	if scope == "user" {
		results := make([]ontologyDeleteItemResult, 0, len(in.Items))
		summary := ontologyDeleteSummary{}
		for _, it := range in.Items {
			res := s.deleteOneUserOntologyItem(ctx, userID, it)
			results = append(results, res)
			if res.Status == "error" {
				summary.Failed++
			} else {
				summary.Trashed++
			}
		}
		return nil, ontologyDeleteOut{Results: results, Summary: &summary}, nil
	}

	// scope == "book": mint ONE confirm token covering the whole batch (§8.8).
	bookID, err := uuid.Parse(strings.TrimSpace(in.BookID))
	if err != nil {
		return nil, ontologyDeleteOut{}, errors.New("book_id must be a UUID when scope=book")
	}
	if err := s.checkGrant(ctx, bookID, userID, grantclient.GrantManage); err != nil {
		return nil, ontologyDeleteOut{}, uniformOwnershipError(err)
	}
	items := make([]bookDeleteParams, 0, len(in.Items))
	rows := make([]previewRow, 0, len(in.Items))
	alreadyGone := 0
	for _, it := range in.Items {
		p := bookDeleteParams{Level: strings.TrimSpace(it.Level), Code: strings.TrimSpace(it.Code),
			KindCode: strings.TrimSpace(it.KindCode), GenreCode: strings.TrimSpace(it.GenreCode)}
		items = append(items, p)
		targetID, terr := s.resolveDeleteTarget(ctx, bookID, p)
		if isNoRows(terr) {
			rows = append(rows, previewRow{Label: p.Level, Value: p.Code, Note: "already removed — nothing to delete"})
			alreadyGone++
			continue
		}
		if terr != nil {
			return nil, ontologyDeleteOut{}, errors.New("failed to preview the cascade")
		}
		cascadeRows, cerr := s.bookDeleteCascadeRows(ctx, bookID, p.Level, targetID)
		if cerr != nil {
			return nil, ontologyDeleteOut{}, errors.New("failed to preview the cascade")
		}
		rows = append(rows, cascadeRows...)
	}
	_, card, merr := s.mintGrantActionCard(userID, bookID, descBookDeleteBatch,
		fmt.Sprintf("Delete %d ontology row(s) (and cascades)", len(items)),
		bookDeleteBatchParams{Items: items}, rows, true)
	if merr != nil {
		return nil, ontologyDeleteOut{}, merr
	}
	out := ontologyDeleteOut{ConfirmToken: card.ConfirmToken, Preview: card.PreviewRows}
	// External MCP discoverability audit #11 — every item in the batch already resolved
	// to "not found" at mint time, so confirming changes nothing.
	if alreadyGone == len(items) {
		out.Warning = fmt.Sprintf("all %d item(s) are already removed — this will delete nothing", len(items))
	}
	return nil, out, nil
}

// deleteOneUserOntologyItem is the direct (no confirm), reversible soft-delete
// branch — mirrors user_tools.go's userTrashTransition, per-item, idempotent (an
// already-gone row is "already_trashed", not an error — spec §8.8).
func (s *Server) deleteOneUserOntologyItem(ctx context.Context, userID uuid.UUID, it ontologyDeleteItemIn) ontologyDeleteItemResult {
	level := strings.TrimSpace(it.Level)
	code := strings.TrimSpace(it.Code)
	res := ontologyDeleteItemResult{Level: level, Code: code}
	var err error
	switch level {
	case userLevelGenre:
		if _, rerr := s.resolveUserGenreID(ctx, userID, code); isNoRows(rerr) {
			res.Status = "already_trashed"
			return res
		} else if rerr != nil {
			res.Status, res.Error = "error", "failed to resolve the genre"
			return res
		}
		if gerr := s.userGenreDeletable(ctx, userID, code); gerr != nil {
			res.Status, res.Error = "error", gerr.Error()
			return res
		}
		_, err = s.toggleUserTrash(ctx, "user_genres", "genre_id", userID, code, true, true)
	case userLevelKind:
		_, err = s.toggleUserTrash(ctx, "user_kinds", "user_kind_id", userID, code, true, true)
	case userLevelAttr:
		kindCode, genreCode := strings.TrimSpace(it.KindCode), strings.TrimSpace(it.GenreCode)
		if kindCode == "" || genreCode == "" {
			res.Status, res.Error = "error", "kind_code and genre_code are required for an attribute"
			return res
		}
		kindID, kerr := s.resolveUserKindID(ctx, userID, kindCode)
		if isNoRows(kerr) {
			res.Status = "already_trashed"
			return res
		} else if kerr != nil {
			res.Status, res.Error = "error", "failed to resolve kind_code"
			return res
		}
		genreID, gerr := s.resolveUserGenreID(ctx, userID, genreCode)
		if isNoRows(gerr) {
			res.Status = "already_trashed"
			return res
		} else if gerr != nil {
			res.Status, res.Error = "error", "failed to resolve genre_code"
			return res
		}
		tag, aerr := s.pool.Exec(ctx,
			`UPDATE user_attributes SET deleted_at = now() WHERE owner_user_id=$1 AND kind_id=$2 AND genre_id=$3 AND code=$4 AND deleted_at IS NULL`,
			userID, kindID, genreID, code)
		if aerr != nil {
			res.Status, res.Error = "error", "delete failed"
			return res
		}
		if tag.RowsAffected() == 0 {
			res.Status = "already_trashed"
			return res
		}
		res.Status = "trashed"
		return res
	default:
		res.Status, res.Error = "error", "level must be genre, kind, or attribute"
		return res
	}
	if isNoRows(err) {
		res.Status = "already_trashed"
		return res
	}
	if err != nil {
		res.Status, res.Error = "error", "delete failed"
		return res
	}
	res.Status = "trashed"
	return res
}

// bookDeleteBatchParams is the captured intent for a glossary_ontology_delete
// (scope=book) proposal: every item the user confirms in ONE click. Mirrors
// kindsBatchParams/effectSchemaCreateKinds' proven shape (action_confirm.go).
type bookDeleteBatchParams struct {
	Items []bookDeleteParams `json:"items"`
}

// effectBookDeleteBatch re-validates + deletes each item against CURRENT state
// (§13.5 #4). Idempotent: an item already gone since propose is SKIPPED, not
// failed — a re-confirm after a partial batch only removes what's left (mirrors
// effectSchemaCreateKinds' skip-on-already-exists symmetry).
func (s *Server) effectBookDeleteBatch(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p bookDeleteBatchParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	if len(p.Items) == 0 {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "no items in this proposal — propose again")
		return
	}
	deleted := make([]string, 0, len(p.Items))
	skipped := make([]string, 0)
	for _, item := range p.Items {
		targetID, err := s.resolveDeleteTarget(ctx, claims.BookID, item)
		if isNoRows(err) {
			skipped = append(skipped, item.Code)
			continue
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
			return
		}
		var found bool
		switch item.Level {
		case deleteLevelGenre:
			found, err = s.cascadeDeleteBookGenre(ctx, claims.BookID, targetID)
		case deleteLevelKind:
			found, err = s.cascadeDeleteBookKind(ctx, claims.BookID, targetID)
		case deleteLevelAttr:
			found, err = s.softDeleteBookAttribute(ctx, claims.BookID, targetID)
		default:
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "unknown delete level")
			return
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
			return
		}
		if !found {
			skipped = append(skipped, item.Code)
			continue
		}
		deleted = append(deleted, item.Code)
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"deleted": deleted, "skipped": skipped,
		"deleted_count": len(deleted), "skipped_count": len(skipped),
	})
}

// previewBookDeleteBatch re-renders the batch confirm card from CURRENT state
// (§5.1 #5) — mirrors previewSchemaCreateKinds.
func (s *Server) previewBookDeleteBatch(w http.ResponseWriter, ctx context.Context, claims actionClaims) {
	var p bookDeleteBatchParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	rows := make([]previewRow, 0, len(p.Items))
	for _, item := range p.Items {
		targetID, err := s.resolveDeleteTarget(ctx, claims.BookID, item)
		if isNoRows(err) {
			rows = append(rows, previewRow{Label: item.Level, Value: item.Code, Note: "already removed — nothing to delete"})
			continue
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "preview failed")
			return
		}
		cascadeRows, cerr := s.bookDeleteCascadeRows(ctx, claims.BookID, item.Level, targetID)
		if cerr != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "preview failed")
			return
		}
		rows = append(rows, cascadeRows...)
	}
	writeJSON(w, http.StatusOK, actionPreview{
		Descriptor: descBookDeleteBatch, Destructive: true,
		Title:       fmt.Sprintf("Delete %d ontology row(s) (and cascades)", len(p.Items)),
		PreviewRows: rows,
	})
}

// ── small pointer-unwrap helpers (the shared item shape serves create+update, so
// its optional fields are pointers; create needs concrete values with zero
// defaults) ────────────────────────────────────────────────────────────────────

func strOrEmpty(p *string) string {
	if p == nil {
		return ""
	}
	return *p
}

func intOrZero(p *int) int {
	if p == nil {
		return 0
	}
	return *p
}

func boolOrFalse(p *bool) bool {
	if p == nil {
		return false
	}
	return *p
}

func sliceOrNil(p *[]string) []string {
	if p == nil {
		return nil
	}
	return *p
}
