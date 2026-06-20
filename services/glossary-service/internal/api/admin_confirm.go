package api

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/google/uuid"
)

// T4 — System-tier admin confirm/preview, gated by the RS256 admin token (separate
// from the HS256 user /actions/confirm). The MCP admin tools PROPOSE (mint an
// authorityAdmin token); a human admin confirms here. Order mirrors the user path:
// requireAdminScope (RS256) → verify token → authority re-check (token asub == the
// confirming admin's subject) BEFORE consuming → single-use jti claim → re-validate
// against current state → run the shared System core. The user confirm path is
// untouched and still rejects authorityAdmin tokens with 501.

// systemActionParams is the captured intent for a System admin action. One struct
// serves create/patch/delete (the descriptor + Level select the effect). Create uses
// the plain fields; patch uses the Patch* pointers (nil = unchanged); delete uses only
// Level + Code (+ KindCode/GenreCode for attributes). Code-addressed (§6.8) — the
// effect re-resolves codes to ids at confirm time so a propose→confirm drift is caught.
type systemActionParams struct {
	Level     string `json:"level"`
	Code      string `json:"code"`
	KindCode  string `json:"kind_code,omitempty"`
	GenreCode string `json:"genre_code,omitempty"`

	// create fields
	Name        string   `json:"name,omitempty"`
	Description string   `json:"description,omitempty"`
	Icon        string   `json:"icon,omitempty"`
	Color       string   `json:"color,omitempty"`
	SortOrder   int      `json:"sort_order,omitempty"`
	IsHidden    bool     `json:"is_hidden,omitempty"`
	FieldType   string   `json:"field_type,omitempty"`
	IsRequired  bool     `json:"is_required,omitempty"`
	Options     []string `json:"options,omitempty"`

	// patch fields (nil = unchanged)
	PatchName        *string   `json:"patch_name,omitempty"`
	PatchDescription *string   `json:"patch_description,omitempty"`
	PatchIcon        *string   `json:"patch_icon,omitempty"`
	PatchColor       *string   `json:"patch_color,omitempty"`
	PatchSortOrder   *int      `json:"patch_sort_order,omitempty"`
	PatchIsHidden    *bool     `json:"patch_is_hidden,omitempty"`
	PatchFieldType   *string   `json:"patch_field_type,omitempty"`
	PatchIsRequired  *bool     `json:"patch_is_required,omitempty"`
	PatchOptions     *[]string `json:"patch_options,omitempty"`
}

// authorizeAdminAction re-checks admin authority at confirm/preview time: the token
// must be an authorityAdmin token whose captured subject matches the RS256 admin
// confirming now. Writes the error itself; ok=false → stop. (The RS256 scope is
// already verified by requireAdminScope before this runs.)
func authorizeAdminAction(w http.ResponseWriter, claims actionClaims, adminSub string) bool {
	if claims.Authority != authorityAdmin {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "not an admin confirmation")
		return false
	}
	if claims.AdminSub == "" || claims.AdminSub != adminSub {
		writeError(w, http.StatusForbidden, "GLOSS_ADMIN_FORBIDDEN", "confirmation not valid for this admin")
		return false
	}
	return true
}

// confirmAdminAction handles POST /v1/glossary/actions/admin/confirm — RS256-gated,
// single-use, the System-tier write path.
func (s *Server) confirmAdminAction(w http.ResponseWriter, r *http.Request) {
	adminClaims, ok := s.requireAdminScope(w, r, scopeAdminWrite)
	if !ok {
		return
	}
	claims, ok := s.decodeConfirmToken(w, r)
	if !ok {
		return
	}
	if !authorizeAdminAction(w, claims, adminClaims.Subject) {
		return
	}
	// Single-use: claim the jti AFTER authority is verified (a stranger can't burn it).
	claimed, err := s.consumeToken(r.Context(), claims.JTI, claims.Descriptor, time.Unix(claims.Exp, 0))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "confirmation failed")
		return
	}
	if !claimed {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "already confirmed — propose again")
		return
	}

	var p systemActionParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	switch claims.Descriptor {
	case descSystemCreate:
		s.effectSystemCreate(w, r.Context(), p)
	case descSystemPatch:
		s.effectSystemPatch(w, r.Context(), p)
	case descSystemDelete:
		s.effectSystemDelete(w, r.Context(), p)
	default:
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "unknown admin action")
	}
}

// previewAdminAction handles POST /v1/glossary/actions/admin/preview — RS256-gated,
// read-only, NEVER consumes the token.
func (s *Server) previewAdminAction(w http.ResponseWriter, r *http.Request) {
	adminClaims, ok := s.requireAdminScope(w, r, scopeAdminWrite)
	if !ok {
		return
	}
	claims, ok := s.decodeConfirmToken(w, r)
	if !ok {
		return
	}
	if !authorizeAdminAction(w, claims, adminClaims.Subject) {
		return
	}
	var p systemActionParams
	if err := json.Unmarshal(claims.Params, &p); err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "bad proposal payload")
		return
	}
	title := map[string]string{
		descSystemCreate: "Create System " + p.Level,
		descSystemPatch:  "Edit System " + p.Level,
		descSystemDelete: "Delete System " + p.Level,
	}[claims.Descriptor]
	rows := []previewRow{{Label: "level", Value: p.Level}}
	if p.Code != "" {
		rows = append(rows, previewRow{Label: "code", Value: p.Code})
	}
	if p.Name != "" {
		rows = append(rows, previewRow{Label: "name", Value: p.Name})
	}
	writeJSON(w, http.StatusOK, actionPreview{
		Descriptor: claims.Descriptor, Title: title, PreviewRows: rows,
		Destructive: claims.Descriptor == descSystemDelete,
	})
}

