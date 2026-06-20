package api

import (
	"context"
	"errors"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// T4 — shared System-tier write cores. The single source of truth for the
// system_genres/kinds/attributes INSERT/UPDATE/DELETE logic (defaulting, content_hash
// recompute, the universal/unknown delete guards), called by BOTH the HTTP admin
// handlers (system_admin_handler.go) and the admin MCP confirm effects (admin_confirm.go)
// so the two write paths can never diverge (the T1 core pattern). Authority (RS256
// admin:write) is checked by the CALLER before any core runs.

var (
	errDuplicateSystemCode   = errors.New("system code already exists")                   // → 409
	errSystemNotFound        = errors.New("system row not found")                         // → 404
	errSystemFKNotLive       = errors.New("kind_id or genre_id is not a live system row") // → 422
	errSystemNotDeletable    = errors.New("this system row is not deletable")             // → 404/422 (universal/unknown)
	errSystemNameRequired    = errors.New("name is required")                             // → 422
	errSystemCodeUnderivable = errors.New("code could not be derived from name")          // → 422
)

// ── code → id resolvers (System tier; codes are globally unique per entity) ────

func (s *Server) resolveSystemGenreID(ctx context.Context, code string) (uuid.UUID, error) {
	var id uuid.UUID
	err := s.pool.QueryRow(ctx, `SELECT genre_id FROM system_genres WHERE code=$1`, code).Scan(&id)
	return id, err
}

func (s *Server) resolveSystemKindID(ctx context.Context, code string) (uuid.UUID, error) {
	var id uuid.UUID
	err := s.pool.QueryRow(ctx, `SELECT kind_id FROM system_kinds WHERE code=$1`, code).Scan(&id)
	return id, err
}

// resolveSystemAttrID resolves a System attribute by (kind_code, genre_code, code) —
// attribute codes are unique only within a (kind × genre) cell.
func (s *Server) resolveSystemAttrID(ctx context.Context, kindCode, genreCode, code string) (uuid.UUID, error) {
	kindID, err := s.resolveSystemKindID(ctx, kindCode)
	if err != nil {
		return uuid.Nil, err
	}
	genreID, err := s.resolveSystemGenreID(ctx, genreCode)
	if err != nil {
		return uuid.Nil, err
	}
	var id uuid.UUID
	err = s.pool.QueryRow(ctx,
		`SELECT attr_id FROM system_attributes WHERE kind_id=$1 AND genre_id=$2 AND code=$3`,
		kindID, genreID, code).Scan(&id)
	return id, err
}

// ── System genres ──────────────────────────────────────────────────────────────

type systemGenreParams struct {
	Code, Name, Icon, Color string
	SortOrder               int
}

func (s *Server) createSystemGenreCore(ctx context.Context, p systemGenreParams) (*genreResp, error) {
	if strings.TrimSpace(p.Name) == "" {
		return nil, errSystemNameRequired
	}
	p.Name = strings.TrimSpace(p.Name)
	if strings.TrimSpace(p.Code) == "" {
		p.Code = slugify(p.Name)
	}
	if p.Code == "" {
		return nil, errSystemCodeUnderivable
	}
	if p.Color == "" {
		p.Color = "#6366f1"
	}
	g := &genreResp{Tier: "system"}
	err := s.pool.QueryRow(ctx, `
		INSERT INTO system_genres (code, name, icon, color, sort_order, content_hash)
		VALUES ($1,$2,$3,$4,$5, md5($1||'|'||$2))
		RETURNING genre_id::text, code, name, icon, color, sort_order, created_at, updated_at`,
		p.Code, p.Name, p.Icon, p.Color, p.SortOrder,
	).Scan(&g.GenreID, &g.Code, &g.Name, &g.Icon, &g.Color, &g.SortOrder, &g.CreatedAt, &g.UpdatedAt)
	if isUniqueViolation(err) {
		return nil, errDuplicateSystemCode
	}
	if err != nil {
		return nil, err
	}
	return g, nil
}

type systemGenrePatch struct {
	Name, Icon, Color *string
	SortOrder         *int
}

func (s *Server) patchSystemGenreCore(ctx context.Context, id uuid.UUID, p systemGenrePatch) (*genreResp, error) {
	g := &genreResp{Tier: "system"}
	// content_hash recomputed from the post-update name (md5(code|name)) so Sync sees
	// the edit (D-GKA-SYNC-HASH-ON-ADMIN-EDIT).
	err := s.pool.QueryRow(ctx, `
		UPDATE system_genres SET
		  name=COALESCE($2,name), icon=COALESCE($3,icon), color=COALESCE($4,color),
		  sort_order=COALESCE($5,sort_order),
		  content_hash=md5(code||'|'||COALESCE($2,name)), updated_at=now()
		WHERE genre_id=$1
		RETURNING genre_id::text, code, name, icon, color, sort_order, created_at, updated_at`,
		id, p.Name, p.Icon, p.Color, p.SortOrder,
	).Scan(&g.GenreID, &g.Code, &g.Name, &g.Icon, &g.Color, &g.SortOrder, &g.CreatedAt, &g.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, errSystemNotFound
	}
	if err != nil {
		return nil, err
	}
	return g, nil
}

// deleteSystemGenreCore removes a System genre. `universal` is mandatory (O4) — never
// deletable; a delete of it (or a missing id) yields errSystemNotDeletable.
func (s *Server) deleteSystemGenreCore(ctx context.Context, id uuid.UUID) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM system_genres WHERE genre_id=$1 AND code <> 'universal'`, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return errSystemNotDeletable
	}
	return nil
}

// ── System kinds ───────────────────────────────────────────────────────────────

type systemKindParams struct {
	Code, Name  string
	Description *string
	Icon, Color string
	IsHidden    bool
	SortOrder   int
}

func (s *Server) createSystemKindCore(ctx context.Context, p systemKindParams) (*systemKindResp, error) {
	if strings.TrimSpace(p.Name) == "" {
		return nil, errSystemNameRequired
	}
	p.Name = strings.TrimSpace(p.Name)
	if strings.TrimSpace(p.Code) == "" {
		p.Code = slugify(p.Name)
	}
	if p.Code == "" {
		return nil, errSystemCodeUnderivable
	}
	if p.Color == "" {
		p.Color = "#6366f1"
	}
	k := &systemKindResp{Tier: "system"}
	err := s.pool.QueryRow(ctx, `
		INSERT INTO system_kinds (code, name, description, icon, color, is_hidden, sort_order)
		VALUES ($1,$2,$3,$4,$5,$6,$7)
		RETURNING kind_id::text, code, name, description, icon, color, is_hidden, sort_order`,
		p.Code, p.Name, p.Description, p.Icon, p.Color, p.IsHidden, p.SortOrder,
	).Scan(&k.KindID, &k.Code, &k.Name, &k.Description, &k.Icon, &k.Color, &k.IsHidden, &k.SortOrder)
	if isUniqueViolation(err) {
		return nil, errDuplicateSystemCode
	}
	if err != nil {
		return nil, err
	}
	return k, nil
}

type systemKindPatch struct {
	Name, Description, Icon, Color *string
	IsHidden                       *bool
	SortOrder                      *int
}

func (s *Server) patchSystemKindCore(ctx context.Context, id uuid.UUID, p systemKindPatch) (*systemKindResp, error) {
	k := &systemKindResp{Tier: "system"}
	err := s.pool.QueryRow(ctx, `
		UPDATE system_kinds SET
		  name=COALESCE($2,name), description=COALESCE($3,description), icon=COALESCE($4,icon),
		  color=COALESCE($5,color), is_hidden=COALESCE($6,is_hidden), sort_order=COALESCE($7,sort_order)
		WHERE kind_id=$1
		RETURNING kind_id::text, code, name, description, icon, color, is_hidden, sort_order`,
		id, p.Name, p.Description, p.Icon, p.Color, p.IsHidden, p.SortOrder,
	).Scan(&k.KindID, &k.Code, &k.Name, &k.Description, &k.Icon, &k.Color, &k.IsHidden, &k.SortOrder)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, errSystemNotFound
	}
	if err != nil {
		return nil, err
	}
	return k, nil
}

// deleteSystemKindCore removes a System kind. `unknown` is the extraction parking kind
// (E6) — never deletable.
func (s *Server) deleteSystemKindCore(ctx context.Context, id uuid.UUID) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM system_kinds WHERE kind_id=$1 AND code <> 'unknown'`, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return errSystemNotDeletable
	}
	return nil
}

