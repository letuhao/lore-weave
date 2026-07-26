package api

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

// ── P4 REG-P4-03: declarative hooks (no code execution) ─────────────────────

// wiredHookActions is the matrix the chat-service hook engine ACTUALLY implements.
// We reject any other (event, action) at create/patch rather than advertise a hook
// that silently no-ops (the /review-impl HIGH-1/MED-2 fix). post_tool_call/post_turn
// + annotate are storage-schema-valid (forward-compat CHECK) but not yet wired, so
// they are refused at the API until the engine handles them.
var wiredHookActions = map[string]map[string]bool{
	"pre_tool_call": {"deny": true, "require_approval": true},
	"pre_turn":      {"inject_text": true},
}

type hookRow struct {
	HookID      uuid.UUID       `json:"hook_id"`
	Tier        string          `json:"tier"`
	OwnerUserID *uuid.UUID      `json:"owner_user_id,omitempty"`
	BookID      *uuid.UUID      `json:"book_id,omitempty"`
	Name        string          `json:"name"`
	Description string          `json:"description"`
	OnEvent     string          `json:"on_event"`
	Match       json.RawMessage `json:"match"`
	Action      json.RawMessage `json:"action"`
	Priority    int             `json:"priority"`
	Enabled     bool            `json:"enabled"`
	CreatedAt   time.Time       `json:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at"`
}

const hookCols = `hook_id, tier, owner_user_id, book_id, name, description, on_event, match, action, priority, enabled, created_at, updated_at`

func scanHook(row interface{ Scan(...any) error }, h *hookRow) error {
	return row.Scan(&h.HookID, &h.Tier, &h.OwnerUserID, &h.BookID, &h.Name, &h.Description,
		&h.OnEvent, &h.Match, &h.Action, &h.Priority, &h.Enabled, &h.CreatedAt, &h.UpdatedAt)
}

// validateHookAction checks the action JSON is a WIRED (event, kind) pair + carries
// the fields that kind needs. Rejects any combination the engine doesn't implement.
func validateHookAction(event string, raw json.RawMessage) (string, bool) {
	allowed, ok := wiredHookActions[event]
	if !ok {
		return "", false
	}
	var a struct {
		Kind string `json:"kind"`
		Text string `json:"text"`
	}
	if err := json.Unmarshal(raw, &a); err != nil || !allowed[a.Kind] {
		return "", false
	}
	// inject_text / annotate carry text; deny / require_approval need none.
	if (a.Kind == "inject_text" || a.Kind == "annotate") && strings.TrimSpace(a.Text) == "" {
		return "", false
	}
	return a.Kind, true
}

type createHookReq struct {
	Name        string          `json:"name"`
	Description string          `json:"description"`
	OnEvent     string          `json:"on_event"`
	Match       json.RawMessage `json:"match"`
	Action      json.RawMessage `json:"action"`
	Priority    int             `json:"priority"`
	Tier        string          `json:"tier"`
	BookID      *uuid.UUID      `json:"book_id"`
}

func (s *Server) createHook(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	var req createHookReq
	if !decodeJSON(w, r, &req) {
		return
	}
	if _, ok := wiredHookActions[req.OnEvent]; !ok {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "on_event must be pre_tool_call or pre_turn (post_tool_call/post_turn not yet supported)")
		return
	}
	if _, ok := validateHookAction(req.OnEvent, req.Action); !ok {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "action.kind must be one the engine supports for this event: pre_tool_call→deny|require_approval, pre_turn→inject_text (inject_text needs text)")
		return
	}
	matchJSON := "{}"
	if len(req.Match) > 0 {
		matchJSON = string(req.Match)
	}
	tier := req.Tier
	if tier == "" {
		tier = "user"
	}
	var ownerArg, bookArg any
	switch tier {
	case "user":
		ownerArg = uid
		if s.queryInt(r.Context(), `SELECT COUNT(*) FROM hooks WHERE tier='user' AND owner_user_id=$1`, uid) >= quotaHooks {
			writeError(w, http.StatusTooManyRequests, "QUOTA_EXCEEDED", "hook limit reached (max 20 per user)")
			return
		}
	case "system":
		// System-tier is platform-owned: RS256 admin token required (D-JWT-ROLE-GATE).
		if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
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
	var row hookRow
	err := scanHook(s.db.QueryRow(r.Context(),
		`INSERT INTO hooks (tier, owner_user_id, book_id, name, description, on_event, match, action, priority)
		 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING `+hookCols,
		tier, ownerArg, bookArg, req.Name, req.Description, req.OnEvent, matchJSON, string(req.Action), req.Priority), &row)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not create hook")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(tier), "hook", "create", &row.HookID, req.OnEvent, tier, nil)
	s.bumpCatalogVersion(r.Context())
	writeJSON(w, http.StatusCreated, row)
}

