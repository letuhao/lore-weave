package api

import (
	"encoding/json"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

// ── P4 REG-P4-01: user-authored slash commands ──────────────────────────────

var commandNameRE = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,31}$`)

// reservedCommandNames are the fixed inline parses in chat-service
// (parse_inline_effort + the manual routes); a user command may not shadow them.
var reservedCommandNames = map[string]bool{
	"think": true, "no_think": true, "no_thinking": true, "effort": true,
	"compact": true, "clear": true, "model": true, "help": true,
}

type commandRow struct {
	CommandID   uuid.UUID       `json:"command_id"`
	Tier        string          `json:"tier"`
	OwnerUserID *uuid.UUID      `json:"owner_user_id,omitempty"`
	BookID      *uuid.UUID      `json:"book_id,omitempty"`
	Name        string          `json:"name"`
	Description string          `json:"description"`
	ArgSchema   json.RawMessage `json:"arg_schema"`
	TemplateMD  string          `json:"template_md"`
	ExpandSide  string          `json:"expand_side"`
	Enabled     bool            `json:"enabled"`
	CreatedAt   time.Time       `json:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at"`
}

const commandCols = `command_id, tier, owner_user_id, book_id, name, description, arg_schema, template_md, expand_side, enabled, created_at, updated_at`

func scanCommand(row interface{ Scan(...any) error }, c *commandRow) error {
	return row.Scan(&c.CommandID, &c.Tier, &c.OwnerUserID, &c.BookID, &c.Name, &c.Description,
		&c.ArgSchema, &c.TemplateMD, &c.ExpandSide, &c.Enabled, &c.CreatedAt, &c.UpdatedAt)
}

type createCommandReq struct {
	Name        string          `json:"name"`
	Description string          `json:"description"`
	ArgSchema   json.RawMessage `json:"arg_schema"`
	TemplateMD  string          `json:"template_md"`
	ExpandSide  string          `json:"expand_side"`
	Tier        string          `json:"tier"`
	BookID      *uuid.UUID      `json:"book_id"`
}

func (s *Server) createCommand(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	var req createCommandReq
	if !decodeJSON(w, r, &req) {
		return
	}
	name := strings.ToLower(strings.TrimSpace(strings.TrimPrefix(req.Name, "/")))
	if !commandNameRE.MatchString(name) {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "name must be lowercase a-z0-9- (1-32 chars), no leading slash")
		return
	}
	if reservedCommandNames[name] {
		writeError(w, http.StatusConflict, "RESERVED_NAME", "'/"+name+"' is a built-in command and cannot be redefined")
		return
	}
	if strings.TrimSpace(req.TemplateMD) == "" {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "template_md is required")
		return
	}
	expand := req.ExpandSide
	if expand == "" {
		expand = "server"
	}
	if expand != "server" && expand != "client" {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "expand_side must be server or client")
		return
	}
	argSchema := "{}"
	if len(req.ArgSchema) > 0 {
		argSchema = string(req.ArgSchema)
	}
	tier := req.Tier
	if tier == "" {
		tier = "user"
	}
	var ownerArg, bookArg any
	switch tier {
	case "user":
		ownerArg = uid
		if s.queryInt(r.Context(), `SELECT COUNT(*) FROM slash_commands WHERE tier='user' AND owner_user_id=$1`, uid) >= quotaCommands {
			writeError(w, http.StatusTooManyRequests, "QUOTA_EXCEEDED", "command limit reached")
			return
		}
	case "system":
		if role != "admin" {
			writeError(w, http.StatusForbidden, "FORBIDDEN", "only admin may create System commands")
			return
		}
	case "book":
		if req.BookID == nil || !s.requireBookGrant(w, r, *req.BookID, uid) {
			if req.BookID == nil {
				writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "book_id required for book tier")
			}
			return
		}
		bookArg = *req.BookID
	default:
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "invalid tier")
		return
	}
	var row commandRow
	err := scanCommand(s.db.QueryRow(r.Context(),
		`INSERT INTO slash_commands (tier, owner_user_id, book_id, name, description, arg_schema, template_md, expand_side)
		 VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING `+commandCols,
		tier, ownerArg, bookArg, name, req.Description, argSchema, req.TemplateMD, expand), &row)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "DUPLICATE", "you already have a command named /"+name)
			return
		}
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not create command")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(role), "command", "create", &row.CommandID, name, tier, nil)
	s.bumpCatalogVersion(r.Context())
	writeJSON(w, http.StatusCreated, row)
}

