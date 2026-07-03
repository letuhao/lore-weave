package api

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

// ── P5 REG-P5-01: subagent definitions (CRUD + resolver) ────────────────────
// The scoped-execution runtime (registry_run_subagent) is D-REG-P5-SUBAGENT-RUNTIME.

type subagentRow struct {
	SubagentID  uuid.UUID       `json:"subagent_id"`
	Tier        string          `json:"tier"`
	OwnerUserID *uuid.UUID      `json:"owner_user_id,omitempty"`
	BookID      *uuid.UUID      `json:"book_id,omitempty"`
	Name        string          `json:"name"`
	Description string          `json:"description"`
	SystemPrompt string         `json:"system_prompt"`
	ToolScope   json.RawMessage `json:"tool_scope"`
	ModelRef    string          `json:"model_ref"`
	Enabled     bool            `json:"enabled"`
	CreatedAt   time.Time       `json:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at"`
}

const subagentCols = `subagent_id, tier, owner_user_id, book_id, name, description, system_prompt, tool_scope, model_ref, enabled, created_at, updated_at`

func scanSubagent(row interface{ Scan(...any) error }, s *subagentRow) error {
	return row.Scan(&s.SubagentID, &s.Tier, &s.OwnerUserID, &s.BookID, &s.Name, &s.Description,
		&s.SystemPrompt, &s.ToolScope, &s.ModelRef, &s.Enabled, &s.CreatedAt, &s.UpdatedAt)
}

type createSubagentReq struct {
	Name         string          `json:"name"`
	Description  string          `json:"description"`
	SystemPrompt string          `json:"system_prompt"`
	ToolScope    json.RawMessage `json:"tool_scope"`
	ModelRef     string          `json:"model_ref"`
	Tier         string          `json:"tier"`
	BookID       *uuid.UUID      `json:"book_id"`
}

func (s *Server) createSubagent(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	var req createSubagentReq
	if !decodeJSON(w, r, &req) {
		return
	}
	name := strings.ToLower(strings.TrimSpace(req.Name))
	if !commandNameRE.MatchString(name) {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "name must be lowercase a-z0-9- (1-32 chars)")
		return
	}
	if strings.TrimSpace(req.SystemPrompt) == "" {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "system_prompt is required")
		return
	}
	// tool_scope must be a JSON array of strings (tool-name globs).
	scope := "[]"
	if len(req.ToolScope) > 0 {
		var arr []string
		if err := json.Unmarshal(req.ToolScope, &arr); err != nil {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "tool_scope must be a JSON array of tool-name globs")
			return
		}
		scope = string(req.ToolScope)
	}
	tier := req.Tier
	if tier == "" {
		tier = "user"
	}
	var ownerArg, bookArg any
	switch tier {
	case "user":
		ownerArg = uid
		if s.queryInt(r.Context(), `SELECT COUNT(*) FROM subagent_defs WHERE tier='user' AND owner_user_id=$1`, uid) >= quotaSubagents {
			writeError(w, http.StatusTooManyRequests, "QUOTA_EXCEEDED", "subagent limit reached (max 20 per user)")
			return
		}
	case "system":
		if role != "admin" {
			writeError(w, http.StatusForbidden, "FORBIDDEN", "only admin may create System subagents")
			return
		}
	case "book":
		if req.BookID == nil {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "book_id required for book tier")
			return
		}
		if !s.requireBookGrant(w, r, *req.BookID, uid) {
			return
		}
		bookArg = *req.BookID
	default:
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "invalid tier")
		return
	}
	var row subagentRow
	err := scanSubagent(s.db.QueryRow(r.Context(),
		`INSERT INTO subagent_defs (tier, owner_user_id, book_id, name, description, system_prompt, tool_scope, model_ref)
		 VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING `+subagentCols,
		tier, ownerArg, bookArg, name, req.Description, req.SystemPrompt, scope, req.ModelRef), &row)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "DUPLICATE", "you already have a subagent named '"+name+"'")
			return
		}
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not create subagent")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(role), "subagent", "create", &row.SubagentID, name, tier, nil)
	s.bumpCatalogVersion(r.Context())
	writeJSON(w, http.StatusCreated, row)
}

func (s *Server) listSubagents(w http.ResponseWriter, r *http.Request) {
	uid, _, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	q := r.URL.Query()
	limit := clampLimit(q.Get("limit"))
	offset := atoiDefault(q.Get("offset"), 0)
	if offset < 0 {
		offset = 0
	}
	where := "(tier = 'system' OR (tier = 'user' AND owner_user_id = $1))"
	args := []any{uid, limit, offset}
	total := s.queryInt(r.Context(), `SELECT COUNT(*) FROM subagent_defs WHERE `+where, uid)
	rows, err := s.db.Query(r.Context(),
		`SELECT `+subagentCols+` FROM subagent_defs WHERE `+where+` ORDER BY name LIMIT $2 OFFSET $3`, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not list subagents")
		return
	}
	defer rows.Close()
	items := []subagentRow{}
	for rows.Next() {
		var sa subagentRow
		if err := scanSubagent(rows, &sa); err == nil {
			items = append(items, sa)
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total, "limit": limit, "offset": offset})
}

