package api

// D-GKA-SYSTEM-TIER-ADMIN — admin-only WRITE surface for the System tier
// (system_genres / system_kinds / system_attributes). System defaults are
// platform-owned: a regular user never mutates them (CLAUDE.md › User Boundaries),
// they clone into their own tier. These endpoints are gated by an RS256 admin JWT
// (requireAdminScope, scope "admin:write") — a normal HS256 user token can never
// satisfy it. On a semantic edit the content_hash is recomputed the SAME way the
// seed/user tiers compute it, so G5 Sync detects the change for adopted books
// (D-GKA-SYNC-HASH-ON-ADMIN-EDIT).

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"github.com/jackc/pgx/v5"
)

const scopeAdminWrite = "admin:write"

// pemOrBase64 returns the raw PEM bytes from a value that is EITHER a literal PEM
// block or a base64-encoded one. Single-line base64 is convenient to pass through
// docker-compose env (a multi-line PEM there is awkward).
func pemOrBase64(v string) []byte {
	if strings.Contains(v, "BEGIN") {
		return []byte(v)
	}
	if dec, err := base64.StdEncoding.DecodeString(strings.TrimSpace(v)); err == nil {
		return dec
	}
	return []byte(v)
}

// decodeJSON decodes the request body into dst, writing a 400 + returning false on
// malformed JSON. Local to the admin handlers (the rest of the package decodes inline).
func decodeJSON(w http.ResponseWriter, r *http.Request, dst any) bool {
	if err := json.NewDecoder(r.Body).Decode(dst); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return false
	}
	return true
}

// ── System genres ──────────────────────────────────────────────────────────────

func (s *Server) createSystemGenre(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
		return
	}
	var in struct {
		Code      string `json:"code"`
		Name      string `json:"name"`
		Icon      string `json:"icon"`
		Color     string `json:"color"`
		SortOrder int    `json:"sort_order"`
	}
	if !decodeJSON(w, r, &in) {
		return
	}
	if strings.TrimSpace(in.Name) == "" {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "name is required")
		return
	}
	if strings.TrimSpace(in.Code) == "" {
		in.Code = slugify(in.Name)
	}
	if in.Code == "" {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "code could not be derived from name")
		return
	}
	if in.Color == "" {
		in.Color = "#6366f1"
	}
	var g genreResp
	g.Tier = "system"
	err := s.pool.QueryRow(r.Context(), `
		INSERT INTO system_genres (code, name, icon, color, sort_order, content_hash)
		VALUES ($1,$2,$3,$4,$5, md5($1||'|'||$2))
		RETURNING genre_id::text, code, name, icon, color, sort_order, created_at, updated_at`,
		in.Code, in.Name, in.Icon, in.Color, in.SortOrder,
	).Scan(&g.GenreID, &g.Code, &g.Name, &g.Icon, &g.Color, &g.SortOrder, &g.CreatedAt, &g.UpdatedAt)
	if isUniqueViolation(err) {
		writeError(w, http.StatusConflict, "GLOSS_GENRE_EXISTS", "a system genre with this code already exists")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "create system genre failed")
		return
	}
	writeJSON(w, http.StatusCreated, g)
}

func (s *Server) patchSystemGenre(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
		return
	}
	genreID, ok := parsePathUUID(w, r, "genre_id")
	if !ok {
		return
	}
	var in struct {
		Name      *string `json:"name"`
		Icon      *string `json:"icon"`
		Color     *string `json:"color"`
		SortOrder *int    `json:"sort_order"`
	}
	if !decodeJSON(w, r, &in) {
		return
	}
	var g genreResp
	g.Tier = "system"
	// content_hash recomputed from the post-update name (md5(code|name)) so Sync
	// sees the edit (D-GKA-SYNC-HASH-ON-ADMIN-EDIT).
	err := s.pool.QueryRow(r.Context(), `
		UPDATE system_genres SET
		  name       = COALESCE($2, name),
		  icon       = COALESCE($3, icon),
		  color      = COALESCE($4, color),
		  sort_order = COALESCE($5, sort_order),
		  content_hash = md5(code||'|'||COALESCE($2, name)),
		  updated_at = now()
		WHERE genre_id = $1
		RETURNING genre_id::text, code, name, icon, color, sort_order, created_at, updated_at`,
		genreID, in.Name, in.Icon, in.Color, in.SortOrder,
	).Scan(&g.GenreID, &g.Code, &g.Name, &g.Icon, &g.Color, &g.SortOrder, &g.CreatedAt, &g.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "GLOSS_GENRE_NOT_FOUND", "system genre not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "patch system genre failed")
		return
	}
	writeJSON(w, http.StatusOK, g)
}

