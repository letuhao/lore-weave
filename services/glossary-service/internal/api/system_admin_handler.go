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

	"github.com/google/uuid"
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

// writeSystemErr maps the shared admin-core sentinels (admin_core.go) to HTTP status
// for the System admin handlers. Both the HTTP path and the MCP admin-confirm path
// run the same cores, so this mapping is the one place HTTP statuses are decided.
func writeSystemErr(w http.ResponseWriter, err error, action string) {
	switch {
	case errors.Is(err, errDuplicateSystemCode):
		writeError(w, http.StatusConflict, "GLOSS_CONFLICT", "a system row with this code already exists")
	case errors.Is(err, errSystemNotFound):
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "system row not found")
	case errors.Is(err, errSystemNotDeletable):
		writeError(w, http.StatusNotFound, "GLOSS_NOT_FOUND", "system row not found or not deletable")
	case errors.Is(err, errSystemFKNotLive):
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", "kind_id or genre_id is not a live system row")
	case errors.Is(err, errSystemNameRequired), errors.Is(err, errSystemCodeUnderivable), errors.Is(err, errInvalidFieldType):
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_INVALID_BODY", err.Error())
	default:
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", action+" failed")
	}
}

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
	g, err := s.createSystemGenreCore(r.Context(), systemGenreParams{Code: in.Code, Name: in.Name, Icon: in.Icon, Color: in.Color, SortOrder: in.SortOrder})
	if err != nil {
		writeSystemErr(w, err, "create system genre")
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
	g, err := s.patchSystemGenreCore(r.Context(), genreID, systemGenrePatch{Name: in.Name, Icon: in.Icon, Color: in.Color, SortOrder: in.SortOrder})
	if err != nil {
		writeSystemErr(w, err, "patch system genre")
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
	if err := s.deleteSystemGenreCore(r.Context(), genreID); err != nil {
		writeSystemErr(w, err, "delete system genre")
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
	k, err := s.createSystemKindCore(r.Context(), systemKindParams{Code: in.Code, Name: in.Name, Description: in.Description, Icon: in.Icon, Color: in.Color, IsHidden: in.IsHidden, SortOrder: in.SortOrder})
	if err != nil {
		writeSystemErr(w, err, "create system kind")
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
	k, err := s.patchSystemKindCore(r.Context(), kindID, systemKindPatch{Name: in.Name, Description: in.Description, Icon: in.Icon, Color: in.Color, IsHidden: in.IsHidden, SortOrder: in.SortOrder})
	if err != nil {
		writeSystemErr(w, err, "patch system kind")
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
	if err := s.deleteSystemKindCore(r.Context(), kindID); err != nil {
		writeSystemErr(w, err, "delete system kind")
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
	a, err := s.createSystemAttributeCore(r.Context(), systemAttrParams{
		KindID: kindID, GenreID: genreID, Code: in.Code, Name: in.Name, Description: in.Description,
		FieldType: in.FieldType, IsRequired: in.IsRequired, SortOrder: in.SortOrder, Options: in.Options,
	})
	if err != nil {
		writeSystemErr(w, err, "create system attribute")
		return
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
		Name        *string   `json:"name"`
		Description *string   `json:"description"`
		FieldType   *string   `json:"field_type"`
		IsRequired  *bool     `json:"is_required"`
		SortOrder   *int      `json:"sort_order"`
		Options     *[]string `json:"options"`
	}
	if !decodeJSON(w, r, &in) {
		return
	}
	a, err := s.patchSystemAttributeCore(r.Context(), attrID, systemAttrPatch{
		Name: in.Name, Description: in.Description, FieldType: in.FieldType,
		IsRequired: in.IsRequired, SortOrder: in.SortOrder, Options: in.Options,
	})
	if err != nil {
		writeSystemErr(w, err, "patch system attribute")
		return
	}
	writeJSON(w, http.StatusOK, a)
}

func (s *Server) deleteSystemAttribute(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
		return
	}
	attrID, ok := parsePathUUID(w, r, "attr_id")
	if !ok {
		return
	}
	if err := s.deleteSystemAttributeCore(r.Context(), attrID); err != nil {
		writeSystemErr(w, err, "delete system attribute")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
