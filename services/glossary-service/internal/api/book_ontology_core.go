package api

import (
	"context"
	"errors"
	"strings"

	"github.com/google/uuid"
)

// T1 — shared book-tier create cores. The single source of truth for the book
// genre/kind/attribute INSERT logic (defaulting + FK guards), called by BOTH the
// HTTP handlers (book_ontology_handler.go) and the MCP tools (book_tools.go) so the
// two write paths can never diverge (the cascade-core / createKindFromParams pattern).

var (
	// errDuplicateBookCode → 409: a row with this code already exists in scope.
	errDuplicateBookCode = errors.New("book code already exists")
	// errBookFKNotLive → 422: an attribute references a kind/genre that is not a live
	// row of THIS book (a cross-tenant / deprecated reference the raw FK would accept).
	errBookFKNotLive = errors.New("kind or genre is not a live row of this book")
	// errInvalidFieldType → 422: an attribute field_type outside the allowed set (no DB
	// CHECK backstops it, so the core is the guard for BOTH the HTTP and MCP write paths).
	errInvalidFieldType = errors.New("invalid field_type (text|textarea|select|number|date|tags|url|boolean)")
	// errCannotClearSystemPersonFlag → 403 (C4/SD-C4, PP-4): an owner may not clear is_person on a
	// SYSTEM-adopted person kind (e.g. 'colleague') — that would re-enable AI biographies of a real,
	// non-consenting third party. Custom (user-authored) kinds stay togglable.
	errCannotClearSystemPersonFlag = errors.New("cannot disable the real-person flag on a system person kind (it protects a real, non-consenting person)")
)

type bookGenreCreateParams struct {
	Code, Name, Icon, Color string
	SortOrder               int
	Active                  *bool // nil → active (default)
}

type bookKindCreateParams struct {
	Code, Name  string
	Description *string
	Icon, Color string
	SortOrder   int
	IsHidden    bool
	IsPerson    bool // C4/SD-C4 — user-settable REAL-person flag on a custom kind (excludes it from AI wiki/enrich)
}

type bookAttrCreateParams struct {
	KindID, GenreID                 uuid.UUID
	Code, Name                      string
	Description                     *string
	FieldType                       string
	IsRequired                      bool
	SortOrder                       int
	Options                         []string
	AutoFillPrompt, TranslationHint *string
}

// createBookGenreCore inserts a book genre (+ activates it unless Active==false).
// Defaults icon/color/code identically for HTTP and MCP callers.
func (s *Server) createBookGenreCore(ctx context.Context, bookID uuid.UUID, p bookGenreCreateParams) (*bookGenreResp, error) {
	if strings.TrimSpace(p.Name) == "" {
		return nil, errors.New("name is required")
	}
	if p.Color == "" {
		p.Color = "#6366f1"
	}
	if strings.TrimSpace(p.Code) == "" {
		p.Code = slugify(p.Name)
	}
	if p.Code == "" {
		return nil, errors.New("code could not be derived from name")
	}
	active := p.Active == nil || *p.Active

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	var genreID uuid.UUID
	if err := tx.QueryRow(ctx, `
		INSERT INTO book_genres (book_id, code, name, icon, color, sort_order)
		VALUES ($1,$2,$3,$4,$5,$6) RETURNING genre_id`,
		bookID, p.Code, p.Name, p.Icon, p.Color, p.SortOrder,
	).Scan(&genreID); err != nil {
		if isUniqueViolation(err) {
			return nil, errDuplicateBookCode
		}
		return nil, err
	}
	if active {
		if _, err := tx.Exec(ctx,
			`INSERT INTO book_active_genres (book_id, genre_id) VALUES ($1,$2) ON CONFLICT DO NOTHING`,
			bookID, genreID); err != nil {
			return nil, err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return s.loadBookGenreOne(ctx, bookID, genreID)
}

// createBookKindCore inserts a book kind.
func (s *Server) createBookKindCore(ctx context.Context, bookID uuid.UUID, p bookKindCreateParams) (*bookKindResp, error) {
	if strings.TrimSpace(p.Name) == "" {
		return nil, errors.New("name is required")
	}
	if p.Icon == "" {
		p.Icon = "box"
	}
	if p.Color == "" {
		p.Color = "#6366f1"
	}
	if strings.TrimSpace(p.Code) == "" {
		p.Code = slugify(p.Name)
	}
	if p.Code == "" {
		return nil, errors.New("code could not be derived from name")
	}
	var kindID uuid.UUID
	if err := s.pool.QueryRow(ctx, `
		INSERT INTO book_kinds (book_id, code, name, description, icon, color, sort_order, is_hidden, is_person)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING book_kind_id`,
		bookID, p.Code, p.Name, p.Description, p.Icon, p.Color, p.SortOrder, p.IsHidden, p.IsPerson,
	).Scan(&kindID); err != nil {
		if isUniqueViolation(err) {
			return nil, errDuplicateBookCode
		}
		return nil, err
	}
	return s.loadBookKindOne(ctx, bookID, kindID)
}

// createBookAttributeCore inserts a book attribute after enforcing the book-local FK
// guard (kind + genre must be live rows of THIS book — errBookFKNotLive otherwise).
func (s *Server) createBookAttributeCore(ctx context.Context, bookID uuid.UUID, p bookAttrCreateParams) (*bookAttrResp, error) {
	if strings.TrimSpace(p.Name) == "" {
		return nil, errors.New("name is required")
	}
	if live, err := s.bookKindLive(ctx, bookID, p.KindID); err != nil {
		return nil, err
	} else if !live {
		return nil, errBookFKNotLive
	}
	if live, err := s.bookGenreLive(ctx, bookID, p.GenreID); err != nil {
		return nil, err
	} else if !live {
		return nil, errBookFKNotLive
	}
	if p.FieldType == "" {
		p.FieldType = "text"
	}
	if !isValidFieldType(p.FieldType) {
		return nil, errInvalidFieldType
	}
	if strings.TrimSpace(p.Code) == "" {
		p.Code = slugify(p.Name)
	}
	if p.Code == "" {
		return nil, errors.New("code could not be derived from name")
	}
	var attrID uuid.UUID
	if err := s.pool.QueryRow(ctx, `
		INSERT INTO book_attributes
		  (book_id, kind_id, genre_id, code, name, description, field_type, is_required,
		   sort_order, options, auto_fill_prompt, translation_hint, merge_strategy)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) RETURNING attr_id`,
		bookID, p.KindID, p.GenreID, p.Code, p.Name, p.Description, p.FieldType, p.IsRequired,
		p.SortOrder, p.Options, p.AutoFillPrompt, p.TranslationHint, seedMergeStrategy(p.Code, p.FieldType, p.IsRequired),
	).Scan(&attrID); err != nil {
		if isUniqueViolation(err) {
			return nil, errDuplicateBookCode
		}
		return nil, err
	}
	return s.loadBookAttrOne(ctx, bookID, attrID)
}