// ── System attributes ──────────────────────────────────────────────────────────

type systemAttrParams struct {
	KindID, GenreID uuid.UUID
	Code, Name      string
	Description     *string
	FieldType       string
	IsRequired      bool
	SortOrder       int
	Options         []string
}

func (s *Server) createSystemAttributeCore(ctx context.Context, p systemAttrParams) (*attributeResp, error) {
	if strings.TrimSpace(p.Name) == "" {
		return nil, errSystemNameRequired
	}
	p.Name = strings.TrimSpace(p.Name)
	if strings.TrimSpace(p.Code) == "" {
		p.Code = slugify(p.Name)
	}
	if p.Code == "" {
		return nil, errSystemCodeUnderivable
	}
	if p.FieldType == "" {
		p.FieldType = "text"
	}
	if !isValidFieldType(p.FieldType) {
		return nil, errInvalidFieldType
	}
	if p.Options == nil {
		p.Options = []string{}
	}
	hash := attrContentHash(p.Code, p.Name, p.Description, p.FieldType, p.IsRequired, p.Options)
	a := &attributeResp{Tier: "system"}
	err := s.pool.QueryRow(ctx, `
		INSERT INTO system_attributes (kind_id, genre_id, code, name, description, field_type, is_required, sort_order, options, content_hash)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
		RETURNING attr_id::text, kind_id::text, genre_id::text, code, name, description, field_type, is_required, sort_order, options`,
		p.KindID, p.GenreID, p.Code, p.Name, p.Description, p.FieldType, p.IsRequired, p.SortOrder, p.Options, hash,
	).Scan(&a.AttrID, &a.KindID, &a.GenreID, &a.Code, &a.Name, &a.Description, &a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options)
	if isUniqueViolation(err) {
		return nil, errDuplicateSystemCode
	}
	if isForeignKeyViolation(err) {
		return nil, errSystemFKNotLive
	}
	if err != nil {
		return nil, err
	}
	if a.Options == nil {
		a.Options = []string{}
	}
	return a, nil
}

