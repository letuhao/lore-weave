package api

// SS-4 (Milestone C): the user-facing system-kind WRITE handlers were removed
// here — createKind / patchKind / deleteKind / reorderKinds and the attribute
// write handlers (createAttrDef / patchAttrDef / deleteAttrDef / reorderAttrDefs).
// System (T1) kinds are now seed/admin/migration-only (CLAUDE.md › User
// Boundaries & Tenancy): a regular user must not mutate the shared catalogue.
// Users author kinds in their own tier via /v1/glossary/user-kinds (SS-4 T2) and
// /v1/glossary/books/{id}/book-kinds (SS-5 T3).
//
// What stays here:
//   - createKindFromParams / createAttrDefFromParams — the shared write CORES,
//     still used by the Tier-S assistant confirm path (schema_confirm_handler.go,
//     token-gated, MCP-first). Their rewire to mint TIERED kinds (so the assistant
//     stops writing the shared catalogue) is tracked for SS-7.
//   - isUniqueViolation / isForeignKeyViolation / validFieldTypes / isValidFieldType
//     and the comma/itoa/toStringSlice SQL-builder helpers (shared with genres_crud).
//   - listKinds (read) lives in kinds_handler.go; listKindAliases (read) in kind_aliases.go.

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5/pgconn"

	"github.com/loreweave/glossary-service/internal/domain"
)

// kindCreateParams is the create-spec for a new kind — captured inside the
// Tier-S confirm token so the confirm step creates exactly what was proposed.
type kindCreateParams struct {
	Code        string   `json:"code"`
	Name        string   `json:"name"`
	Description *string  `json:"description"`
	Icon        string   `json:"icon"`
	Color       string   `json:"color"`
	GenreTags   []string `json:"genre_tags"`
}

