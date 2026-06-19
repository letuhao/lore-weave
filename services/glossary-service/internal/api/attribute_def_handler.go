package api

// G2 — attribute-DEFINITION tier (genre·kind·attribute re-architecture, 2026-06-19).
// NOT to be confused with attribute_handler.go, which manages per-entity attribute
// VALUES (the EAV layer). This file manages the tiered attribute DEFINITIONS keyed
// by (kind × genre × code): system_attributes (read-only) + user_attributes (CRUD).
//
// System attributes are admin/seed-only → READ-ONLY over HTTP. User attributes are
// owner-scoped CRUD and follow ATTACH-BY-CODE (§2.6): a user attribute attaches to
// the caller's OWN user_kind × user_genre. To extend a System kind×genre, the user
// first clones them into their tier (the clone keeps the same code, so resolution
// still merges by code at adopt) — keeping every FK single-tier (no polymorphism).

import (
	"context"
	"crypto/md5"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"

	"github.com/google/uuid"
)

// attrContentHash mirrors the seed's md5 format
// (md5(code|name|description|field_type|is_required|options)) so the SAME content
// yields the SAME hash across tiers — the basis for G5 Sync's change-detection.
func attrContentHash(code, name string, desc *string, fieldType string, isRequired bool, options []string) string {
	d := ""
	if desc != nil {
		d = *desc
	}
	raw := code + "|" + name + "|" + d + "|" + fieldType + "|" + strconv.FormatBool(isRequired) + "|" + strings.Join(options, ",")
	sum := md5.Sum([]byte(raw))
	return hex.EncodeToString(sum[:])
}

type attributeResp struct {
	AttrID          string   `json:"attr_id"`
	Tier            string   `json:"tier"`
	KindID          string   `json:"kind_id"`
	GenreID         string   `json:"genre_id"`
	Code            string   `json:"code"`
	Name            string   `json:"name"`
	Description     *string  `json:"description,omitempty"`
	FieldType       string   `json:"field_type"`
	IsRequired      bool     `json:"is_required"`
	SortOrder       int      `json:"sort_order"`
	Options         []string `json:"options"`
	AutoFillPrompt  *string  `json:"auto_fill_prompt,omitempty"`
	TranslationHint *string  `json:"translation_hint,omitempty"`
}

// parseKindGenreQuery reads the required kind_id + genre_id query params.
func parseKindGenreQuery(w http.ResponseWriter, r *http.Request) (uuid.UUID, uuid.UUID, bool) {
	kindID, err := uuid.Parse(r.URL.Query().Get("kind_id"))
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "kind_id query param required (uuid)")
		return uuid.Nil, uuid.Nil, false
	}
	genreID, err := uuid.Parse(r.URL.Query().Get("genre_id"))
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "genre_id query param required (uuid)")
		return uuid.Nil, uuid.Nil, false
	}
	return kindID, genreID, true
}

const attrDefCols = `attr_id::text, kind_id::text, genre_id::text, code, name, description,
	field_type, is_required, sort_order, options, auto_fill_prompt, translation_hint`

// scanAttrDefs collects attribute-definition rows in the attrDefCols column order.
// Returns (items, true) on success; on a scan/rows error it writes the 500 and
// returns (nil, false) so the caller stops.
func scanAttrDefs(w http.ResponseWriter, rows interface {
	Next() bool
	Scan(...any) error
	Err() error
}, tier string) ([]attributeResp, bool) {
	items := []attributeResp{}
	for rows.Next() {
		var a attributeResp
		a.Tier = tier
		if err := rows.Scan(&a.AttrID, &a.KindID, &a.GenreID, &a.Code, &a.Name, &a.Description,
			&a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options, &a.AutoFillPrompt, &a.TranslationHint); err != nil {
			writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "scan failed")
			return nil, false
		}
		if a.Options == nil {
			a.Options = []string{}
		}
		items = append(items, a)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "rows error")
		return nil, false
	}
	return items, true
}