func (s *Server) deleteSystemGenre(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
		return
	}
	genreID, ok := parsePathUUID(w, r, "genre_id")
	if !ok {
		return
	}
	// `universal` is mandatory (O4) — never deletable. Its attributes + kind links
	// cascade (FK ON DELETE CASCADE); adopted book rows reference it by source_ref
	// (a string, not FK) → they read as source_retired in Sync.
	tag, err := s.pool.Exec(r.Context(),
		`DELETE FROM system_genres WHERE genre_id=$1 AND code <> 'universal'`, genreID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete system genre failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_GENRE_NOT_FOUND", "system genre not found or not deletable")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// ── System kinds ───────────────────────────────────────────────────────────────
// system_kinds has no content_hash column; G5 Sync recomputes a kind's hash live
// from (code,name,description), so an edit is detected without a stored hash.

type systemKindResp struct {
	KindID      string  `json:"kind_id"`
	Tier        string  `json:"tier"`
	Code        string  `json:"code"`
	Name        string  `json:"name"`
	Description *string `json:"description,omitempty"`
	Icon        string  `json:"icon"`
	Color       string  `json:"color"`
	IsHidden    bool    `json:"is_hidden"`
	SortOrder   int     `json:"sort_order"`
}

func (s *Server) createSystemKind(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
		return
	}
	var in struct {
		Code        string  `json:"code"`
		Name        string  `json:"name"`
		Description *string `json:"description"`
		Icon        string  `json:"icon"`
		Color       string  `json:"color"`
		IsHidden    bool    `json:"is_hidden"`
		SortOrder   int     `json:"sort_order"`
	}
	if !decodeJSON(w, r, &in) {
		return
	}
	if strings.TrimSpace(in.Name) == "" {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "name is required")
		return
	}
	if strings.TrimSpace(in.Code) == "" {
		in.Code = slugify(in.Name)
	}
	if in.Code == "" {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "code could not be derived from name")
		return
	}
	if in.Color == "" {
		in.Color = "#6366f1"
	}
	k := systemKindResp{Tier: "system"}
	err := s.pool.QueryRow(r.Context(), `
		INSERT INTO system_kinds (code, name, description, icon, color, is_hidden, sort_order)
		VALUES ($1,$2,$3,$4,$5,$6,$7)
		RETURNING kind_id::text, code, name, description, icon, color, is_hidden, sort_order`,
		in.Code, in.Name, in.Description, in.Icon, in.Color, in.IsHidden, in.SortOrder,
	).Scan(&k.KindID, &k.Code, &k.Name, &k.Description, &k.Icon, &k.Color, &k.IsHidden, &k.SortOrder)
	if isUniqueViolation(err) {
		writeError(w, http.StatusConflict, "GLOSS_KIND_EXISTS", "a system kind with this code already exists")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "create system kind failed")
		return
	}
	writeJSON(w, http.StatusCreated, k)
}

func (s *Server) patchSystemKind(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
		return
	}
	kindID, ok := parsePathUUID(w, r, "kind_id")
	if !ok {
		return
	}
	var in struct {
		Name        *string `json:"name"`
		Description *string `json:"description"`
		Icon        *string `json:"icon"`
		Color       *string `json:"color"`
		IsHidden    *bool   `json:"is_hidden"`
		SortOrder   *int    `json:"sort_order"`
	}
	if !decodeJSON(w, r, &in) {
		return
	}
	k := systemKindResp{Tier: "system"}
	err := s.pool.QueryRow(r.Context(), `
		UPDATE system_kinds SET
		  name        = COALESCE($2, name),
		  description = COALESCE($3, description),
		  icon        = COALESCE($4, icon),
		  color       = COALESCE($5, color),
		  is_hidden   = COALESCE($6, is_hidden),
		  sort_order  = COALESCE($7, sort_order)
		WHERE kind_id = $1
		RETURNING kind_id::text, code, name, description, icon, color, is_hidden, sort_order`,
		kindID, in.Name, in.Description, in.Icon, in.Color, in.IsHidden, in.SortOrder,
	).Scan(&k.KindID, &k.Code, &k.Name, &k.Description, &k.Icon, &k.Color, &k.IsHidden, &k.SortOrder)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "GLOSS_KIND_NOT_FOUND", "system kind not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "patch system kind failed")
		return
	}
	writeJSON(w, http.StatusOK, k)
}

