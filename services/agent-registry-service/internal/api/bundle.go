package api

import (
	"context"
	"encoding/json"
	"net/http"
	"regexp"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// ── P5 REG-P5-02: plugin bundle export/import ────────────────────────────────
//
// A bundle is a self-contained, portable snapshot of a plugin + its prompt-only
// members (skills, slash commands, hooks). MCP servers are DELIBERATELY excluded —
// they carry a vault secret + connection/scan state that isn't portable (re-register
// + re-auth on the target). Import validates EVERY member with the same validators as
// the live create paths (a tampered/invalid member rejects the whole bundle), inside
// one transaction, linking members to the freshly-created plugin.

var semverRe = regexp.MustCompile(`^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$`)

type bundleManifest struct {
	Name        string `json:"name"`
	Version     string `json:"version"`
	Description string `json:"description"`
}

type bundleSkill struct {
	Slug        string          `json:"slug"`
	Description string          `json:"description"`
	BodyMD      string          `json:"body_md"`
	Surfaces    []string        `json:"surfaces"`
	Frontmatter json.RawMessage `json:"frontmatter,omitempty"`
}
type bundleCommand struct {
	Name        string          `json:"name"`
	Description string          `json:"description"`
	TemplateMD  string          `json:"template_md"`
	ExpandSide  string          `json:"expand_side"`
	ArgSchema   json.RawMessage `json:"arg_schema,omitempty"`
}
type bundleHook struct {
	Name        string          `json:"name"`
	Description string          `json:"description"`
	OnEvent     string          `json:"on_event"`
	Match       json.RawMessage `json:"match,omitempty"`
	Action      json.RawMessage `json:"action"`
	Priority    int             `json:"priority"`
}

type bundle struct {
	Manifest bundleManifest  `json:"manifest"`
	Skills   []bundleSkill   `json:"skills"`
	Commands []bundleCommand `json:"commands"`
	Hooks    []bundleHook    `json:"hooks"`
}

// exportBundle — GET /plugins/{id}/export. Serializes the plugin + its members
// (WHERE plugin_id = id) into a portable bundle. Owner/System visible only.
func (s *Server) exportBundle(w http.ResponseWriter, r *http.Request) {
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
	out := bundle{
		Manifest: bundleManifest{Name: p.Name, Version: p.Version, Description: p.Description},
		Skills:   []bundleSkill{}, Commands: []bundleCommand{}, Hooks: []bundleHook{},
	}
	// skills
	if rows, e := s.db.Query(r.Context(), `SELECT slug, description, body_md, surfaces, frontmatter FROM skills WHERE plugin_id=$1`, pid); e == nil {
		for rows.Next() {
			var b bundleSkill
			if rows.Scan(&b.Slug, &b.Description, &b.BodyMD, &b.Surfaces, &b.Frontmatter) == nil {
				out.Skills = append(out.Skills, b)
			}
		}
		rows.Close()
	}
	if rows, e := s.db.Query(r.Context(), `SELECT name, description, template_md, expand_side, arg_schema FROM slash_commands WHERE plugin_id=$1`, pid); e == nil {
		for rows.Next() {
			var b bundleCommand
			if rows.Scan(&b.Name, &b.Description, &b.TemplateMD, &b.ExpandSide, &b.ArgSchema) == nil {
				out.Commands = append(out.Commands, b)
			}
		}
		rows.Close()
	}
	if rows, e := s.db.Query(r.Context(), `SELECT name, description, on_event, match, action, priority FROM hooks WHERE plugin_id=$1`, pid); e == nil {
		for rows.Next() {
			var b bundleHook
			if rows.Scan(&b.Name, &b.Description, &b.OnEvent, &b.Match, &b.Action, &b.Priority) == nil {
				out.Hooks = append(out.Hooks, b)
			}
		}
		rows.Close()
	}
	w.Header().Set("Content-Disposition", `attachment; filename="`+bundleFileName(p.Name, p.Version)+`"`)
	writeJSON(w, http.StatusOK, out)
}

func bundleFileName(name, version string) string {
	safe := strings.NewReplacer("/", "-", " ", "-").Replace(name)
	return safe + "-" + version + ".loreweave-bundle.json"
}

// validateBundle checks the manifest + every member against the live validators.
// Returns a user-facing error string (or "") — nothing is written here.
func (s *Server) validateBundle(b *bundle) string {
	if !pluginNameRe.MatchString(strings.TrimSpace(b.Manifest.Name)) {
		return "manifest.name must be reverse-DNS 'namespace/name'"
	}
	if !semverRe.MatchString(b.Manifest.Version) {
		return "manifest.version must be semver (e.g. 1.2.0)"
	}
	if len(b.Skills)+len(b.Commands)+len(b.Hooks) == 0 {
		return "bundle has no members"
	}
	for _, sk := range b.Skills {
		if !skillSlugRe.MatchString(sk.Slug) {
			return "invalid skill slug: " + sk.Slug
		}
	}
	for _, c := range b.Commands {
		name := strings.ToLower(strings.TrimSpace(strings.TrimPrefix(c.Name, "/")))
		if !commandNameRE.MatchString(name) {
			return "invalid command name: " + c.Name
		}
		if reservedCommandNames[name] {
			return "command shadows a built-in: /" + name
		}
		if strings.TrimSpace(c.TemplateMD) == "" {
			return "command '" + name + "' has an empty template"
		}
	}
	for _, h := range b.Hooks {
		if _, ok := validateHookAction(h.OnEvent, h.Action); !ok {
			return "hook has an unsupported (event, action): " + h.OnEvent
		}
	}
	return ""
}

// importBundle — POST /plugins/import. Creates the plugin + every member in one
// transaction (all-or-nothing), each linked to the new plugin_id. User-tier only.
func (s *Server) importBundle(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	var b bundle
	if !decodeJSON(w, r, &b) {
		return
	}
	if msg := s.validateBundle(&b); msg != "" {
		writeError(w, http.StatusBadRequest, "INVALID_BUNDLE", msg)
		return
	}
	// Quota: importing must not push the user past their per-type caps.
	if s.queryInt(r.Context(), `SELECT COUNT(*) FROM skills WHERE tier='user' AND owner_user_id=$1`, uid)+len(b.Skills) > quotaSkills ||
		s.queryInt(r.Context(), `SELECT COUNT(*) FROM slash_commands WHERE tier='user' AND owner_user_id=$1`, uid)+len(b.Commands) > quotaCommands ||
		s.queryInt(r.Context(), `SELECT COUNT(*) FROM hooks WHERE tier='user' AND owner_user_id=$1`, uid)+len(b.Hooks) > quotaHooks {
		writeError(w, http.StatusTooManyRequests, "QUOTA_EXCEEDED", "importing this bundle would exceed your extension quota")
		return
	}

	tx, err := s.db.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not begin import")
		return
	}
	defer tx.Rollback(r.Context())

	var pid uuid.UUID
	err = tx.QueryRow(r.Context(),
		`INSERT INTO plugins (tier, owner_user_id, name, version, description, status)
		 VALUES ('user',$1,$2,$3,$4,'active') RETURNING plugin_id`,
		uid, strings.TrimSpace(b.Manifest.Name), b.Manifest.Version, b.Manifest.Description).Scan(&pid)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "DUPLICATE", "you already have a plugin with this name+version")
			return
		}
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not create plugin")
		return
	}

	if !insertBundleMembers(r.Context(), tx, w, pid, uid, &b) {
		return // insertBundleMembers wrote the error
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not commit import")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(role), "plugin", "import", &pid, b.Manifest.Name, "user",
		map[string]any{"skills": len(b.Skills), "commands": len(b.Commands), "hooks": len(b.Hooks)})
	s.bumpCatalogVersion(r.Context())
	writeJSON(w, http.StatusCreated, map[string]any{
		"plugin_id": pid, "name": b.Manifest.Name, "version": b.Manifest.Version,
		"imported": map[string]int{"skills": len(b.Skills), "commands": len(b.Commands), "hooks": len(b.Hooks)},
	})
}