// listSystemAttributes reads the System standard's attributes for a (kind, genre).
// Read-only; System is everyone's read-only default (no ownership).
func (s *Server) listSystemAttributes(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	kindID, genreID, ok := parseKindGenreQuery(w, r)
	if !ok {
		return
	}
	rows, err := s.pool.Query(r.Context(),
		`SELECT `+attrDefCols+` FROM system_attributes WHERE kind_id=$1 AND genre_id=$2 ORDER BY sort_order, code`,
		kindID, genreID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer rows.Close()
	items, ok := scanAttrDefs(w, rows, "system")
	if !ok {
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

// listUserAttributes lists the caller's user attributes for a (user-kind, user-genre).
// The owner_user_id filter is the tenancy chokepoint.
func (s *Server) listUserAttributes(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	kindID, genreID, ok := parseKindGenreQuery(w, r)
	if !ok {
		return
	}
	rows, err := s.pool.Query(r.Context(),
		`SELECT `+attrDefCols+` FROM user_attributes
		 WHERE owner_user_id=$1 AND kind_id=$2 AND genre_id=$3 AND deleted_at IS NULL
		 ORDER BY sort_order, code`, userID, kindID, genreID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "query failed")
		return
	}
	defer rows.Close()
	items, ok := scanAttrDefs(w, rows, "user")
	if !ok {
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) createUserAttribute(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	var in struct {
		KindID          string   `json:"kind_id"`
		GenreID         string   `json:"genre_id"`
		Code            string   `json:"code"`
		Name            string   `json:"name"`
		Description     *string  `json:"description"`
		FieldType       string   `json:"field_type"`
		IsRequired      bool     `json:"is_required"`
		SortOrder       int      `json:"sort_order"`
		Options         []string `json:"options"`
		AutoFillPrompt  *string  `json:"auto_fill_prompt"`
		TranslationHint *string  `json:"translation_hint"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid JSON")
		return
	}
	kindID, err := uuid.Parse(in.KindID)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "kind_id is required (uuid)")
		return
	}
	genreID, err := uuid.Parse(in.GenreID)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "genre_id is required (uuid)")
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

	// ATTACH-BY-CODE tenancy gate: kind_id + genre_id MUST be the caller's own live
	// user-tier rows. A non-owned/absent id → 422 (a body-validation failure), not 404.
	if owned, err := s.ownsUserKind(r.Context(), kindID, userID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "ownership check failed")
		return
	} else if !owned {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY",
			"kind_id is not your user-tier kind (clone the system kind into your tier first)")
		return
	}
	if owned, err := s.ownsUserGenre(r.Context(), genreID, userID); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "ownership check failed")
		return
	} else if !owned {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY",
			"genre_id is not your user-tier genre (clone the system genre into your tier first)")
		return
	}

	contentHash := attrContentHash(in.Code, in.Name, in.Description, in.FieldType, in.IsRequired, in.Options)

	var a attributeResp
	a.Tier = "user"
	err = s.pool.QueryRow(r.Context(), `
		INSERT INTO user_attributes
		  (owner_user_id, kind_id, genre_id, code, name, description, field_type,
		   is_required, sort_order, options, auto_fill_prompt, translation_hint, content_hash)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
		RETURNING `+attrDefCols,
		userID, kindID, genreID, in.Code, in.Name, in.Description, in.FieldType,
		in.IsRequired, in.SortOrder, in.Options, in.AutoFillPrompt, in.TranslationHint, contentHash,
	).Scan(&a.AttrID, &a.KindID, &a.GenreID, &a.Code, &a.Name, &a.Description,
		&a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options, &a.AutoFillPrompt, &a.TranslationHint)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "GLOSS_DUPLICATE_CODE",
				"an attribute with this code already exists on this kind×genre")
			return
		}
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "insert failed")
		return
	}
	if a.Options == nil {
		a.Options = []string{}
	}
	writeJSON(w, http.StatusCreated, a)
}

func (s *Server) patchUserAttribute(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	attrID, ok := parsePathUUID(w, r, "attr_id")
	if !ok {
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
	// nullable string fields
	for _, fld := range []struct{ key, col string }{
		{"description", "description"},
		{"auto_fill_prompt", "auto_fill_prompt"},
		{"translation_hint", "translation_hint"},
	} {
		if raw, ok := in[fld.key]; ok {
			var v *string
			if err := json.Unmarshal(raw, &v); err != nil {
				writeError(w, http.StatusBadRequest, "GLOSS_INVALID_BODY", "invalid "+fld.key)
				return
			}
			setClauses = append(setClauses, fmt.Sprintf("%s = $%d", fld.col, argN))
			args = append(args, v)
			argN++
		}
	}
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

	// owner_user_id in the WHERE is the tenancy gate: a non-owned attr → 0 rows → 404.
	args = append(args, attrID, userID)
	updateSQL := fmt.Sprintf(
		"UPDATE user_attributes SET %s WHERE attr_id = $%d AND owner_user_id = $%d AND deleted_at IS NULL",
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

	var a attributeResp
	a.Tier = "user"
	if err := s.pool.QueryRow(r.Context(),
		`SELECT `+attrDefCols+` FROM user_attributes WHERE attr_id = $1`, attrID,
	).Scan(&a.AttrID, &a.KindID, &a.GenreID, &a.Code, &a.Name, &a.Description,
		&a.FieldType, &a.IsRequired, &a.SortOrder, &a.Options, &a.AutoFillPrompt, &a.TranslationHint); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "reload failed")
		return
	}
	if a.Options == nil {
		a.Options = []string{}
	}
	writeJSON(w, http.StatusOK, a)
}

func (s *Server) deleteUserAttribute(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	attrID, ok := parsePathUUID(w, r, "attr_id")
	if !ok {
		return
	}
	tag, err := s.pool.Exec(r.Context(), `
		UPDATE user_attributes SET deleted_at = now()
		WHERE attr_id = $1 AND owner_user_id = $2 AND deleted_at IS NULL`,
		attrID, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "delete failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "attribute not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// ── ownership predicates (no response side-effects; return bool) ───────────────

// ownsUserKind/ownsUserGenre return (owned, error). The error is propagated (NOT
// swallowed) so a transient DB fault surfaces as a 500 rather than masquerading as
// a 422/404 "not yours" (review-impl finding 1). They still fail closed: callers
// treat any non-nil error as "deny + 500", never as "granted".
func (s *Server) ownsUserKind(ctx context.Context, kindID, userID uuid.UUID) (bool, error) {
	var ok bool
	err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM user_kinds WHERE user_kind_id=$1 AND owner_user_id=$2
		               AND deleted_at IS NULL AND permanently_deleted_at IS NULL)`,
		kindID, userID).Scan(&ok)
	return ok, err
}

func (s *Server) ownsUserGenre(ctx context.Context, genreID, userID uuid.UUID) (bool, error) {
	var ok bool
	err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM user_genres WHERE genre_id=$1 AND owner_user_id=$2
		               AND deleted_at IS NULL AND permanently_deleted_at IS NULL)`,
		genreID, userID).Scan(&ok)
	return ok, err
}