// ── effects (each re-validates against CURRENT state) ─────────────────────────

func (s *Server) effectSystemCreate(w http.ResponseWriter, ctx context.Context, p systemActionParams) {
	switch p.Level {
	case adminLevelGenre:
		g, err := s.createSystemGenreCore(ctx, systemGenreParams{Code: p.Code, Name: p.Name, Icon: p.Icon, Color: p.Color, SortOrder: p.SortOrder})
		writeSystemResult(w, http.StatusCreated, g, err, "create system genre")
	case adminLevelKind:
		k, err := s.createSystemKindCore(ctx, systemKindParams{Code: p.Code, Name: p.Name, Description: optStr(p.Description), Icon: p.Icon, Color: p.Color, IsHidden: p.IsHidden, SortOrder: p.SortOrder})
		writeSystemResult(w, http.StatusCreated, k, err, "create system kind")
	case adminLevelAttr:
		kindID, genreID, ok := s.resolveSystemCell(w, ctx, p.KindCode, p.GenreCode)
		if !ok {
			return
		}
		a, err := s.createSystemAttributeCore(ctx, systemAttrParams{KindID: kindID, GenreID: genreID, Code: p.Code, Name: p.Name, Description: optStr(p.Description), FieldType: p.FieldType, IsRequired: p.IsRequired, SortOrder: p.SortOrder, Options: p.Options})
		writeSystemResult(w, http.StatusCreated, a, err, "create system attribute")
	default:
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "unknown level")
	}
}

func (s *Server) effectSystemPatch(w http.ResponseWriter, ctx context.Context, p systemActionParams) {
	id, ok := s.resolveSystemTarget(w, ctx, p)
	if !ok {
		return
	}
	switch p.Level {
	case adminLevelGenre:
		g, err := s.patchSystemGenreCore(ctx, id, systemGenrePatch{Name: p.PatchName, Icon: p.PatchIcon, Color: p.PatchColor, SortOrder: p.PatchSortOrder})
		writeSystemResult(w, http.StatusOK, g, err, "patch system genre")
	case adminLevelKind:
		k, err := s.patchSystemKindCore(ctx, id, systemKindPatch{Name: p.PatchName, Description: p.PatchDescription, Icon: p.PatchIcon, Color: p.PatchColor, IsHidden: p.PatchIsHidden, SortOrder: p.PatchSortOrder})
		writeSystemResult(w, http.StatusOK, k, err, "patch system kind")
	case adminLevelAttr:
		a, err := s.patchSystemAttributeCore(ctx, id, systemAttrPatch{Name: p.PatchName, Description: p.PatchDescription, FieldType: p.PatchFieldType, IsRequired: p.PatchIsRequired, SortOrder: p.PatchSortOrder, Options: p.PatchOptions})
		writeSystemResult(w, http.StatusOK, a, err, "patch system attribute")
	default:
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "unknown level")
	}
}

func (s *Server) effectSystemDelete(w http.ResponseWriter, ctx context.Context, p systemActionParams) {
	id, ok := s.resolveSystemTarget(w, ctx, p)
	if !ok {
		return
	}
	var err error
	switch p.Level {
	case adminLevelGenre:
		err = s.deleteSystemGenreCore(ctx, id)
	case adminLevelKind:
		err = s.deleteSystemKindCore(ctx, id)
	case adminLevelAttr:
		err = s.deleteSystemAttributeCore(ctx, id)
	default:
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "unknown level")
		return
	}
	if err != nil {
		writeSystemErr(w, err, "delete system row")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// resolveSystemTarget re-resolves a patch/delete target by code at confirm time. A
// missing target → 422 (drift since propose — re-proposable), not 500.
func (s *Server) resolveSystemTarget(w http.ResponseWriter, ctx context.Context, p systemActionParams) (uuid.UUID, bool) {
	var id uuid.UUID
	var err error
	switch p.Level {
	case adminLevelGenre:
		id, err = s.resolveSystemGenreID(ctx, p.Code)
	case adminLevelKind:
		id, err = s.resolveSystemKindID(ctx, p.Code)
	case adminLevelAttr:
		id, err = s.resolveSystemAttrID(ctx, p.KindCode, p.GenreCode, p.Code)
	default:
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "unknown level")
		return uuid.Nil, false
	}
	if isNoRows(err) {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "the target no longer exists — propose again")
		return uuid.Nil, false
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to resolve the target")
		return uuid.Nil, false
	}
	return id, true
}

func (s *Server) resolveSystemCell(w http.ResponseWriter, ctx context.Context, kindCode, genreCode string) (uuid.UUID, uuid.UUID, bool) {
	kindID, kerr := s.resolveSystemKindID(ctx, kindCode)
	genreID, gerr := s.resolveSystemGenreID(ctx, genreCode)
	if isNoRows(kerr) || isNoRows(gerr) {
		writeError(w, http.StatusUnprocessableEntity, "GLOSS_ACTION_TOKEN", "the kind×genre cell no longer exists — propose again")
		return uuid.Nil, uuid.Nil, false
	}
	if kerr != nil || gerr != nil {
		writeError(w, http.StatusInternalServerError, "GLOSS_INTERNAL", "failed to resolve the cell")
		return uuid.Nil, uuid.Nil, false
	}
	return kindID, genreID, true
}

// writeSystemResult writes a created/patched row or maps a core error via writeSystemErr.
func writeSystemResult(w http.ResponseWriter, okStatus int, body any, err error, action string) {
	if err != nil {
		writeSystemErr(w, err, action)
		return
	}
	writeJSON(w, okStatus, body)
}
