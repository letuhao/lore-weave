package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgconn"
)

// Reverse-DNS-ish plugin name: `namespace/name` (spec §11).
var pluginNameRe = regexp.MustCompile(`^[a-z0-9][a-z0-9.-]*/[a-z0-9][a-z0-9-]*$`)

type pluginRow struct {
	PluginID    uuid.UUID       `json:"plugin_id"`
	Tier        string          `json:"tier"`
	OwnerUserID *uuid.UUID      `json:"owner_user_id,omitempty"`
	BookID      *uuid.UUID      `json:"book_id,omitempty"`
	Name        string          `json:"name"`
	Version     string          `json:"version"`
	Description string          `json:"description"`
	Manifest    json.RawMessage `json:"manifest"`
	Status      string          `json:"status"`
	CreatedAt   time.Time       `json:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at"`
}

type createPluginReq struct {
	Name        string          `json:"name"`
	Version     string          `json:"version"`
	Description string          `json:"description"`
	Tier        string          `json:"tier"`   // 'user' (default) | 'system' (admin) | 'book'
	BookID      *uuid.UUID      `json:"book_id"` // required when tier='book'
	Manifest    json.RawMessage `json:"manifest"`
	Status      string          `json:"status"`
}

func (s *Server) createPlugin(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	var req createPluginReq
	if !decodeJSON(w, r, &req) {
		return
	}
	req.Name = strings.TrimSpace(req.Name)
	if !pluginNameRe.MatchString(req.Name) {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "name must be reverse-DNS form 'namespace/name' (lowercase)")
		return
	}
	if req.Version == "" {
		req.Version = "0.0.0"
	}
	// /review-impl: version must be semver (D3) — an unconstrained version otherwise
	// flows into the export Content-Disposition filename.
	if !semverRe.MatchString(req.Version) {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "version must be semver (e.g. 1.2.0)")
		return
	}
	tier := req.Tier
	if tier == "" {
		tier = "user"
	}
	status := req.Status
	if status == "" {
		status = "active"
	}
	if status != "active" && status != "draft" {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "status must be 'active' or 'draft' on create")
		return
	}
	manifest := req.Manifest
	if len(manifest) == 0 {
		manifest = json.RawMessage(`{}`)
	}

	var ownerArg, bookArg any
	switch tier {
	case "user":
		ownerArg = uid
	case "system":
		if role != "admin" {
			writeError(w, http.StatusForbidden, "FORBIDDEN", "only admin may create System-tier plugins")
			return
		}
	case "book":
		// D-REG-BOOK-GRANT: book-tier creation requires the caller to hold ≥edit
		// on the book (E0 grant), checked via book-service. Fail-closed.
		if req.BookID == nil {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "book_id required for book tier")
			return
		}
		if !s.requireBookGrant(w, r, *req.BookID, uid) {
			return
		}
		bookArg = *req.BookID
	default:
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "tier must be 'user', 'system', or 'book'")
		return
	}

	var row pluginRow
	err := s.db.QueryRow(r.Context(),
		`INSERT INTO plugins (tier, owner_user_id, book_id, name, version, description, manifest, status)
		 VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
		 RETURNING plugin_id, tier, owner_user_id, book_id, name, version, description, manifest, status, created_at, updated_at`,
		tier, ownerArg, bookArg, req.Name, req.Version, req.Description, string(manifest), status,
	).Scan(&row.PluginID, &row.Tier, &row.OwnerUserID, &row.BookID, &row.Name, &row.Version, &row.Description, &row.Manifest, &row.Status, &row.CreatedAt, &row.UpdatedAt)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "DUPLICATE", "a plugin with this name+version already exists in your scope")
			return
		}
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not create plugin")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(role), "plugin", "create", &row.PluginID, row.Name, row.Tier, nil)
	s.bumpCatalogVersion(r.Context())
	registryWrites.WithLabelValues("plugin", "create").Inc()
	writeJSON(w, http.StatusCreated, row)
}

