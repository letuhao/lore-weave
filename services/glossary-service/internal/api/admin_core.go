package api

import (
	"context"
	"errors"
	"strings"
	"time"

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
	// G-C8 soft-delete/restore sentinels.
	errSystemNotInTrash       = errors.New("system row is not in the recycle bin")                   // → 404
	errSystemParentDeprecated = errors.New("restore the parent kind/genre first")                    // → 422
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

// deleteSystemGenreCore SOFT-deletes a System genre (G-C8): sets deprecated_at instead
// of DELETE, so it is restorable from the recycle bin. `universal` is mandatory (O4) —
// never deletable; a delete of it (or a missing/already-deprecated id) yields
// errSystemNotDeletable. The genre's attributes are cascade-deprecated in the SAME
// transaction (the FK ON DELETE CASCADE no longer fires on a soft delete, so the cascade
// is explicit). The system_kind_genres link rows are left intact so a restore re-attaches.
func (s *Server) deleteSystemGenreCore(ctx context.Context, id uuid.UUID) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	tag, err := tx.Exec(ctx, `UPDATE system_genres SET deprecated_at=now() WHERE genre_id=$1 AND code <> 'universal' AND deprecated_at IS NULL`, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return errSystemNotDeletable
	}
	if _, err := tx.Exec(ctx, `UPDATE system_attributes SET deprecated_at=now() WHERE genre_id=$1 AND deprecated_at IS NULL`, id); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// restoreSystemGenreCore clears deprecated_at on a soft-deleted System genre (G-C8). Per
// the P0 restore semantics, restoring a genre un-hides ONLY the genre — its cascade-
// deprecated attributes are restored individually (so an attribute independently deleted
// earlier is not accidentally resurrected). A row not currently in the bin yields
// errSystemNotInTrash.
func (s *Server) restoreSystemGenreCore(ctx context.Context, id uuid.UUID) (*genreResp, error) {
	g := &genreResp{Tier: "system"}
	err := s.pool.QueryRow(ctx, `
		UPDATE system_genres SET deprecated_at=NULL, updated_at=now()
		WHERE genre_id=$1 AND deprecated_at IS NOT NULL
		RETURNING genre_id::text, code, name, icon, color, sort_order, created_at, updated_at`,
		id,
	).Scan(&g.GenreID, &g.Code, &g.Name, &g.Icon, &g.Color, &g.SortOrder, &g.CreatedAt, &g.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, errSystemNotInTrash
	}
	if err != nil {
		return nil, err
	}
	return g, nil
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

// deleteSystemKindCore SOFT-deletes a System kind (G-C8). `unknown` is the extraction
// parking kind (E6) — never deletable. The kind's attributes are cascade-deprecated in
// the same transaction.
func (s *Server) deleteSystemKindCore(ctx context.Context, id uuid.UUID) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	tag, err := tx.Exec(ctx, `UPDATE system_kinds SET deprecated_at=now() WHERE kind_id=$1 AND code <> 'unknown' AND deprecated_at IS NULL`, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return errSystemNotDeletable
	}
	if _, err := tx.Exec(ctx, `UPDATE system_attributes SET deprecated_at=now() WHERE kind_id=$1 AND deprecated_at IS NULL`, id); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// restoreSystemKindCore clears deprecated_at on a soft-deleted System kind (G-C8).
// Restores ONLY the kind (its attributes are restored individually). system_kinds has no
// updated_at column.
func (s *Server) restoreSystemKindCore(ctx context.Context, id uuid.UUID) (*systemKindResp, error) {
	k := &systemKindResp{Tier: "system"}
	err := s.pool.QueryRow(ctx, `
		UPDATE system_kinds SET deprecated_at=NULL
		WHERE kind_id=$1 AND deprecated_at IS NOT NULL
		RETURNING kind_id::text, code, name, description, icon, color, is_hidden, sort_order`,
		id,
	).Scan(&k.KindID, &k.Code, &k.Name, &k.Description, &k.Icon, &k.Color, &k.IsHidden, &k.SortOrder)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, errSystemNotInTrash
	}
	if err != nil {
		return nil, err
	}
	return k, nil
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
	// G-C8: a System attribute must never be created under a SOFT-DELETED kind/genre — the
	// FK only checks existence, and a deprecated parent would make the new attribute an
	// invisible orphan that resurfaces if the parent is later restored. Reject up front.
	var parentsLive bool
	if err := s.pool.QueryRow(ctx, `SELECT
		EXISTS(SELECT 1 FROM system_kinds  WHERE kind_id=$1  AND deprecated_at IS NULL)
		AND EXISTS(SELECT 1 FROM system_genres WHERE genre_id=$2 AND deprecated_at IS NULL)`,
		p.KindID, p.GenreID).Scan(&parentsLive); err != nil {
		return nil, err
	}
	if !parentsLive {
		return nil, errSystemFKNotLive
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

// deleteSystemAttributeCore SOFT-deletes a single System attribute (G-C8).
func (s *Server) deleteSystemAttributeCore(ctx context.Context, id uuid.UUID) error {
	tag, err := s.pool.Exec(ctx, `UPDATE system_attributes SET deprecated_at=now() WHERE attr_id=$1 AND deprecated_at IS NULL`, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return errSystemNotFound
	}
	return nil
}

// restoreSystemAttributeCore clears deprecated_at on a soft-deleted System attribute
// (G-C8). Guarded: a restored attribute under a still-deprecated kind/genre would be
// invisible in merged reads (they filter the parent), so restore is BLOCKED with
// errSystemParentDeprecated until the parent is restored first.
func (s *Server) restoreSystemAttributeCore(ctx context.Context, id uuid.UUID) (*attributeResp, error) {
	var parentsLive bool
	err := s.pool.QueryRow(ctx, `
		SELECT (sk.deprecated_at IS NULL AND sg.deprecated_at IS NULL)
		FROM system_attributes sa
		JOIN system_kinds  sk ON sk.kind_id  = sa.kind_id
		JOIN system_genres sg ON sg.genre_id = sa.genre_id
		WHERE sa.attr_id=$1 AND sa.deprecated_at IS NOT NULL`, id,
	).Scan(&parentsLive)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, errSystemNotInTrash
	}
	if err != nil {
		return nil, err
	}
	if !parentsLive {
		return nil, errSystemParentDeprecated
	}
	a := &attributeResp{Tier: "system"}
	err = s.pool.QueryRow(ctx, `
		UPDATE system_attributes SET deprecated_at=NULL
		WHERE attr_id=$1 AND deprecated_at IS NOT NULL
		RETURNING attr_id::text, kind_id::text, genre_id::text, code, name, description, field_type, is_required, sort_order, options`,
		id,
	).Scan(&a.AttrID, &a.KindID, &a.GenreID, &a.Code, &a.Name, &a.Description, &a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, errSystemNotInTrash
	}
	if err != nil {
		return nil, err
	}
	if a.Options == nil {
		a.Options = []string{}
	}
	return a, nil
}

// ── Recycle bin (list-deprecated) ────────────────────────────────────────────────

// systemTrashRow is one soft-deleted System row for the recycle bin. KindCode/GenreCode/
// FieldType are populated for attributes only (so the bin can show the cell context even
// when the parent kind/genre is itself deprecated).
type systemTrashRow struct {
	ID           string    `json:"id"`
	Code         string    `json:"code"`
	Name         string    `json:"name"`
	KindCode     string    `json:"kind_code,omitempty"`
	GenreCode    string    `json:"genre_code,omitempty"`
	FieldType    string    `json:"field_type,omitempty"`
	DeprecatedAt time.Time `json:"deprecated_at"`
}

type systemTrashResp struct {
	Genres     []systemTrashRow `json:"genres"`
	Kinds      []systemTrashRow `json:"kinds"`
	Attributes []systemTrashRow `json:"attributes"`
}

// listSystemTrashCore returns every soft-deleted System genre/kind/attribute, newest
// first, for the CMS recycle bin (G-C8). Attribute rows carry their kind/genre codes via
// plain JOINs (codes survive deprecation of the parent).
func (s *Server) listSystemTrashCore(ctx context.Context) (*systemTrashResp, error) {
	out := &systemTrashResp{Genres: []systemTrashRow{}, Kinds: []systemTrashRow{}, Attributes: []systemTrashRow{}}

	grows, err := s.pool.Query(ctx, `
		SELECT genre_id::text, code, name, deprecated_at
		FROM system_genres WHERE deprecated_at IS NOT NULL ORDER BY deprecated_at DESC`)
	if err != nil {
		return nil, err
	}
	defer grows.Close()
	for grows.Next() {
		var r systemTrashRow
		if err := grows.Scan(&r.ID, &r.Code, &r.Name, &r.DeprecatedAt); err != nil {
			return nil, err
		}
		out.Genres = append(out.Genres, r)
	}
	if err := grows.Err(); err != nil {
		return nil, err
	}

	krows, err := s.pool.Query(ctx, `
		SELECT kind_id::text, code, name, deprecated_at
		FROM system_kinds WHERE deprecated_at IS NOT NULL ORDER BY deprecated_at DESC`)
	if err != nil {
		return nil, err
	}
	defer krows.Close()
	for krows.Next() {
		var r systemTrashRow
		if err := krows.Scan(&r.ID, &r.Code, &r.Name, &r.DeprecatedAt); err != nil {
			return nil, err
		}
		out.Kinds = append(out.Kinds, r)
	}
	if err := krows.Err(); err != nil {
		return nil, err
	}

	arows, err := s.pool.Query(ctx, `
		SELECT sa.attr_id::text, sa.code, sa.name, sk.code, sg.code, sa.field_type, sa.deprecated_at
		FROM system_attributes sa
		JOIN system_kinds  sk ON sk.kind_id  = sa.kind_id
		JOIN system_genres sg ON sg.genre_id = sa.genre_id
		WHERE sa.deprecated_at IS NOT NULL ORDER BY sa.deprecated_at DESC`)
	if err != nil {
		return nil, err
	}
	defer arows.Close()
	for arows.Next() {
		var r systemTrashRow
		if err := arows.Scan(&r.ID, &r.Code, &r.Name, &r.KindCode, &r.GenreCode, &r.FieldType, &r.DeprecatedAt); err != nil {
			return nil, err
		}
		out.Attributes = append(out.Attributes, r)
	}
	if err := arows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}
