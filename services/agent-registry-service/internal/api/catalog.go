package api

import (
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

// D2 quota limits (sealed). Enforced at write time in later phases; surfaced
// here so the FE quota strip renders.
const (
	quotaSkills     = 50
	quotaWorkflows  = 50
	quotaMCPServers = 10
	quotaCommands   = 20
	quotaHooks      = 20
	quotaSubagents  = 20
)

// effectiveCatalog (internal, X-Internal-Token) resolves the plugins enabled for
// a (user, book) context. P0 = System tier only (parity with today's static set);
// P2 layers user/book plugins + their tool/skill entries. The catalog_version is
// the Q-CACHE etag consumers compare per turn.
func (s *Server) effectiveCatalog(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
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
		if b, err := uuid.Parse(v); err == nil {
			bookID = b
		}
	}

	version := s.catalogVersion(r.Context())

	// P0: System-tier plugins, filtered by the caller's enablement overrides.
	rows, err := s.db.Query(r.Context(),
		`SELECT plugin_id, name, tier, status FROM plugins WHERE tier = 'system' AND status = 'active' ORDER BY name`)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not resolve catalog")
		return
	}
	defer rows.Close()
	type catalogPlugin struct {
		PluginID uuid.UUID `json:"plugin_id"`
		Name     string    `json:"name"`
		Tier     string    `json:"tier"`
	}
	type sysRow struct {
		id   uuid.UUID
		name string
		tier string
	}
	var sys []sysRow
	for rows.Next() {
		var p sysRow
		var status string
		if err := rows.Scan(&p.id, &p.name, &p.tier, &status); err != nil {
			continue
		}
		sys = append(sys, p)
	}
	rows.Close()

	plugins := []catalogPlugin{}
	for _, p := range sys {
		userOv, bookOv := s.loadOverrides(r.Context(), p.id, uid, bookID)
		if resolveEnabled(true, userOv, bookOv) {
			plugins = append(plugins, catalogPlugin{PluginID: p.id, Name: p.name, Tier: p.tier})
		}
	}

	etag := `"v` + strconv.FormatInt(version, 10) + `"`
	w.Header().Set("ETag", etag)
	catalogResolveSeconds.Observe(time.Since(start).Seconds())
	writeJSON(w, http.StatusOK, map[string]any{
		"catalog_version": version,
		"user_id":         uid,
		"book_id":         nullUUID(bookID),
		"plugins":         plugins,
	})
}

// getUsage returns the caller's quota counters for the FE strip (D2).
func (s *Server) getUsage(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	plugins := s.queryInt(r.Context(), `SELECT COUNT(*) FROM plugins WHERE tier = 'user' AND owner_user_id = $1`, uid)
	// skills / mcp_servers / commands counts land as their tables arrive (P1/P2/P4);
	// their columns are 0 until then so the strip renders from day one.
	skillPending, wfPending := s.countPendingProposals(r, uid)
	writeJSON(w, http.StatusOK, map[string]any{
		"plugins":     plugins,
		"skills":      map[string]int{"used": s.countIfExists(r, "skills", uid), "limit": quotaSkills},
		"workflows":   map[string]int{"used": s.countIfExists(r, "workflows", uid), "limit": quotaWorkflows},
		"mcp_servers": map[string]int{"used": s.countIfExists(r, "mcp_server_registrations", uid), "limit": quotaMCPServers},
		"commands":    map[string]int{"used": s.countIfExists(r, "slash_commands", uid), "limit": quotaCommands},
		// S-12 badge: split the pending count so the studio status badge can route a click to
		// the right panel (workflow vs skill). proposals_pending stays = the SUM (back-compat:
		// the /extensions strip + existing consumers read it unchanged).
		"skill_proposals_pending":    skillPending,
		"workflow_proposals_pending": wfPending,
		"proposals_pending":          skillPending + wfPending,
	})
}

