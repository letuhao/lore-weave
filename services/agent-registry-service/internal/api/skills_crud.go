package api

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

func (s *Server) listSkills(w http.ResponseWriter, r *http.Request) {
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
	if v := q.Get("tier"); v == "system" || v == "user" || v == "book" {
		args = append(args, v)
		where = append(where, "tier = $"+strconv.Itoa(len(args)))
	}
	if v := q.Get("status"); v != "" {
		args = append(args, v)
		where = append(where, "status = $"+strconv.Itoa(len(args)))
	}
	if v := strings.TrimSpace(q.Get("q")); v != "" {
		args = append(args, v)
		p := strconv.Itoa(len(args))
		where = append(where, "(slug ILIKE '%' || $"+p+" || '%' OR description ILIKE '%' || $"+p+" || '%')")
	}
	orderBy := "updated_at DESC"
	switch q.Get("sort") {
	case "name", "slug":
		orderBy = "slug ASC"
	case "last_triggered":
		orderBy = "last_triggered_at DESC NULLS LAST"
	}
	whereSQL := strings.Join(where, " AND ")
	total := s.queryInt(r.Context(), `SELECT COUNT(*) FROM skills WHERE `+whereSQL, args...)
	args = append(args, limit, offset)
	rows, err := s.db.Query(r.Context(),
		`SELECT `+skillCols+` FROM skills WHERE `+whereSQL+` ORDER BY `+orderBy+
			` LIMIT $`+strconv.Itoa(len(args)-1)+` OFFSET $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not list skills")
		return
	}
	defer rows.Close()
	items := []skillRow{}
	for rows.Next() {
		var sk skillRow
		if err := scanSkill(rows, &sk); err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "scan failed")
			return
		}
		items = append(items, sk)
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total, "limit": limit, "offset": offset})
}

func (s *Server) loadVisibleSkill(r *http.Request, uid, sid uuid.UUID) (*skillRow, error) {
	var sk skillRow
	err := scanSkill(s.db.QueryRow(r.Context(),
		`SELECT `+skillCols+` FROM skills WHERE skill_id = $1 AND (tier = 'system' OR (tier = 'user' AND owner_user_id = $2))`,
		sid, uid), &sk)
	if err != nil {
		return nil, err
	}
	return &sk, nil
}

func (s *Server) getSkill(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	sid, ok := parseUUIDParam(w, r, "skill_id")
	if !ok {
		return
	}
	sk, err := s.loadVisibleSkill(r, uid, sid)
	if err != nil {
		// Fall back to a book-tier skill the caller has grant on (authorizeRowWrite
		// resolves ≥edit + active). loadVisibleSkill only covers System ∪ own.
		var full skillRow
		if e := scanSkill(s.db.QueryRow(r.Context(), `SELECT `+skillCols+` FROM skills WHERE skill_id = $1`, sid), &full); e == nil &&
			full.Tier == "book" && s.authorizeRowWrite(w, r, full.Tier, full.OwnerUserID, full.BookID, uid) {
			writeJSON(w, http.StatusOK, &full)
			return
		}
		writeError(w, http.StatusNotFound, "NOT_FOUND", "skill not found")
		return
	}
	writeJSON(w, http.StatusOK, sk)
}

type patchSkillReq struct {
	Description *string          `json:"description"`
	Surfaces    *[]string        `json:"surfaces"`
	BodyMD      *string          `json:"body_md"`
	Frontmatter *json.RawMessage `json:"frontmatter"`
	Status      *string          `json:"status"`
}

func (s *Server) patchSkill(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	sid, ok := parseUUIDParam(w, r, "skill_id")
	if !ok {
		return
	}
	var tier string
	var owner, book *uuid.UUID
	if err := s.db.QueryRow(r.Context(), `SELECT tier, owner_user_id, book_id FROM skills WHERE skill_id = $1`, sid).Scan(&tier, &owner, &book); err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "skill not found")
		return
	}
	if !s.authorizeRowWrite(w, r, tier, owner, book, uid) {
		if tier != "system" {
			writeError(w, http.StatusNotFound, "NOT_FOUND", "skill not found")
		}
		return
	}
	var req patchSkillReq
	if !decodeJSON(w, r, &req) {
		return
	}
	if req.BodyMD != nil && len(*req.BodyMD) > maxSkillBodyBytes {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "body exceeds 64 KB")
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
	if req.Surfaces != nil {
		set("surfaces", *req.Surfaces)
	}
	if req.BodyMD != nil {
		set("body_md", *req.BodyMD)
	}
	if req.Frontmatter != nil {
		set("frontmatter", string(*req.Frontmatter))
	}
	publishing := false
	if req.Status != nil {
		if *req.Status != "draft" && *req.Status != "published" && *req.Status != "archived" {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "invalid status")
			return
		}
		set("status", *req.Status)
		publishing = *req.Status == "published"
	}
	args = append(args, sid)
	if _, err := s.db.Exec(r.Context(), `UPDATE skills SET `+strings.Join(sets, ", ")+` WHERE skill_id = $`+strconv.Itoa(len(args)), args...); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not update skill")
		return
	}
	// D3: snapshot a revision on publish.
	if publishing {
		_, _ = s.db.Exec(r.Context(),
			`INSERT INTO skill_revisions (skill_id, description, frontmatter, body_md)
			 SELECT skill_id, description, frontmatter, body_md FROM skills WHERE skill_id = $1`, sid)
	}
	s.audit(r.Context(), uid, actorKindOf(tier), "skill", "update", &sid, "", tier, nil)
	s.bumpCatalogVersion(r.Context())
	registryWrites.WithLabelValues("skill", "update").Inc()
	sk, _ := s.loadVisibleSkill(r, uid, sid)
	writeJSON(w, http.StatusOK, sk)
}

func (s *Server) deleteSkill(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	sid, ok := parseUUIDParam(w, r, "skill_id")
	if !ok {
		return
	}
	var tier, slug string
	var owner, book *uuid.UUID
	if err := s.db.QueryRow(r.Context(), `SELECT tier, owner_user_id, slug, book_id FROM skills WHERE skill_id = $1`, sid).Scan(&tier, &owner, &slug, &book); err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "skill not found")
		return
	}
	if !s.authorizeRowWrite(w, r, tier, owner, book, uid) {
		if tier != "system" {
			writeError(w, http.StatusNotFound, "NOT_FOUND", "skill not found")
		}
		return
	}
	if _, err := s.db.Exec(r.Context(), `DELETE FROM skills WHERE skill_id = $1`, sid); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not delete skill")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(tier), "skill", "delete", &sid, slug, tier, nil)
	s.bumpCatalogVersion(r.Context())
	registryWrites.WithLabelValues("skill", "delete").Inc()
	w.WriteHeader(http.StatusNoContent)
}

// shadowCheck reports whether a slug collides with a System skill (the FE shows
// a warning so the user can rename or intentionally override).
func (s *Server) shadowCheck(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireUser(w, r); !ok {
		return
	}
	slug := r.URL.Query().Get("slug")
	n := s.queryInt(r.Context(), `SELECT COUNT(*) FROM skills WHERE tier = 'system' AND slug = $1`, slug)
	writeJSON(w, http.StatusOK, map[string]any{"slug": slug, "shadows_system": n > 0})
}

// importSkill parses a SKILL.md document ({markdown:"..."} — frontmatter+body).
func (s *Server) importSkill(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	var body struct {
		Markdown string `json:"markdown"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	in, msg, ok := parseSkillMarkdown(body.Markdown)
	if !ok {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", msg)
		return
	}
	in.Source = "import"
	s.doCreateSkill(w, r, uid, in, "import")
}

// exportSkill returns the skill as a SKILL.md document.
func (s *Server) exportSkill(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	sid, ok := parseUUIDParam(w, r, "skill_id")
	if !ok {
		return
	}
	sk, err := s.loadVisibleSkill(r, uid, sid)
	if err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "skill not found")
		return
	}
	md := renderSkillMarkdown(sk)
	w.Header().Set("Content-Type", "text/markdown; charset=utf-8")
	w.Header().Set("Content-Disposition", `attachment; filename="`+sk.Slug+`.SKILL.md"`)
	_, _ = w.Write([]byte(md))
}

func (s *Server) listSkillRevisions(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	sid, ok := parseUUIDParam(w, r, "skill_id")
	if !ok {
		return
	}
	if _, err := s.loadVisibleSkill(r, uid, sid); err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "skill not found")
		return
	}
	rows, err := s.db.Query(r.Context(),
		`SELECT revision_id, description, body_md, created_at FROM skill_revisions WHERE skill_id = $1 ORDER BY created_at DESC LIMIT 50`, sid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not list revisions")
		return
	}
	defer rows.Close()
	items := []map[string]any{}
	for rows.Next() {
		var id uuid.UUID
		var desc, body string
		var at time.Time
		if err := rows.Scan(&id, &desc, &body, &at); err != nil {
			continue
		}
		items = append(items, map[string]any{"revision_id": id, "description": desc, "body_md": body, "created_at": at})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}
