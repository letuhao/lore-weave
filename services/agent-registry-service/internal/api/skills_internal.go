package api

import (
	"net/http"

	"github.com/google/uuid"
)

// skillEnabled resolves a skill's effective enablement for a user:
// explicit override (skill_enablement) → else published-status default.
func skillEnabled(status string, override *bool) bool {
	if override != nil {
		return *override
	}
	return status == "published"
}

// internalSkills (X-Internal-Token) returns the skills chat-service should inject
// for a (user, book, surface) context: the caller's user + book skills (effective-
// enabled, surface-filtered), plus which System slugs the user disabled and which
// System slugs a user skill shadows. System skill BODIES stay in chat-service
// (DL-4); this endpoint carries user/book bodies + the System override signal.
func (s *Server) internalSkills(w http.ResponseWriter, r *http.Request) {
	if s.db == nil {
		writeError(w, http.StatusServiceUnavailable, "NO_DB", "database unavailable")
		return
	}
	uid, err := uuid.Parse(r.URL.Query().Get("user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "user_id required")
		return
	}
	surface := r.URL.Query().Get("surface")
	bookID := uuid.Nil
	if v := r.URL.Query().Get("book_id"); v != "" {
		if b, err := uuid.Parse(v); err == nil {
			bookID = b
		}
	}

	// The caller's user-tier skills PLUS the book-tier skills for this book context
	// (both effective-enabled + surface-filtered), each with the per-user override.
	// /review-impl: book-tier skills were created but never resolved here — they must
	// inject for turns in their book, else book-tier creation orphans inert rows.
	rows, err := s.db.Query(r.Context(),
		`SELECT sk.slug, sk.description, sk.body_md, sk.surfaces, sk.tier, sk.source, sk.status, se.enabled
		 FROM skills sk
		 LEFT JOIN skill_enablement se ON se.skill_id = sk.skill_id AND se.owner_user_id = $1
		 WHERE (sk.tier = 'user' AND sk.owner_user_id = $1)
		    OR (sk.tier = 'book' AND sk.book_id = $2)`, uid, nullUUID(bookID))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not resolve skills")
		return
	}
	defer rows.Close()

	type outSkill struct {
		Slug        string   `json:"slug"`
		Description string   `json:"description"`
		BodyMD      string   `json:"body_md"`
		L1Line      string   `json:"l1_line"`
		Surfaces    []string `json:"surfaces"`
		Tier        string   `json:"tier"`
		Source      string   `json:"source"`
	}
	skills := []outSkill{}
	userSlugs := []string{}
	for rows.Next() {
		var slug, desc, body, tier, source, status string
		var surfaces []string
		var override *bool
		if err := rows.Scan(&slug, &desc, &body, &surfaces, &tier, &source, &status, &override); err != nil {
			continue
		}
		if !skillEnabled(status, override) {
			continue
		}
		if surface != "" && len(surfaces) > 0 && !contains(surfaces, surface) {
			continue
		}
		skills = append(skills, outSkill{
			Slug: slug, Description: desc, BodyMD: body, L1Line: l1MetadataLine(slug, desc),
			Surfaces: surfaces, Tier: tier, Source: source,
		})
		userSlugs = append(userSlugs, slug)
	}
	rows.Close()

	// System slugs the user disabled (chat-service skips injecting those bodies).
	sysOverrides := map[string]bool{}
	orows, err := s.db.Query(r.Context(),
		`SELECT sk.slug, se.enabled FROM skills sk
		 JOIN skill_enablement se ON se.skill_id = sk.skill_id AND se.owner_user_id = $1
		 WHERE sk.tier = 'system'`, uid)
	if err == nil {
		defer orows.Close()
		for orows.Next() {
			var slug string
			var enabled bool
			if err := orows.Scan(&slug, &enabled); err == nil && !enabled {
				sysOverrides[slug] = false
			}
		}
		orows.Close()
	}

	// shadowed_system = ONLY the user slugs that actually collide with a System
	// skill (so chat-service skips the built-in body of exactly those). A user
	// slug with no System counterpart must NOT appear here.
	shadowList := []string{}
	if len(userSlugs) > 0 {
		srows, err := s.db.Query(r.Context(),
			`SELECT slug FROM skills WHERE tier = 'system' AND slug = ANY($1::text[])`, userSlugs)
		if err == nil {
			defer srows.Close()
			for srows.Next() {
				var slug string
				if err := srows.Scan(&slug); err == nil {
					shadowList = append(shadowList, slug)
				}
			}
			srows.Close()
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"catalog_version":   s.catalogVersion(r.Context()),
		"skills":            skills,
		"system_overrides":  sysOverrides, // slug → false for disabled System skills
		"shadowed_system":   shadowList,   // System slugs a user skill overrides
	})
}

// setSkillEnabled toggles a skill for the caller (per-user override; System row
// never mutated).
func (s *Server) setSkillEnabled(w http.ResponseWriter, r *http.Request) {
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
	var body struct {
		Enabled bool `json:"enabled"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	_, err := s.db.Exec(r.Context(),
		`INSERT INTO skill_enablement (skill_id, owner_user_id, enabled) VALUES ($1,$2,$3)
		 ON CONFLICT (skill_id, owner_user_id) DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = now()`,
		sid, uid, body.Enabled)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not set skill enablement")
		return
	}
	action := "disable"
	if body.Enabled {
		action = "enable"
	}
	s.audit(r.Context(), uid, "user", "skill", action, &sid, "", "", nil)
	s.bumpCatalogVersion(r.Context())
	writeJSON(w, http.StatusOK, map[string]any{"skill_id": sid, "enabled": body.Enabled})
}

func contains(xs []string, v string) bool {
	for _, x := range xs {
		if x == v {
			return true
		}
	}
	return false
}