func (s *Server) loadSubagentForWrite(w http.ResponseWriter, r *http.Request, uid uuid.UUID, role string) (uuid.UUID, string, bool) {
	sid, ok := parseUUIDParam(w, r, "subagent_id")
	if !ok {
		return uuid.Nil, "", false
	}
	var tier string
	var owner, book *uuid.UUID
	if err := s.db.QueryRow(r.Context(), `SELECT tier, owner_user_id, book_id FROM subagent_defs WHERE subagent_id=$1`, sid).Scan(&tier, &owner, &book); err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "subagent not found")
		return uuid.Nil, "", false
	}
	if !s.authorizeRowWrite(r, tier, owner, book, uid, role) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "subagent not found")
		return uuid.Nil, "", false
	}
	return sid, tier, true
}

func (s *Server) patchSubagent(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	sid, tier, ok := s.loadSubagentForWrite(w, r, uid, role)
	if !ok {
		return
	}
	var req struct {
		Description  *string         `json:"description"`
		SystemPrompt *string         `json:"system_prompt"`
		ToolScope    json.RawMessage `json:"tool_scope"`
		ModelRef     *string         `json:"model_ref"`
		Enabled      *bool           `json:"enabled"`
	}
	if !decodeJSON(w, r, &req) {
		return
	}
	sets := []string{"updated_at = now()"}
	args := []any{sid}
	add := func(col string, val any) {
		args = append(args, val)
		sets = append(sets, col+" = $"+strconv.Itoa(len(args)))
	}
	if req.Description != nil {
		add("description", *req.Description)
	}
	if req.SystemPrompt != nil {
		add("system_prompt", *req.SystemPrompt)
	}
	if len(req.ToolScope) > 0 {
		var arr []string
		if err := json.Unmarshal(req.ToolScope, &arr); err != nil {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "tool_scope must be a JSON array")
			return
		}
		add("tool_scope", string(req.ToolScope))
	}
	if req.ModelRef != nil {
		add("model_ref", *req.ModelRef)
	}
	if req.Enabled != nil {
		add("enabled", *req.Enabled)
	}
	var row subagentRow
	if err := scanSubagent(s.db.QueryRow(r.Context(),
		`UPDATE subagent_defs SET `+strings.Join(sets, ", ")+` WHERE subagent_id=$1 RETURNING `+subagentCols, args...), &row); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not update subagent")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(role), "subagent", "update", &sid, row.Name, tier, nil)
	s.bumpCatalogVersion(r.Context())
	writeJSON(w, http.StatusOK, row)
}

func (s *Server) deleteSubagent(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	sid, tier, ok := s.loadSubagentForWrite(w, r, uid, role)
	if !ok {
		return
	}
	if _, err := s.db.Exec(r.Context(), `DELETE FROM subagent_defs WHERE subagent_id=$1`, sid); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not delete subagent")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(role), "subagent", "delete", &sid, "", tier, nil)
	s.bumpCatalogVersion(r.Context())
	w.WriteHeader(http.StatusNoContent)
}

// internalSubagents (X-Internal-Token) — the resolver the future runtime loads a
// subagent def by (user, book, name) from. Returns enabled subagents for the context.
func (s *Server) internalSubagents(w http.ResponseWriter, r *http.Request) {
	if s.db == nil {
		writeError(w, http.StatusServiceUnavailable, "NO_DB", "database unavailable")
		return
	}
	uid, err := uuid.Parse(r.URL.Query().Get("user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "user_id required")
		return
	}
	bookID := uuid.Nil
	if v := r.URL.Query().Get("book_id"); v != "" {
		if b, e := uuid.Parse(v); e == nil {
			bookID = b
		}
	}
	rows, err := s.db.Query(r.Context(),
		`SELECT name, description, system_prompt, tool_scope, model_ref, tier FROM subagent_defs
		 WHERE enabled = true
		   AND ( tier = 'system'
		      OR (tier = 'user' AND owner_user_id = $1)
		      OR (tier = 'book' AND book_id = $2) )
		 ORDER BY (tier = 'book') DESC, (tier = 'user') DESC, name`, uid, nullUUID(bookID))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not resolve subagents")
		return
	}
	defer rows.Close()
	type outSa struct {
		Name         string          `json:"name"`
		Description  string          `json:"description"`
		SystemPrompt string          `json:"system_prompt"`
		ToolScope    json.RawMessage `json:"tool_scope"`
		ModelRef     string          `json:"model_ref"`
		Tier         string          `json:"tier"`
	}
	seen := map[string]bool{}
	subs := []outSa{}
	for rows.Next() {
		var sa outSa
		if err := rows.Scan(&sa.Name, &sa.Description, &sa.SystemPrompt, &sa.ToolScope, &sa.ModelRef, &sa.Tier); err != nil {
			continue
		}
		if seen[sa.Name] {
			continue
		}
		seen[sa.Name] = true
		subs = append(subs, sa)
	}
	writeJSON(w, http.StatusOK, map[string]any{"catalog_version": s.catalogVersion(r.Context()), "subagents": subs})
}
