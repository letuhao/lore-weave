package api

// SS-4 — T2 per-user kind CRUD (docs/03_planning/93_SS4_USER_KIND_CRUD_DETAILED_DESIGN.md).
//
// Per-user kinds live in user_kinds/user_kind_attributes, scoped by
// owner_user_id (CLAUDE.md › User Boundaries & Tenancy). Every query filters on
// the caller's user id, so user A can never read or mutate user B's kinds — the
// fix for the old globally-mutable system_kinds defect. System (T1) kinds remain
// admin/seed-only; a user CLONES a T1 kind into their own tier, never edits the
// shared original.
//
// Entities cannot yet reference a T2 kind (glossary_entities.kind_id stays the
// live system_kinds ref until SS-7). The delete guards below probe the future
// glossary_entities.user_kind_id / entity_attribute_values.user_attr_def_id
// columns and treat "column does not exist" (SQLSTATE 42703) as zero — so they
// are correct now and become fully functional once SS-7 adds those columns.

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

// ── response types ───────────────────────────────────────────────────────────

type userKindAttrResp struct {
	AttrID      string    `json:"attr_id"`
	UserKindID  string    `json:"user_kind_id"`
	Code        string    `json:"code"`
	Name        string    `json:"name"`
	Description *string   `json:"description,omitempty"`
	FieldType   string    `json:"field_type"`
	IsRequired  bool      `json:"is_required"`
	SortOrder   int       `json:"sort_order"`
	Options     []string  `json:"options"`
	CreatedAt   time.Time `json:"created_at"`
}

type userKindSummaryResp struct {
	UserKindID       string    `json:"user_kind_id"`
	OwnerUserID      string    `json:"owner_user_id"`
	Code             string    `json:"code"`
	Name             string    `json:"name"`
	Description      *string   `json:"description,omitempty"`
	Icon             string    `json:"icon"`
	Color            string    `json:"color"`
	GenreTags        []string  `json:"genre_tags"`
	IsActive         bool      `json:"is_active"`
	// C4/SD-C4 · D-WIKI-PERSON-USER-TIER — the REAL-person flag on the USER tier (mirrors the
	// book tier). A user-authored person kind must carry it so the adopt-clone into a book keeps
	// is_person=true and the wiki-gen/enrichment `NOT is_person` filters exclude a real person.
	IsPerson         bool      `json:"is_person"`
	ClonedFromKindID *string   `json:"cloned_from_kind_id,omitempty"`
	AttributeCount   int       `json:"attribute_count"`
	CreatedAt        time.Time `json:"created_at"`
	UpdatedAt        time.Time `json:"updated_at"`
}

type userKindDetailResp struct {
	userKindSummaryResp
	Attributes []userKindAttrResp `json:"attributes"`
}

type userKindListResp struct {
	Items  []userKindSummaryResp `json:"items"`
	Total  int                   `json:"total"`
	Limit  int                   `json:"limit"`
	Offset int                   `json:"offset"`
}

type userKindTrashItem struct {
	UserKindID string    `json:"user_kind_id"`
	Code       string    `json:"code"`
	Name       string    `json:"name"`
	Icon       string    `json:"icon"`
	Color      string    `json:"color"`
	DeletedAt  time.Time `json:"deleted_at"`
}

// ── helpers ──────────────────────────────────────────────────────────────────

// slugify converts a display name to a lowercase underscore code:
// "My Character" → "my_character". Used when the client omits an explicit code.
func slugify(name string) string {
	s := strings.ToLower(strings.TrimSpace(name))
	s = strings.Map(func(r rune) rune {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') {
			return r
		}
		return '_'
	}, s)
	for strings.Contains(s, "__") {
		s = strings.ReplaceAll(s, "__", "_")
	}
	return strings.Trim(s, "_")
}