func (s *Server) deleteSystemKind(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
		return
	}
	kindID, ok := parsePathUUID(w, r, "kind_id")
	if !ok {
		return
	}
	// `unknown` is the extraction parking kind (E6) — never deletable. Attributes +
	// kind-genre links cascade.
	tag, err := s.pool.Exec(r.Context(),
		`DELETE FROM system_kinds WHERE kind_id=$1 AND code <> 'unknown'`, kindID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete system kind failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_KIND_NOT_FOUND", "system kind not found or not deletable")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// ── System attributes ──────────────────────────────────────────────────────────
// Keyed (kind × genre × code); content_hash recomputed via attrContentHash so Sync
// detects an edit. kind_id/genre_id must be live system rows (the FK enforces it).

func (s *Server) createSystemAttribute(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
		return
	}
	var in struct {
		KindID      string   `json:"kind_id"`
		GenreID     string   `json:"genre_id"`
		Code        string   `json:"code"`
		Name        string   `json:"name"`
		Description *string  `json:"description"`
		FieldType   string   `json:"field_type"`
		IsRequired  bool     `json:"is_required"`
		SortOrder   int      `json:"sort_order"`
		Options     []string `json:"options"`
	}
	if !decodeJSON(w, r, &in) {
		return
	}
	if strings.TrimSpace(in.Name) == "" || in.KindID == "" || in.GenreID == "" {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "kind_id, genre_id and name are required")
		return
	}
	if strings.TrimSpace(in.Code) == "" {
		in.Code = slugify(in.Name)
	}
	if in.FieldType == "" {
		in.FieldType = "text"
	}
	if in.Options == nil {
		in.Options = []string{}
	}
	hash := attrContentHash(in.Code, in.Name, in.Description, in.FieldType, in.IsRequired, in.Options)
	a := attributeResp{Tier: "system"}
	err := s.pool.QueryRow(r.Context(), `
		INSERT INTO system_attributes (kind_id, genre_id, code, name, description, field_type, is_required, sort_order, options, content_hash)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
		RETURNING attr_id::text, kind_id::text, genre_id::text, code, name, description, field_type, is_required, sort_order, options`,
		in.KindID, in.GenreID, in.Code, in.Name, in.Description, in.FieldType, in.IsRequired, in.SortOrder, in.Options, hash,
	).Scan(&a.AttrID, &a.KindID, &a.GenreID, &a.Code, &a.Name, &a.Description, &a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options)
	if isUniqueViolation(err) {
		writeError(w, http.StatusConflict, "GLOSS_ATTR_EXISTS", "an attribute with this code already exists for the (kind, genre)")
		return
	}
	if isForeignKeyViolation(err) {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "kind_id or genre_id is not a live system row")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "create system attribute failed")
		return
	}
	if a.Options == nil {
		a.Options = []string{}
	}
	writeJSON(w, http.StatusCreated, a)
}

func (s *Server) patchSystemAttribute(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
		return
	}
	attrID, ok := parsePathUUID(w, r, "attr_id")
	if !ok {
		return
	}
	var in struct {
		Name        *string  `json:"name"`
		Description *string  `json:"description"`
		FieldType   *string  `json:"field_type"`
		IsRequired  *bool    `json:"is_required"`
		SortOrder   *int     `json:"sort_order"`
		Options     []string `json:"options"`
	}
	if !decodeJSON(w, r, &in) {
		return
	}
	ctx := r.Context()
	// Read-modify-write so content_hash is recomputed from the merged row via the
	// shared attrContentHash (single source of truth with the seed/user tiers).
	cur := attributeResp{Tier: "system"}
	if err := s.pool.QueryRow(ctx, `
		SELECT attr_id::text, kind_id::text, genre_id::text, code, name, description, field_type, is_required, sort_order, options
		FROM system_attributes WHERE attr_id=$1`, attrID,
	).Scan(&cur.AttrID, &cur.KindID, &cur.GenreID, &cur.Code, &cur.Name, &cur.Description, &cur.FieldType, &cur.IsRequired, &cur.SortOrder, &cur.Options); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "GLOSS_ATTR_NOT_FOUND", "system attribute not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load system attribute failed")
		return
	}
	if in.Name != nil {
		cur.Name = *in.Name
	}
	if in.Description != nil {
		cur.Description = in.Description
	}
	if in.FieldType != nil {
		cur.FieldType = *in.FieldType
	}
	if in.IsRequired != nil {
		cur.IsRequired = *in.IsRequired
	}
	if in.SortOrder != nil {
		cur.SortOrder = *in.SortOrder
	}
	if in.Options != nil {
		cur.Options = in.Options
	}
	if cur.Options == nil {
		cur.Options = []string{}
	}
	hash := attrContentHash(cur.Code, cur.Name, cur.Description, cur.FieldType, cur.IsRequired, cur.Options)
	if _, err := s.pool.Exec(ctx, `
		UPDATE system_attributes SET
		  name=$2, description=$3, field_type=$4, is_required=$5, sort_order=$6, options=$7, content_hash=$8
		WHERE attr_id=$1`,
		attrID, cur.Name, cur.Description, cur.FieldType, cur.IsRequired, cur.SortOrder, cur.Options, hash,
	); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "patch system attribute failed")
		return
	}
	writeJSON(w, http.StatusOK, cur)
}

func (s *Server) deleteSystemAttribute(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
		return
	}
	attrID, ok := parsePathUUID(w, r, "attr_id")
	if !ok {
		return
	}
	tag, err := s.pool.Exec(r.Context(), `DELETE FROM system_attributes WHERE attr_id=$1`, attrID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete system attribute failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_ATTR_NOT_FOUND", "system attribute not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