type systemAttrPatch struct {
	Name, Description, FieldType *string
	IsRequired                   *bool
	SortOrder                    *int
	Options                      *[]string
}

// patchSystemAttributeCore read-modify-writes so content_hash is recomputed from the
// merged row via the shared attrContentHash (one source of truth across tiers).
func (s *Server) patchSystemAttributeCore(ctx context.Context, id uuid.UUID, p systemAttrPatch) (*attributeResp, error) {
	cur := &attributeResp{Tier: "system"}
	if err := s.pool.QueryRow(ctx, `
		SELECT attr_id::text, kind_id::text, genre_id::text, code, name, description, field_type, is_required, sort_order, options
		FROM system_attributes WHERE attr_id=$1`, id,
	).Scan(&cur.AttrID, &cur.KindID, &cur.GenreID, &cur.Code, &cur.Name, &cur.Description, &cur.FieldType, &cur.IsRequired, &cur.SortOrder, &cur.Options); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, errSystemNotFound
		}
		return nil, err
	}
	if p.Name != nil {
		cur.Name = *p.Name
	}
	if p.Description != nil {
		cur.Description = p.Description
	}
	if p.FieldType != nil {
		cur.FieldType = *p.FieldType
	}
	if p.IsRequired != nil {
		cur.IsRequired = *p.IsRequired
	}
	if p.SortOrder != nil {
		cur.SortOrder = *p.SortOrder
	}
	if p.Options != nil {
		cur.Options = *p.Options
	}
	if cur.Options == nil {
		cur.Options = []string{}
	}
	hash := attrContentHash(cur.Code, cur.Name, cur.Description, cur.FieldType, cur.IsRequired, cur.Options)
	if _, err := s.pool.Exec(ctx, `
		UPDATE system_attributes SET name=$2, description=$3, field_type=$4, is_required=$5, sort_order=$6, options=$7, content_hash=$8
		WHERE attr_id=$1`,
		id, cur.Name, cur.Description, cur.FieldType, cur.IsRequired, cur.SortOrder, cur.Options, hash,
	); err != nil {
		return nil, err
	}
	return cur, nil
}

func (s *Server) deleteSystemAttributeCore(ctx context.Context, id uuid.UUID) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM system_attributes WHERE attr_id=$1`, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return errSystemNotFound
	}
	return nil
}