// countIfExists returns COUNT for an owner in a table, or 0 if the table doesn't
// exist yet (forward-compat so the usage endpoint ships in P0 unchanged).
func (s *Server) countIfExists(r *http.Request, table string, uid uuid.UUID) int {
	if !tableExists(table) {
		return 0
	}
	return s.queryInt(r.Context(), `SELECT COUNT(*) FROM `+table+` WHERE owner_user_id = $1`, uid)
}

// countPendingProposals returns the owner's pending skill-proposal + workflow-proposal
// counts SEPARATELY (the caller sums them for the back-compat proposals_pending). Split so
// the S-12 studio badge can route a click to the panel that actually has pending items.
func (s *Server) countPendingProposals(r *http.Request, uid uuid.UUID) (skill, workflow int) {
	if tableExists("skill_proposals") {
		skill = s.queryInt(r.Context(), `SELECT COUNT(*) FROM skill_proposals WHERE owner_user_id = $1 AND status = 'pending'`, uid)
	}
	if tableExists("workflow_proposals") {
		workflow = s.queryInt(r.Context(), `SELECT COUNT(*) FROM workflow_proposals WHERE owner_user_id = $1 AND status = 'pending'`, uid)
	}
	return skill, workflow
}

// tableExists is a compile-time-known allowlist of tables present per phase.
// Updated as phases add tables; keeps getUsage stable without runtime catalog
// introspection.
func tableExists(name string) bool {
	switch name {
	// P0/P1/P2 tables; later phases flip on their own as migrations land.
	case "plugins", "plugin_enablement", "registry_audit", "registry_meta",
		"skills", "skill_proposals", "workflows", "workflow_proposals",
		"mcp_server_registrations", "mcp_server_enablement":
		return true
	}
	return false
}

// listAudit returns the caller's activity log (REG-X-01 read surface).
func (s *Server) listAudit(w http.ResponseWriter, r *http.Request) {
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
	where := []string{"actor_user_id = $1"}
	args := []any{uid}
	if v := q.Get("kind"); v != "" {
		args = append(args, v)
		where = append(where, "kind = $"+strconv.Itoa(len(args)))
	}
	if v := q.Get("range"); v == "7d" || v == "30d" {
		days := 7
		if v == "30d" {
			days = 30
		}
		where = append(where, "at >= now() - interval '"+strconv.Itoa(days)+" days'")
	}
	whereSQL := strings.Join(where, " AND ")
	total := s.queryInt(r.Context(), `SELECT COUNT(*) FROM registry_audit WHERE `+whereSQL, args...)
	args = append(args, limit, offset)
	rows, err := s.db.Query(r.Context(),
		`SELECT audit_id, at, actor_kind, kind, action, target_id, target_name, tier, detail
		 FROM registry_audit WHERE `+whereSQL+` ORDER BY at DESC LIMIT $`+strconv.Itoa(len(args)-1)+` OFFSET $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not list audit")
		return
	}
	defer rows.Close()
	items := []map[string]any{}
	for rows.Next() {
		var (
			id         uuid.UUID
			at         time.Time
			actorKind  string
			kind       string
			action     string
			targetID   *uuid.UUID
			targetName string
			tier       *string
			detail     []byte
		)
		if err := rows.Scan(&id, &at, &actorKind, &kind, &action, &targetID, &targetName, &tier, &detail); err != nil {
			continue
		}
		items = append(items, map[string]any{
			"audit_id": id, "at": at, "actor_kind": actorKind, "kind": kind,
			"action": action, "target_id": targetID, "target_name": targetName,
			"tier": tier, "detail": rawOrEmpty(detail),
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total, "limit": limit, "offset": offset})
}

func rawOrEmpty(b []byte) any {
	if len(b) == 0 {
		return map[string]any{}
	}
	return jsonRaw(b)
}

type jsonRaw []byte

func (j jsonRaw) MarshalJSON() ([]byte, error) { return j, nil }
