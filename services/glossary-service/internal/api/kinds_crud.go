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

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
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

// createKindFromParams inserts a kind into the BOOK tier (O2 — the assistant
// proposes into the book's sovereign ontology, never the shared system catalogue,
// per CLAUDE.md › User Boundaries & Tenancy). It writes book_kinds + a universal
// kind↔genre link + a seed 'name' attribute in book_attributes (under the book's
// `universal` genre), all in one tx, and returns the created kind (KindID =
// book_kind_id). A duplicate (book_id, code) surfaces as a unique-violation
// (isUniqueViolation → 409). An FK/missing-universal-genre surfaces as a 23503
// (the book wasn't adopted) → the confirm handler maps it to a clean 422.
//
// The Tier-S confirm endpoint is the only caller; bookID is the token-bound book.
func (s *Server) createKindFromParams(ctx context.Context, bookID uuid.UUID, in kindCreateParams) (domain.EntityKind, error) {
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

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return domain.EntityKind{}, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	// The book's `universal` genre anchors the seed 'name' attr (O4). If the book
	// hasn't been adopted there is no universal genre → no row → the name-attr
	// insert below trips a 23503-style "not adopted" path. Resolve it up front so a
	// missing genre is a clean error rather than a partial kind.
	var universalGenreID string
	if err := tx.QueryRow(ctx,
		`SELECT genre_id FROM book_genres WHERE book_id=$1 AND code='universal' AND deprecated_at IS NULL`,
		bookID,
	).Scan(&universalGenreID); err != nil {
		// pgx.ErrNoRows here = book not adopted; surface as a foreign-key-shaped
		// error so the confirm handler returns 422 ("book not scaffolded").
		return domain.EntityKind{}, fmt.Errorf("book has no universal genre (adopt the book first): %w", errNotAdopted)
	}

	var kindID string
	if err := tx.QueryRow(ctx, `
		INSERT INTO book_kinds(book_id, code, name, description, icon, color, sort_order, is_hidden)
		VALUES ($1,$2,$3,$4,$5,$6,
			COALESCE((SELECT MAX(sort_order)+1 FROM book_kinds WHERE book_id=$1),1),
			false)
		RETURNING book_kind_id`,
		bookID, in.Code, in.Name, in.Description, in.Icon, in.Color,
	).Scan(&kindID); err != nil {
		return domain.EntityKind{}, err
	}

	// Link the new kind to the book's universal genre (O4 — anchors base attrs).
	if _, err := tx.Exec(ctx, `
		INSERT INTO book_kind_genres(book_id, kind_id, genre_id) VALUES ($1,$2,$3)
		ON CONFLICT DO NOTHING`, bookID, kindID, universalGenreID,
	); err != nil {
		return domain.EntityKind{}, err
	}

	// Seed a 'name' display attribute (under universal) so the kind is name-capable.
	nameAttr := domain.AttrDef{Code: "name", Name: "Name", FieldType: "text", IsRequired: true, IsActive: true, SortOrder: 0, GenreTags: []string{}}
	if err := tx.QueryRow(ctx, `
		INSERT INTO book_attributes(book_id, kind_id, genre_id, code, name, field_type, is_required, sort_order)
		VALUES ($1,$2,$3,'name','Name','text',true,0)
		RETURNING attr_id`,
		bookID, kindID, universalGenreID,
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
		GenreTags:   []string{"universal"},
		Attributes:  []domain.AttrDef{nameAttr},
	}, nil
}

// errNotAdopted marks a schema-create attempt against a book whose ontology hasn't
// been scaffolded (no `universal` genre). The confirm handler maps it to 422.
var errNotAdopted = errors.New("book ontology not adopted")

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

// createAttrDefFromParams inserts an attribute definition into the BOOK tier (O2)
// under in.KindID (a book_kind_id) + the book's `universal` genre, and returns it.
// A duplicate (book_id, kind_id, genre_id, code) surfaces as a unique-violation
// (→ 409). A KindID that isn't a live book kind, or a book with no universal genre,
// trips an FK (23503) → the confirm handler maps it to a clean 422. Shared core for
// the Tier-S confirm endpoint; bookID is the token-bound book.
func (s *Server) createAttrDefFromParams(ctx context.Context, bookID uuid.UUID, in attrCreateParams) (domain.AttrDef, error) {
	// SCHEMA-LOW1: defense-in-depth code/name guard (see createKindFromParams).
	if strings.TrimSpace(in.Code) == "" || strings.TrimSpace(in.Name) == "" {
		return domain.AttrDef{}, errors.New("code and name are required")
	}
	if in.FieldType == "" {
		in.FieldType = "text"
	}
	var attrDefID string
	// genre_id resolves to the book's universal genre in a subquery so a not-yet-
	// adopted book (no universal row) yields a NULL → NOT NULL violation surfaced as
	// 23503-shaped via isForeignKeyViolation upstream. kind_id must belong to bookID.
	err := s.pool.QueryRow(ctx, `
		INSERT INTO book_attributes(book_id, kind_id, genre_id, code, name, description, field_type, is_required, sort_order, options, auto_fill_prompt, translation_hint)
		SELECT $1, bk.book_kind_id,
		       (SELECT genre_id FROM book_genres WHERE book_id=$1 AND code='universal' AND deprecated_at IS NULL),
		       $3,$4,$5,$6,$7,$8,$9,$10,$11
		FROM book_kinds bk
		WHERE bk.book_id=$1 AND bk.book_kind_id=$2 AND bk.deprecated_at IS NULL
		RETURNING attr_id`,
		bookID, in.KindID, in.Code, in.Name, in.Description, in.FieldType, in.IsRequired, in.SortOrder, in.Options, in.AutoFillPrompt, in.TranslationHint,
	).Scan(&attrDefID)
	if err != nil {
		// pgx.ErrNoRows = the kind_id doesn't match a live book kind for this book
		// (deleted between propose and confirm, or never adopted) → FK-shaped 422.
		if errors.Is(err, pgx.ErrNoRows) {
			return domain.AttrDef{}, fmt.Errorf("kind not found in book ontology: %w", errNotAdopted)
		}
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
		GenreTags:       []string{"universal"},
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