// verifyUserKindOwner confirms user_kind_id belongs to userID and is not purged.
// Writes the 404/500 response itself; returns true only when the caller owns it.
func (s *Server) verifyUserKindOwner(w http.ResponseWriter, ctx context.Context, userKindID, userID uuid.UUID) bool {
	// Edit endpoints operate on LIVE kinds only: a soft-deleted (trashed) kind is
	// not editable (restore it first) — without the deleted_at guard a patch/attr
	// op would mutate a trashed row then 500 on the deleted_at-filtered reload.
	var exists bool
	if err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM user_kinds
		               WHERE user_kind_id=$1 AND owner_user_id=$2
		                 AND deleted_at IS NULL
		                 AND permanently_deleted_at IS NULL)`,
		userKindID, userID,
	).Scan(&exists); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "db error")
		return false
	}
	if !exists {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "user kind not found")
		return false
	}
	return true
}

// loadUserKindDetail fetches kind metadata + all non-deleted attributes, scoped
// to the owner. Returns pgx.ErrNoRows when not found or not owned by userID.
func (s *Server) loadUserKindDetail(ctx context.Context, userKindID, userID uuid.UUID) (*userKindDetailResp, error) {
	var d userKindDetailResp
	err := s.pool.QueryRow(ctx, `
		SELECT uk.user_kind_id, uk.owner_user_id, uk.code, uk.name, uk.description,
		       uk.icon, uk.color, uk.is_active, uk.is_person,
		       uk.cloned_from_kind_id, uk.created_at, uk.updated_at,
		       COUNT(uka.attr_id) AS attribute_count
		FROM user_kinds uk
		LEFT JOIN user_kind_attributes uka
		  ON uka.user_kind_id = uk.user_kind_id AND uka.deleted_at IS NULL
		WHERE uk.user_kind_id = $1
		  AND uk.owner_user_id = $2
		  AND uk.permanently_deleted_at IS NULL
		  AND uk.deleted_at IS NULL
		GROUP BY uk.user_kind_id`,
		userKindID, userID,
	).Scan(
		&d.UserKindID, &d.OwnerUserID, &d.Code, &d.Name, &d.Description,
		&d.Icon, &d.Color, &d.IsActive, &d.IsPerson,
		&d.ClonedFromKindID, &d.CreatedAt, &d.UpdatedAt,
		&d.AttributeCount,
	)
	if err != nil {
		return nil, err
	}
	// G4e: genre_tags column dropped — genre membership moved to user_kind_genres.
	// The response field stays for back-compat, always empty here.
	d.GenreTags = []string{}

	rows, err := s.pool.Query(ctx, `
		SELECT attr_id, user_kind_id, code, name, description,
		       field_type, is_required, sort_order, options, created_at
		FROM user_kind_attributes
		WHERE user_kind_id = $1 AND deleted_at IS NULL
		ORDER BY sort_order ASC, created_at ASC`,
		userKindID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	d.Attributes = []userKindAttrResp{}
	for rows.Next() {
		var a userKindAttrResp
		if err := rows.Scan(
			&a.AttrID, &a.UserKindID, &a.Code, &a.Name, &a.Description,
			&a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options, &a.CreatedAt,
		); err != nil {
			return nil, err
		}
		if a.Options == nil {
			a.Options = []string{}
		}
		d.Attributes = append(d.Attributes, a)
	}
	return &d, rows.Err()
}

// ── kind CRUD ────────────────────────────────────────────────────────────────

func (s *Server) listUserKinds(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}

	q := r.URL.Query()
	limit := parseIntDefault(q.Get("limit"), 20)
	offset := parseIntDefault(q.Get("offset"), 0)
	if limit > 100 {
		limit = 100
	}
	if limit < 1 {
		limit = 1
	}
	if offset < 0 {
		offset = 0
	}

	// Columns are qualified with the `uk.` alias throughout: the list query
	// LEFT JOINs user_kind_attributes, which ALSO has a deleted_at column, so an
	// unqualified `deleted_at` would be ambiguous. The count query aliases the
	// table `uk` too so the same WHERE fragment is reusable.
	where := []string{"uk.owner_user_id = $1", "uk.deleted_at IS NULL", "uk.permanently_deleted_at IS NULL"}
	args := []any{userID}
	argN := 2

	switch q.Get("is_active") {
	case "true":
		where = append(where, fmt.Sprintf("uk.is_active = $%d", argN))
		args = append(args, true)
		argN++
	case "false":
		where = append(where, fmt.Sprintf("uk.is_active = $%d", argN))
		args = append(args, false)
		argN++
	}
	switch q.Get("cloned_from") {
	case "system":
		where = append(where, "uk.cloned_from_kind_id IS NOT NULL")
	case "scratch":
		where = append(where, "uk.cloned_from_kind_id IS NULL")
	}

	orderClause := "created_at DESC"
	if q.Get("sort") == "name" {
		orderClause = "name ASC"
	}

	ctx := r.Context()
	whereSQL := strings.Join(where, " AND ")

	var total int
	if err := s.pool.QueryRow(ctx,
		"SELECT COUNT(*) FROM user_kinds uk WHERE "+whereSQL, args...,
	).Scan(&total); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count failed")
		return
	}

	args = append(args, limit, offset)
	listSQL := fmt.Sprintf(`
		SELECT uk.user_kind_id, uk.owner_user_id, uk.code, uk.name, uk.description,
		       uk.icon, uk.color, uk.is_active, uk.is_person,
		       uk.cloned_from_kind_id, uk.created_at, uk.updated_at,
		       COUNT(uka.attr_id) AS attribute_count
		FROM user_kinds uk
		LEFT JOIN user_kind_attributes uka
		  ON uka.user_kind_id = uk.user_kind_id AND uka.deleted_at IS NULL
		WHERE %s
		GROUP BY uk.user_kind_id
		ORDER BY uk.%s
		LIMIT $%d OFFSET $%d`, whereSQL, orderClause, argN, argN+1)

	rows, err := s.pool.Query(ctx, listSQL, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer rows.Close()

	items := []userKindSummaryResp{}
	for rows.Next() {
		var uk userKindSummaryResp
		if err := rows.Scan(
			&uk.UserKindID, &uk.OwnerUserID, &uk.Code, &uk.Name, &uk.Description,
			&uk.Icon, &uk.Color, &uk.IsActive, &uk.IsPerson,
			&uk.ClonedFromKindID, &uk.CreatedAt, &uk.UpdatedAt, &uk.AttributeCount,
		); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return
		}
		// G4e: genre_tags column dropped; response field stays empty for back-compat.
		uk.GenreTags = []string{}
		items = append(items, uk)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
		return
	}

	writeJSON(w, http.StatusOK, userKindListResp{Items: items, Total: total, Limit: limit, Offset: offset})
}

func (s *Server) createUserKind(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}

	var in struct {
		Code            string   `json:"code"`
		Name            string   `json:"name"`
		Description     *string  `json:"description"`
		Icon            string   `json:"icon"`
		Color           string   `json:"color"`
		GenreTags       []string `json:"genre_tags"`
		IsPerson        bool     `json:"is_person"` // C4/SD-C4 · D-WIKI-PERSON-USER-TIER — REAL-person flag
		CloneFromKindID *string  `json:"clone_from_kind_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	if strings.TrimSpace(in.Name) == "" {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "name is required")
		return
	}
	in.Name = strings.TrimSpace(in.Name) // normalize identically to the MCP tool path
	if in.Icon == "" {
		in.Icon = "box"
	}
	if in.Color == "" {
		in.Color = "#6366f1"
	}
	if in.GenreTags == nil {
		in.GenreTags = []string{}
	}
	if strings.TrimSpace(in.Code) == "" {
		in.Code = slugify(in.Name)
	}
	if in.Code == "" {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "code could not be derived from name")
		return
	}

	var cloneFromKindID *uuid.UUID
	if in.CloneFromKindID != nil && *in.CloneFromKindID != "" {
		id, err := uuid.Parse(*in.CloneFromKindID)
		if err != nil {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "invalid clone_from_kind_id")
			return
		}
		cloneFromKindID = &id
	}

	ctx := r.Context()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "tx failed")
		return
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	// G4e: user_kinds.genre_tags is dropped (flat-genre drift replaced by
	// user_kind_genres). The request still ACCEPTS genre_tags for back-compat but it
	// is no longer persisted; genre membership is set via the user-kind-genres link.
	var ukID uuid.UUID
	err = tx.QueryRow(ctx, `
		INSERT INTO user_kinds
		  (owner_user_id, code, name, description, icon, color, is_person, cloned_from_kind_id)
		VALUES ($1,$2,$3,$4,$5,$6,
		        -- cold-review HIGH: CLONING a system person-kind (e.g. 'colleague') is the PRIMARY way a
		        -- user gets a person kind; inherit is_person from the source so the flag isn't silently
		        -- dropped to false and re-opened as a leak. An explicit is_person=true on a from-scratch
		        -- kind still wins; a NULL clone source COALESCEs to false so it's just in.IsPerson.
		        $7 OR COALESCE((SELECT sk.is_person FROM system_kinds sk WHERE sk.kind_id = $8), false),
		        $8)
		RETURNING user_kind_id`,
		userID, in.Code, in.Name, in.Description, in.Icon, in.Color, in.IsPerson, cloneFromKindID,
	).Scan(&ukID)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "GLOSS_DUPLICATE_CODE", "a user kind with this code already exists")
			return
		}
		// clone_from_kind_id that isn't a real system kind trips the FK (23503) —
		// surface a clean 422 rather than a 500.
		if isForeignKeyViolation(err) {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "clone_from_kind_id is not a system kind")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "insert failed")
		return
	}

	// Clone: copy the T1 system kind's base attribute definitions into this user
	// kind. G4: system attrs now live in system_attributes keyed (kind,genre,code);
	// the kind's base attrs are its `universal`-genre rows (the seed lifts every
	// attr there). Copy only the universal set so the clone gets one row per code.
	if cloneFromKindID != nil {
		if _, err := tx.Exec(ctx, `
			INSERT INTO user_kind_attributes
			  (user_kind_id, code, name, description, field_type, is_required, sort_order, options)
			SELECT $1, sa.code, sa.name, sa.description, sa.field_type, sa.is_required, sa.sort_order, sa.options
			FROM system_attributes sa
			JOIN system_genres g ON g.genre_id = sa.genre_id AND g.code = 'universal' AND g.deprecated_at IS NULL
			WHERE sa.kind_id = $2 AND sa.deprecated_at IS NULL
			ORDER BY sa.sort_order`,
			ukID, cloneFromKindID,
		); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "clone attrs failed")
			return
		}
	}

	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "commit failed")
		return
	}

	detail, err := s.loadUserKindDetail(ctx, ukID, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
		return
	}
	writeJSON(w, http.StatusCreated, detail)
}