// createKindFromParams inserts a kind + its seed 'name' attribute in one tx and
// returns the created kind. A duplicate code surfaces as a unique-violation
// (isUniqueViolation) so callers can map it to 409. Shared core — currently the
// Tier-S confirm endpoint is the only caller (the manual user handler was removed
// in SS-4 Milestone C). SS-7 rewires this to write the tiered tables.
func (s *Server) createKindFromParams(ctx context.Context, in kindCreateParams) (domain.EntityKind, error) {
	// SCHEMA-LOW1: defense-in-depth — the caller validates upstream, but the core
	// must not create an unnamed kind if a future caller forgets.
	if strings.TrimSpace(in.Code) == "" || strings.TrimSpace(in.Name) == "" {
		return domain.EntityKind{}, errors.New("code and name are required")
	}
	if in.Icon == "" {
		in.Icon = "📝"
	}
	if in.Color == "" {
		in.Color = "#6366f1"
	}
	if in.GenreTags == nil {
		in.GenreTags = []string{"universal"}
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.EntityKind{}, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	var kindID string
	if err := tx.QueryRow(ctx, `
		INSERT INTO system_kinds(code, name, description, icon, color, is_default, is_hidden, sort_order, genre_tags)
		VALUES ($1,$2,$3,$4,$5,false,false,
			COALESCE((SELECT MAX(sort_order)+1 FROM system_kinds),1),
			$6)
		RETURNING kind_id`,
		in.Code, in.Name, in.Description, in.Icon, in.Color, in.GenreTags,
	).Scan(&kindID); err != nil {
		return domain.EntityKind{}, err
	}

	// Seed a system 'name' display attribute so the kind is name-capable from creation.
	nameAttr := domain.AttrDef{Code: "name", Name: "Name", FieldType: "text", IsRequired: true, IsActive: true, SortOrder: 0, GenreTags: []string{}}
	if err := tx.QueryRow(ctx, `
		INSERT INTO system_kind_attributes(kind_id, code, name, field_type, is_required, is_system, sort_order)
		VALUES ($1,'name','Name','text',true,true,0)
		RETURNING attr_def_id`,
		kindID,
	).Scan(&nameAttr.AttrDefID); err != nil {
		return domain.EntityKind{}, err
	}

	if err := tx.Commit(ctx); err != nil {
		return domain.EntityKind{}, err
	}

	return domain.EntityKind{
		KindID:      kindID,
		Code:        in.Code,
		Name:        in.Name,
		Description: in.Description,
		Icon:        in.Icon,
		Color:       in.Color,
		IsDefault:   false,
		IsHidden:    false,
		GenreTags:   in.GenreTags,
		Attributes:  []domain.AttrDef{nameAttr},
	}, nil
}

// attrCreateParams is the create-spec for a new attribute definition — KindID is
// resolved at propose time and carried inside the Tier-S confirm token.
type attrCreateParams struct {
	KindID          string   `json:"kind_id"`
	Code            string   `json:"code"`
	Name            string   `json:"name"`
	Description     *string  `json:"description"`
	FieldType       string   `json:"field_type"`
	IsRequired      bool     `json:"is_required"`
	SortOrder       int      `json:"sort_order"`
	Options         []string `json:"options"`
	GenreTags       []string `json:"genre_tags"`
	AutoFillPrompt  *string  `json:"auto_fill_prompt"`
	TranslationHint *string  `json:"translation_hint"`
}

// createAttrDefFromParams inserts an attribute definition under in.KindID and
// returns it. A duplicate (kind, code) surfaces as a unique-violation. Shared
// core for the Tier-S confirm endpoint (the manual handler was removed in SS-4).
func (s *Server) createAttrDefFromParams(ctx context.Context, in attrCreateParams) (domain.AttrDef, error) {
	// SCHEMA-LOW1: defense-in-depth code/name guard (see createKindFromParams).
	if strings.TrimSpace(in.Code) == "" || strings.TrimSpace(in.Name) == "" {
		return domain.AttrDef{}, errors.New("code and name are required")
	}
	if in.FieldType == "" {
		in.FieldType = "text"
	}
	if in.GenreTags == nil {
		in.GenreTags = []string{}
	}
	var attrDefID string
	err := s.pool.QueryRow(ctx, `
		INSERT INTO system_kind_attributes(kind_id, code, name, description, field_type, is_required, sort_order, options, genre_tags, auto_fill_prompt, translation_hint)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
		RETURNING attr_def_id`,
		in.KindID, in.Code, in.Name, in.Description, in.FieldType, in.IsRequired, in.SortOrder, in.Options, in.GenreTags, in.AutoFillPrompt, in.TranslationHint,
	).Scan(&attrDefID)
	if err != nil {
		return domain.AttrDef{}, err
	}
	return domain.AttrDef{
		AttrDefID:       attrDefID,
		Code:            in.Code,
		Name:            in.Name,
		Description:     in.Description,
		FieldType:       in.FieldType,
		IsRequired:      in.IsRequired,
		IsActive:        true,
		SortOrder:       in.SortOrder,
		Options:         in.Options,
		GenreTags:       in.GenreTags,
		AutoFillPrompt:  in.AutoFillPrompt,
		TranslationHint: in.TranslationHint,
	}, nil
}

// isUniqueViolation reports whether err is a Postgres unique-constraint violation
// (SQLSTATE 23505) — used to map a duplicate kind/attribute code to 409.
func isUniqueViolation(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == "23505"
}

// isForeignKeyViolation reports whether err is a Postgres FK violation (23503) —
// e.g. confirming a new attribute whose kind was deleted between propose and
// confirm — so the caller can return a clean 422 instead of a 500.
func isForeignKeyViolation(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == "23503"
}

// validFieldTypes is the allowed attribute field_type set.
var validFieldTypes = map[string]bool{
	"text": true, "textarea": true, "select": true, "number": true,
	"date": true, "tags": true, "url": true, "boolean": true,
}

func isValidFieldType(ft string) bool { return validFieldTypes[ft] }

// ── small SQL-builder helpers (shared with genres_crud.go) ───────────────────

func comma(s string) string {
	if s == "" {
		return ""
	}
	return ","
}

func itoa(i int) string {
	return fmt.Sprintf("%d", i)
}