func (s *Server) listHooks(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	q := r.URL.Query()
	limit := clampLimit(q.Get("limit"))
	offset := atoiDefault(q.Get("offset"), 0)
	if offset < 0 {
		offset = 0
	}
	bookID, okScope := s.resolveListBookScope(w, r, uid)
	if !okScope {
		return
	}
	args := []any{uid}
	tierClause := "(tier = 'system' OR (tier = 'user' AND owner_user_id = $1)"
	if bookID != uuid.Nil {
		args = append(args, bookID)
		tierClause += " OR (tier = 'book' AND book_id = $" + strconv.Itoa(len(args)) + ")"
	}
	tierClause += ")"
	where := []string{tierClause}
	if v := q.Get("on_event"); v != "" {
		args = append(args, v)
		where = append(where, "on_event = $"+strconv.Itoa(len(args)))
	}
	whereSQL := strings.Join(where, " AND ")
	total := s.queryInt(r.Context(), `SELECT COUNT(*) FROM hooks WHERE `+whereSQL, args...)
	args = append(args, limit, offset)
	rows, err := s.db.Query(r.Context(),
		`SELECT `+hookCols+` FROM hooks WHERE `+whereSQL+` ORDER BY on_event, priority DESC LIMIT $`+strconv.Itoa(len(args)-1)+` OFFSET $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not list hooks")
		return
	}
	defer rows.Close()
	items := []hookRow{}
	for rows.Next() {
		var h hookRow
		if err := scanHook(rows, &h); err == nil {
			items = append(items, h)
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total, "limit": limit, "offset": offset})
}

func (s *Server) loadHookForWrite(w http.ResponseWriter, r *http.Request, uid uuid.UUID) (uuid.UUID, string, string, bool) {
	hid, ok := parseUUIDParam(w, r, "hook_id")
	if !ok {
		return uuid.Nil, "", "", false
	}
	var tier, onEvent string
	var owner, book *uuid.UUID
	if err := s.db.QueryRow(r.Context(), `SELECT tier, owner_user_id, book_id, on_event FROM hooks WHERE hook_id=$1`, hid).Scan(&tier, &owner, &book, &onEvent); err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "hook not found")
		return uuid.Nil, "", "", false
	}
	if !s.authorizeRowWrite(w, r, tier, owner, book, uid) {
		if tier != "system" {
			writeError(w, http.StatusNotFound, "NOT_FOUND", "hook not found")
		}
		return uuid.Nil, "", "", false
	}
	return hid, tier, onEvent, true
}

func (s *Server) patchHook(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	hid, tier, onEvent, ok := s.loadHookForWrite(w, r, uid)
	if !ok {
		return
	}
	var req struct {
		Name        *string         `json:"name"`
		Description *string         `json:"description"`
		Match       json.RawMessage `json:"match"`
		Action      json.RawMessage `json:"action"`
		Priority    *int            `json:"priority"`
		Enabled     *bool           `json:"enabled"`
	}
	if !decodeJSON(w, r, &req) {
		return
	}
	sets := []string{"updated_at = now()"}
	args := []any{hid}
	add := func(col string, val any) {
		args = append(args, val)
		sets = append(sets, col+" = $"+strconv.Itoa(len(args)))
	}
	if req.Name != nil {
		add("name", *req.Name)
	}
	if req.Description != nil {
		add("description", *req.Description)
	}
	if len(req.Match) > 0 {
		add("match", string(req.Match))
	}
	if len(req.Action) > 0 {
		// Re-validate against the hook's (immutable) event so a patch can't turn a
		// wired hook into an unwired no-op.
		if _, ok := validateHookAction(onEvent, req.Action); !ok {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "invalid action for this event")
			return
		}
		add("action", string(req.Action))
	}
	if req.Priority != nil {
		add("priority", *req.Priority)
	}
	if req.Enabled != nil {
		add("enabled", *req.Enabled)
	}
	var row hookRow
	if err := scanHook(s.db.QueryRow(r.Context(),
		`UPDATE hooks SET `+strings.Join(sets, ", ")+` WHERE hook_id=$1 RETURNING `+hookCols, args...), &row); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not update hook")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(tier), "hook", "update", &hid, row.OnEvent, tier, nil)
	s.bumpCatalogVersion(r.Context())
	writeJSON(w, http.StatusOK, row)
}

func (s *Server) deleteHook(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	hid, tier, _, ok := s.loadHookForWrite(w, r, uid)
	if !ok {
		return
	}
	if _, err := s.db.Exec(r.Context(), `DELETE FROM hooks WHERE hook_id=$1`, hid); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not delete hook")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(tier), "hook", "delete", &hid, "", tier, nil)
	s.bumpCatalogVersion(r.Context())
	w.WriteHeader(http.StatusNoContent)
}

// internalHooks (X-Internal-Token) — the resolver the chat-service hook engine loads
// per turn: the caller's user + book + System hooks, enabled, ordered by priority.
func (s *Server) internalHooks(w http.ResponseWriter, r *http.Request) {
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
		`SELECT on_event, match, action, priority, tier FROM hooks
		 WHERE enabled = true
		   AND ( tier = 'system'
		      OR (tier = 'user' AND owner_user_id = $1)
		      OR (tier = 'book' AND book_id = $2) )
		 ORDER BY on_event, priority DESC`, uid, nullUUID(bookID))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not resolve hooks")
		return
	}
	defer rows.Close()
	type outHook struct {
		OnEvent  string          `json:"on_event"`
		Match    json.RawMessage `json:"match"`
		Action   json.RawMessage `json:"action"`
		Priority int             `json:"priority"`
		Tier     string          `json:"tier"`
	}
	hooks := []outHook{}
	for rows.Next() {
		var h outHook
		if err := rows.Scan(&h.OnEvent, &h.Match, &h.Action, &h.Priority, &h.Tier); err == nil {
			hooks = append(hooks, h)
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"catalog_version": s.catalogVersion(r.Context()),
		"hooks":           hooks,
	})
}