func (s *Server) getUserKind(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	userKindID, ok := parsePathUUID(w, r, "user_kind_id")
	if !ok {
		return
	}

	detail, err := s.loadUserKindDetail(r.Context(), userKindID, userID)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "user kind not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

func (s *Server) patchUserKind(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	userKindID, ok := parsePathUUID(w, r, "user_kind_id")
	if !ok {
		return
	}
	if !s.verifyUserKindOwner(w, r.Context(), userKindID, userID) {
		return
	}

	var in map[string]json.RawMessage
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}

	setClauses := []string{}
	args := []any{}
	argN := 1

	if raw, ok := in["name"]; ok {
		var v string
		if err := json.Unmarshal(raw, &v); err != nil || strings.TrimSpace(v) == "" {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid name")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("name = $%d", argN))
		args = append(args, strings.TrimSpace(v)) // normalize identically to the MCP tool path
		argN++
	}
	if raw, ok := in["description"]; ok {
		var v *string
		if err := json.Unmarshal(raw, &v); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid description")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("description = $%d", argN))
		args = append(args, v)
		argN++
	}
	if raw, ok := in["icon"]; ok {
		var v string
		if err := json.Unmarshal(raw, &v); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid icon")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("icon = $%d", argN))
		args = append(args, v)
		argN++
	}
	if raw, ok := in["color"]; ok {
		var v string
		if err := json.Unmarshal(raw, &v); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid color")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("color = $%d", argN))
		args = append(args, v)
		argN++
	}
	if raw, ok := in["genre_tags"]; ok {
		// G4e: genre_tags column dropped. Still validate the shape for back-compat
		// but DO NOT persist — genre membership moves to user_kind_genres.
		var v []string
		if err := json.Unmarshal(raw, &v); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid genre_tags")
			return
		}
	}
	if raw, ok := in["is_active"]; ok {
		var v bool
		if err := json.Unmarshal(raw, &v); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid is_active")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("is_active = $%d", argN))
		args = append(args, v)
		argN++
	}
	if raw, ok := in["is_person"]; ok {
		// C4/SD-C4 · D-WIKI-PERSON-USER-TIER — the REAL-person flag on the user tier. Setting it true
		// closes the leak (a user-authored person kind now carries is_person into the adopt-clone). A
		// from-scratch kind (no clone source) is freely togglable both ways — the owner classified it.
		var v bool
		if err := json.Unmarshal(raw, &v); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid is_person")
			return
		}
		if !v {
			// cold-review parity with the book-tier MED-2 guard: PP-4 protects the THIRD PARTY, not
			// owner preference. A kind CLONED from a system PERSON kind (e.g. 'colleague') may not have
			// is_person cleared — that would re-enable AI biographies of a real, non-consenting person
			// after adopt. A from-scratch kind (cloned_from_kind_id IS NULL) stays clearable.
			var clonedFromIsPerson bool
			if qerr := s.pool.QueryRow(r.Context(),
				`SELECT COALESCE(sk.is_person, false)
				 FROM user_kinds uk
				 LEFT JOIN system_kinds sk ON sk.kind_id = uk.cloned_from_kind_id
				 WHERE uk.user_kind_id = $1 AND uk.owner_user_id = $2`,
				userKindID, userID).Scan(&clonedFromIsPerson); qerr == nil && clonedFromIsPerson {
				writeError(w, http.StatusForbidden, "GLOSS_CANNOT_CLEAR_PERSON",
					"cannot clear is_person on a kind cloned from a system person kind")
				return
			}
		}
		setClauses = append(setClauses, fmt.Sprintf("is_person = $%d", argN))
		args = append(args, v)
		argN++
	}

	if len(setClauses) > 0 {
		setClauses = append(setClauses, "updated_at = now()")
		args = append(args, userKindID, userID)
		updateSQL := fmt.Sprintf(
			"UPDATE user_kinds SET %s WHERE user_kind_id = $%d AND owner_user_id = $%d",
			strings.Join(setClauses, ", "), argN, argN+1)
		if _, err := s.pool.Exec(r.Context(), updateSQL, args...); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
			return
		}
	}

	detail, err := s.loadUserKindDetail(r.Context(), userKindID, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "load failed")
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