func (s *Server) listCommands(w http.ResponseWriter, r *http.Request) {
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
	where := []string{"(tier = 'system' OR (tier = 'user' AND owner_user_id = $1))"}
	args := []any{uid}
	if v := strings.TrimSpace(q.Get("q")); v != "" {
		args = append(args, "%"+strings.ToLower(v)+"%")
		where = append(where, "(lower(name) LIKE $"+strconv.Itoa(len(args))+" OR lower(description) LIKE $"+strconv.Itoa(len(args))+")")
	}
	whereSQL := strings.Join(where, " AND ")
	total := s.queryInt(r.Context(), `SELECT COUNT(*) FROM slash_commands WHERE `+whereSQL, args...)
	args = append(args, limit, offset)
	rows, err := s.db.Query(r.Context(),
		`SELECT `+commandCols+` FROM slash_commands WHERE `+whereSQL+` ORDER BY name LIMIT $`+strconv.Itoa(len(args)-1)+` OFFSET $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not list commands")
		return
	}
	defer rows.Close()
	items := []commandRow{}
	for rows.Next() {
		var c commandRow
		if err := scanCommand(rows, &c); err == nil {
			items = append(items, c)
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total, "limit": limit, "offset": offset})
}

func (s *Server) loadCommandForWrite(w http.ResponseWriter, r *http.Request, uid uuid.UUID, role string) (uuid.UUID, string, bool) {
	cid, ok := parseUUIDParam(w, r, "command_id")
	if !ok {
		return uuid.Nil, "", false
	}
	var tier string
	var owner, book *uuid.UUID
	if err := s.db.QueryRow(r.Context(), `SELECT tier, owner_user_id, book_id FROM slash_commands WHERE command_id=$1`, cid).Scan(&tier, &owner, &book); err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "command not found")
		return uuid.Nil, "", false
	}
	if !s.authorizeRowWrite(r, tier, owner, book, uid, role) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "command not found")
		return uuid.Nil, "", false
	}
	return cid, tier, true
}

func (s *Server) patchCommand(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	cid, tier, ok := s.loadCommandForWrite(w, r, uid, role)
	if !ok {
		return
	}
	var req struct {
		Description *string          `json:"description"`
		ArgSchema   json.RawMessage  `json:"arg_schema"`
		TemplateMD  *string          `json:"template_md"`
		ExpandSide  *string          `json:"expand_side"`
		Enabled     *bool            `json:"enabled"`
	}
	if !decodeJSON(w, r, &req) {
		return
	}
	sets := []string{"updated_at = now()"}
	args := []any{cid}
	add := func(col string, val any) {
		args = append(args, val)
		sets = append(sets, col+" = $"+strconv.Itoa(len(args)))
	}
	if req.Description != nil {
		add("description", *req.Description)
	}
	if len(req.ArgSchema) > 0 {
		add("arg_schema", string(req.ArgSchema))
	}
	if req.TemplateMD != nil {
		add("template_md", *req.TemplateMD)
	}
	if req.ExpandSide != nil {
		if *req.ExpandSide != "server" && *req.ExpandSide != "client" {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "expand_side must be server or client")
			return
		}
		add("expand_side", *req.ExpandSide)
	}
	if req.Enabled != nil {
		add("enabled", *req.Enabled)
	}
	var row commandRow
	if err := scanCommand(s.db.QueryRow(r.Context(),
		`UPDATE slash_commands SET `+strings.Join(sets, ", ")+` WHERE command_id=$1 RETURNING `+commandCols, args...), &row); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not update command")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(role), "command", "update", &cid, row.Name, tier, nil)
	s.bumpCatalogVersion(r.Context())
	writeJSON(w, http.StatusOK, row)
}

func (s *Server) deleteCommand(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	cid, tier, ok := s.loadCommandForWrite(w, r, uid, role)
	if !ok {
		return
	}
	if _, err := s.db.Exec(r.Context(), `DELETE FROM slash_commands WHERE command_id=$1`, cid); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not delete command")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(role), "command", "delete", &cid, "", tier, nil)
	s.bumpCatalogVersion(r.Context())
	w.WriteHeader(http.StatusNoContent)
}

// internalCommands (X-Internal-Token) — the resolver chat-service uses to expand a
// /name in a message: the caller's user + book + System commands, effective-enabled.
func (s *Server) internalCommands(w http.ResponseWriter, r *http.Request) {
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
		`SELECT name, description, arg_schema, template_md, expand_side, tier FROM slash_commands
		 WHERE enabled = true
		   AND ( tier = 'system'
		      OR (tier = 'user' AND owner_user_id = $1)
		      OR (tier = 'book' AND book_id = $2) )
		 ORDER BY (tier = 'book') DESC, (tier = 'user') DESC`, uid, nullUUID(bookID))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not resolve commands")
		return
	}
	defer rows.Close()
	type outCmd struct {
		Name        string          `json:"name"`
		Description string          `json:"description"`
		ArgSchema   json.RawMessage `json:"arg_schema"`
		TemplateMD  string          `json:"template_md"`
		ExpandSide  string          `json:"expand_side"`
		Tier        string          `json:"tier"`
	}
	// Higher tier (book > user > system) shadows a lower one by name (resolution order).
	seen := map[string]bool{}
	cmds := []outCmd{}
	for rows.Next() {
		var c outCmd
		if err := rows.Scan(&c.Name, &c.Description, &c.ArgSchema, &c.TemplateMD, &c.ExpandSide, &c.Tier); err != nil {
			continue
		}
		if seen[c.Name] {
			continue
		}
		seen[c.Name] = true
		cmds = append(cmds, c)
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"catalog_version": s.catalogVersion(r.Context()),
		"commands":        cmds,
	})
}