func (s *Server) listPlugins(w http.ResponseWriter, r *http.Request) {
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

	// Visibility: System (everyone, read-only) ∪ the caller's own user-tier rows.
	// Book-tier visibility lands with grant wiring (DL-2).
	where := []string{"(tier = 'system' OR (tier = 'user' AND owner_user_id = $1))"}
	args := []any{uid}
	eq := func(col string, val any) {
		args = append(args, val)
		where = append(where, col+" = $"+strconv.Itoa(len(args)))
	}
	if v := q.Get("tier"); v == "system" || v == "user" || v == "book" {
		eq("tier", v)
	}
	if v := q.Get("status"); v != "" {
		eq("status", v)
	}
	if v := strings.TrimSpace(q.Get("q")); v != "" {
		args = append(args, v)
		p := strconv.Itoa(len(args))
		where = append(where, "(name ILIKE '%' || $"+p+" || '%' OR description ILIKE '%' || $"+p+" || '%')")
	}

	orderBy := "updated_at DESC"
	switch q.Get("sort") {
	case "name":
		orderBy = "name ASC"
	case "tier":
		orderBy = "tier ASC, name ASC"
	case "status":
		orderBy = "status ASC, updated_at DESC"
	}

	whereSQL := strings.Join(where, " AND ")
	total := s.queryInt(r.Context(), `SELECT COUNT(*) FROM plugins WHERE `+whereSQL, args...)

	args = append(args, limit, offset)
	rows, err := s.db.Query(r.Context(),
		`SELECT plugin_id, tier, owner_user_id, book_id, name, version, description, manifest, status, created_at, updated_at
		 FROM plugins WHERE `+whereSQL+` ORDER BY `+orderBy+` LIMIT $`+strconv.Itoa(len(args)-1)+` OFFSET $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not list plugins")
		return
	}
	defer rows.Close()
	items := []pluginRow{}
	for rows.Next() {
		var p pluginRow
		if err := rows.Scan(&p.PluginID, &p.Tier, &p.OwnerUserID, &p.BookID, &p.Name, &p.Version, &p.Description, &p.Manifest, &p.Status, &p.CreatedAt, &p.UpdatedAt); err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "scan failed")
			return
		}
		items = append(items, p)
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total, "limit": limit, "offset": offset})
}

// loadVisiblePlugin fetches a plugin the caller may see (System ∪ own).
func (s *Server) loadVisiblePlugin(r *http.Request, uid, pid uuid.UUID) (*pluginRow, error) {
	var p pluginRow
	err := s.db.QueryRow(r.Context(),
		`SELECT plugin_id, tier, owner_user_id, book_id, name, version, description, manifest, status, created_at, updated_at
		 FROM plugins WHERE plugin_id = $1 AND (tier = 'system' OR (tier = 'user' AND owner_user_id = $2))`,
		pid, uid,
	).Scan(&p.PluginID, &p.Tier, &p.OwnerUserID, &p.BookID, &p.Name, &p.Version, &p.Description, &p.Manifest, &p.Status, &p.CreatedAt, &p.UpdatedAt)
	if err != nil {
		return nil, err
	}
	return &p, nil
}

func (s *Server) getPlugin(w http.ResponseWriter, r *http.Request) {
	uid, _, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	pid, ok := parseUUIDParam(w, r, "plugin_id")
	if !ok {
		return
	}
	p, err := s.loadVisiblePlugin(r, uid, pid)
	if err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "plugin not found")
		return
	}
	writeJSON(w, http.StatusOK, p)
}

type patchPluginReq struct {
	Description *string          `json:"description"`
	Manifest    *json.RawMessage `json:"manifest"`
	Status      *string          `json:"status"`
	Version     *string          `json:"version"`
}

func (s *Server) patchPlugin(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	pid, ok := parseUUIDParam(w, r, "plugin_id")
	if !ok {
		return
	}
	// Only own user-tier rows are writable by a regular user; System rows need admin.
	var tier string
	var owner, book *uuid.UUID
	if err := s.db.QueryRow(r.Context(), `SELECT tier, owner_user_id, book_id FROM plugins WHERE plugin_id = $1`, pid).Scan(&tier, &owner, &book); err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "plugin not found")
		return
	}
	if !s.authorizeRowWrite(r, tier, owner, book, uid, role) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "plugin not found") // anti-oracle
		return
	}
	var req patchPluginReq
	if !decodeJSON(w, r, &req) {
		return
	}
	sets := []string{"updated_at = now()"}
	args := []any{}
	set := func(col string, val any) {
		args = append(args, val)
		sets = append(sets, col+" = $"+strconv.Itoa(len(args)))
	}
	if req.Description != nil {
		set("description", *req.Description)
	}
	if req.Manifest != nil {
		set("manifest", string(*req.Manifest))
	}
	if req.Version != nil {
		if !semverRe.MatchString(*req.Version) {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "version must be semver")
			return
		}
		set("version", *req.Version)
	}
	if req.Status != nil {
		if *req.Status != "active" && *req.Status != "draft" && *req.Status != "suspended" {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "invalid status")
			return
		}
		set("status", *req.Status)
	}
	args = append(args, pid)
	_, err := s.db.Exec(r.Context(), `UPDATE plugins SET `+strings.Join(sets, ", ")+` WHERE plugin_id = $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not update plugin")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(role), "plugin", "update", &pid, "", tier, nil)
	s.bumpCatalogVersion(r.Context())
	registryWrites.WithLabelValues("plugin", "update").Inc()
	p, _ := s.loadVisiblePlugin(r, uid, pid)
	writeJSON(w, http.StatusOK, p)
}

func (s *Server) deletePlugin(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	pid, ok := parseUUIDParam(w, r, "plugin_id")
	if !ok {
		return
	}
	var tier string
	var owner, book *uuid.UUID
	var name string
	if err := s.db.QueryRow(r.Context(), `SELECT tier, owner_user_id, name, book_id FROM plugins WHERE plugin_id = $1`, pid).Scan(&tier, &owner, &name, &book); err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "plugin not found")
		return
	}
	if !s.authorizeRowWrite(r, tier, owner, book, uid, role) {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "plugin not found")
		return
	}
	if _, err := s.db.Exec(r.Context(), `DELETE FROM plugins WHERE plugin_id = $1`, pid); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not delete plugin")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(role), "plugin", "delete", &pid, name, tier, nil)
	s.bumpCatalogVersion(r.Context())
	registryWrites.WithLabelValues("plugin", "delete").Inc()
	w.WriteHeader(http.StatusNoContent)
}