func (s *Server) deleteUserKind(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	userKindID, ok := parsePathUUID(w, r, "user_kind_id")
	if !ok {
		return
	}
	if !s.verifyUserKindOwner(w, r.Context(), userKindID, userID) {
		return
	}

	ctx := r.Context()

	// Guard: reject if live entities use this kind. glossary_entities.user_kind_id
	// arrives in SS-7; until then the column is absent — treat 42703 as "0 entities".
	var entityCount int
	if err := s.pool.QueryRow(ctx, `
		SELECT COUNT(*) FROM glossary_entities
		WHERE user_kind_id = $1 AND deleted_at IS NULL AND permanently_deleted_at IS NULL`,
		userKindID,
	).Scan(&entityCount); err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "42703" {
			entityCount = 0
		} else {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count failed")
			return
		}
	}
	if entityCount > 0 {
		writeError(w, http.StatusConflict, "GLOSS_KIND_HAS_ENTITIES",
			fmt.Sprintf("%d entities use this kind; move or delete them first", entityCount))
		return
	}

	tag, err := s.pool.Exec(ctx, `
		UPDATE user_kinds SET deleted_at = now(), updated_at = now()
		WHERE user_kind_id = $1 AND owner_user_id = $2 AND deleted_at IS NULL`,
		userKindID, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "user kind not found or already deleted")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// ── attribute CRUD ───────────────────────────────────────────────────────────