// insertBundleMembers inserts all members on the open tx; on any DB error it writes a
// 4xx/5xx and returns false (the deferred Rollback then discards the plugin). A DUPLICATE
// (a member the user already owns at user-tier) rejects the whole import — atomic.
func insertBundleMembers(ctx context.Context, tx pgx.Tx, w http.ResponseWriter, pid, uid uuid.UUID, b *bundle) bool {
	for _, sk := range b.Skills {
		fm := sk.Frontmatter
		if len(fm) == 0 {
			fm = json.RawMessage(`{}`)
		}
		if _, err := tx.Exec(ctx,
			`INSERT INTO skills (plugin_id, tier, owner_user_id, slug, description, body_md, surfaces, frontmatter, source, status)
			 VALUES ($1,'user',$2,$3,$4,$5,$6,$7,'import','published')`,
			pid, uid, sk.Slug, sk.Description, sk.BodyMD, sk.Surfaces, string(fm)); err != nil {
			return bundleInsertErr(w, err, "skill", sk.Slug)
		}
	}
	for _, c := range b.Commands {
		name := strings.ToLower(strings.TrimSpace(strings.TrimPrefix(c.Name, "/")))
		expand := c.ExpandSide
		if expand != "server" && expand != "client" {
			expand = "server"
		}
		as := c.ArgSchema
		if len(as) == 0 {
			as = json.RawMessage(`{}`)
		}
		if _, err := tx.Exec(ctx,
			`INSERT INTO slash_commands (plugin_id, tier, owner_user_id, name, description, arg_schema, template_md, expand_side)
			 VALUES ($1,'user',$2,$3,$4,$5,$6,$7)`,
			pid, uid, name, c.Description, string(as), c.TemplateMD, expand); err != nil {
			return bundleInsertErr(w, err, "command", name)
		}
	}
	for _, h := range b.Hooks {
		match := h.Match
		if len(match) == 0 {
			match = json.RawMessage(`{}`)
		}
		if _, err := tx.Exec(ctx,
			`INSERT INTO hooks (plugin_id, tier, owner_user_id, name, description, on_event, match, action, priority)
			 VALUES ($1,'user',$2,$3,$4,$5,$6,$7,$8)`,
			pid, uid, h.Name, h.Description, h.OnEvent, string(match), string(h.Action), h.Priority); err != nil {
			return bundleInsertErr(w, err, "hook", h.OnEvent)
		}
	}
	return true
}

func bundleInsertErr(w http.ResponseWriter, err error, kind, id string) bool {
	if isUniqueViolation(err) {
		writeError(w, http.StatusConflict, "DUPLICATE", "you already have a "+kind+" named '"+id+"' — remove it or rename before importing")
		return false
	}
	writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not import "+kind+" '"+id+"'")
	return false
}