// cascadePreview returns member counts a delete would remove (for the typed-
// confirm dialog). P0 has no member tables yet → zeros; later phases extend.
func (s *Server) cascadePreview(w http.ResponseWriter, r *http.Request) {
	uid, _, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	pid, ok := parseUUIDParam(w, r, "plugin_id")
	if !ok {
		return
	}
	if _, err := s.loadVisiblePlugin(r, uid, pid); err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "plugin not found")
		return
	}
	// Real member counts (a plugin delete cascades to these via the FK ON DELETE CASCADE).
	writeJSON(w, http.StatusOK, map[string]any{
		"skills":          s.queryInt(r.Context(), `SELECT COUNT(*) FROM skills WHERE plugin_id=$1`, pid),
		"mcp_servers":     s.queryInt(r.Context(), `SELECT COUNT(*) FROM mcp_server_registrations WHERE plugin_id=$1`, pid),
		"commands":        s.queryInt(r.Context(), `SELECT COUNT(*) FROM slash_commands WHERE plugin_id=$1`, pid),
		"hooks":           s.queryInt(r.Context(), `SELECT COUNT(*) FROM hooks WHERE plugin_id=$1`, pid),
		"subagents":       0,
		"pinned_sessions": 0,
	})
}

func (s *Server) canWritePlugin(tier string, owner *uuid.UUID, uid uuid.UUID, role string) bool {
	switch tier {
	case "user":
		return owner != nil && *owner == uid
	case "system":
		return role == "admin"
	default:
		return false
	}
}

func actorKindOf(role string) string {
	if role == "admin" {
		return "admin"
	}
	return "user"
}

// isUniqueViolation checks the Postgres SQLSTATE via the typed error rather than
// a fragile substring match (a driver error-format change must not silently turn
// a 409 DUPLICATE into a 500). 23505 = unique_violation.
func isUniqueViolation(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == "23505"
}