func (s *Server) createUserKindAttr(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	userKindID, ok := parsePathUUID(w, r, "user_kind_id")
	if !ok {
		return
	}
	if !s.verifyUserKindOwner(w, r.Context(), userKindID, userID) {
		return
	}

	var in struct {
		Code        string   `json:"code"`
		Name        string   `json:"name"`
		Description *string  `json:"description"`
		FieldType   string   `json:"field_type"`
		IsRequired  bool     `json:"is_required"`
		SortOrder   int      `json:"sort_order"`
		Options     []string `json:"options"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
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
	if in.FieldType == "" {
		in.FieldType = "text"
	}
	if !validFieldTypes[in.FieldType] {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY",
			"field_type must be text, textarea, select, number, date, tags, url, or boolean")
		return
	}

	var a userKindAttrResp
	err := s.pool.QueryRow(r.Context(), `
		INSERT INTO user_kind_attributes
		  (user_kind_id, code, name, description, field_type, is_required, sort_order, options)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
		RETURNING attr_id, user_kind_id, code, name, description,
		          field_type, is_required, sort_order, options, created_at`,
		userKindID, in.Code, in.Name, in.Description, in.FieldType, in.IsRequired, in.SortOrder, in.Options,
	).Scan(
		&a.AttrID, &a.UserKindID, &a.Code, &a.Name, &a.Description,
		&a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options, &a.CreatedAt,
	)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "GLOSS_DUPLICATE_CODE",
				"an attribute with this code already exists for this kind")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "insert failed")
		return
	}
	if a.Options == nil {
		a.Options = []string{}
	}

	_, _ = s.pool.Exec(r.Context(), `UPDATE user_kinds SET updated_at = now() WHERE user_kind_id = $1`, userKindID)
	writeJSON(w, http.StatusCreated, a)
}

func (s *Server) patchUserKindAttr(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	userKindID, ok := parsePathUUID(w, r, "user_kind_id")
	if !ok {
		return
	}
	attrID, ok := parsePathUUID(w, r, "attr_id")
	if !ok {
		return
	}
	if !s.verifyUserKindOwner(w, r.Context(), userKindID, userID) {
		return
	}

	var in map[string]json.RawMessage
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}

	setClauses := []string{}
	args := []any{}
	argN := 1

	if raw, ok := in["name"]; ok {
		var v string
		if err := json.Unmarshal(raw, &v); err != nil || strings.TrimSpace(v) == "" {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid name")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("name = $%d", argN))
		args = append(args, v)
		argN++
	}
	if raw, ok := in["description"]; ok {
		var v *string
		if err := json.Unmarshal(raw, &v); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid description")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("description = $%d", argN))
		args = append(args, v)
		argN++
	}
	if raw, ok := in["field_type"]; ok {
		var v string
		if err := json.Unmarshal(raw, &v); err != nil || !validFieldTypes[v] {
			writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "invalid field_type")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("field_type = $%d", argN))
		args = append(args, v)
		argN++
	}
	if raw, ok := in["is_required"]; ok {
		var v bool
		if err := json.Unmarshal(raw, &v); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid is_required")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("is_required = $%d", argN))
		args = append(args, v)
		argN++
	}
	if raw, ok := in["sort_order"]; ok {
		var v int
		if err := json.Unmarshal(raw, &v); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid sort_order")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("sort_order = $%d", argN))
		args = append(args, v)
		argN++
	}
	if raw, ok := in["options"]; ok {
		var v []string
		if err := json.Unmarshal(raw, &v); err != nil {
			writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid options")
			return
		}
		setClauses = append(setClauses, fmt.Sprintf("options = $%d", argN))
		args = append(args, v)
		argN++
	}

	if len(setClauses) == 0 {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "no fields to update")
		return
	}

	args = append(args, attrID, userKindID)
	updateSQL := fmt.Sprintf(
		"UPDATE user_kind_attributes SET %s WHERE attr_id = $%d AND user_kind_id = $%d AND deleted_at IS NULL",
		strings.Join(setClauses, ", "), argN, argN+1)

	tag, err := s.pool.Exec(r.Context(), updateSQL, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "update failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "attribute not found")
		return
	}

	_, _ = s.pool.Exec(r.Context(), `UPDATE user_kinds SET updated_at = now() WHERE user_kind_id = $1`, userKindID)

	var a userKindAttrResp
	if err := s.pool.QueryRow(r.Context(), `
		SELECT attr_id, user_kind_id, code, name, description,
		       field_type, is_required, sort_order, options, created_at
		FROM user_kind_attributes WHERE attr_id = $1`, attrID,
	).Scan(
		&a.AttrID, &a.UserKindID, &a.Code, &a.Name, &a.Description,
		&a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options, &a.CreatedAt,
	); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "reload failed")
		return
	}
	if a.Options == nil {
		a.Options = []string{}
	}
	writeJSON(w, http.StatusOK, a)
}

func (s *Server) deleteUserKindAttr(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	userKindID, ok := parsePathUUID(w, r, "user_kind_id")
	if !ok {
		return
	}
	attrID, ok := parsePathUUID(w, r, "attr_id")
	if !ok {
		return
	}
	if !s.verifyUserKindOwner(w, r.Context(), userKindID, userID) {
		return
	}

	force := r.URL.Query().Get("force") == "true"
	ctx := r.Context()

	// Guard: warn if entities hold data for this attr. entity_attribute_values
	// .user_attr_def_id arrives in SS-7; until then treat 42703 as "0".
	var dataCount int
	err := s.pool.QueryRow(ctx, `
		SELECT COUNT(*) FROM entity_attribute_values
		WHERE user_attr_def_id = $1 AND original_value != ''`,
		attrID,
	).Scan(&dataCount)
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "42703" {
			dataCount = 0
		} else {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count failed")
			return
		}
	}
	if dataCount > 0 && !force {
		writeJSON(w, http.StatusConflict, map[string]any{
			"code":         "GLOSS_ATTR_HAS_DATA",
			"message":      fmt.Sprintf("%d entities have data for this attribute", dataCount),
			"entity_count": dataCount,
		})
		return
	}

	tag, err := s.pool.Exec(ctx, `
		UPDATE user_kind_attributes SET deleted_at = now()
		WHERE attr_id = $1 AND user_kind_id = $2 AND deleted_at IS NULL`,
		attrID, userKindID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "attribute not found")
		return
	}

	_, _ = s.pool.Exec(ctx, `UPDATE user_kinds SET updated_at = now() WHERE user_kind_id = $1`, userKindID)
	w.WriteHeader(http.StatusNoContent)
}

// ── recycle bin ──────────────────────────────────────────────────────────────

func (s *Server) listUserKindTrash(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}

	q := r.URL.Query()
	limit := parseIntDefault(q.Get("limit"), 20)
	offset := parseIntDefault(q.Get("offset"), 0)
	if limit > 100 {
		limit = 100
	}
	if limit < 1 {
		limit = 1
	}
	if offset < 0 {
		offset = 0
	}

	ctx := r.Context()
	var total int
	if err := s.pool.QueryRow(ctx, `
		SELECT COUNT(*) FROM user_kinds
		WHERE owner_user_id=$1 AND deleted_at IS NOT NULL AND permanently_deleted_at IS NULL`,
		userID).Scan(&total); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "count failed")
		return
	}

	rows, err := s.pool.Query(ctx, `
		SELECT user_kind_id::text, code, name, icon, color, deleted_at
		FROM user_kinds
		WHERE owner_user_id=$1 AND deleted_at IS NOT NULL AND permanently_deleted_at IS NULL
		ORDER BY deleted_at DESC
		LIMIT $2 OFFSET $3`, userID, limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer rows.Close()

	items := []userKindTrashItem{}
	for rows.Next() {
		var it userKindTrashItem
		if err := rows.Scan(&it.UserKindID, &it.Code, &it.Name, &it.Icon, &it.Color, &it.DeletedAt); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return
		}
		items = append(items, it)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total, "limit": limit, "offset": offset})
}

func (s *Server) restoreUserKind(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	userKindID, ok := parsePathUUID(w, r, "user_kind_id")
	if !ok {
		return
	}

	tag, err := s.pool.Exec(r.Context(), `
		UPDATE user_kinds SET deleted_at = NULL, updated_at = now()
		WHERE user_kind_id = $1 AND owner_user_id = $2
		  AND deleted_at IS NOT NULL AND permanently_deleted_at IS NULL`,
		userKindID, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "restore failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "user kind not in trash")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) purgeUserKind(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	userKindID, ok := parsePathUUID(w, r, "user_kind_id")
	if !ok {
		return
	}

	tag, err := s.pool.Exec(r.Context(), `
		UPDATE user_kinds SET permanently_deleted_at = now()
		WHERE user_kind_id = $1 AND owner_user_id = $2
		  AND deleted_at IS NOT NULL AND permanently_deleted_at IS NULL`,
		userKindID, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "purge failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "user kind not in trash")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
