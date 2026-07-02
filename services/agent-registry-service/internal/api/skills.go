package api

import (
	"encoding/json"
	"net/http"
	"regexp"
	"strings"
	"time"

	"github.com/google/uuid"
)

var skillSlugRe = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{1,63}$`)

const maxSkillBodyBytes = 64 * 1024 // D2

// scriptsMarkerRe flags an imported SKILL pack that smuggles executable content
// (prompt-only decision — no scripts/ execution). We reject on a scripts/ path
// reference in an import payload.
var scriptsMarkerRe = regexp.MustCompile(`(?m)^\s*scripts/`)

type skillRow struct {
	SkillID     uuid.UUID       `json:"skill_id"`
	PluginID    *uuid.UUID      `json:"plugin_id,omitempty"`
	Tier        string          `json:"tier"`
	OwnerUserID *uuid.UUID      `json:"owner_user_id,omitempty"`
	BookID      *uuid.UUID      `json:"book_id,omitempty"`
	Slug        string          `json:"slug"`
	Description string          `json:"description"`
	Frontmatter json.RawMessage `json:"frontmatter"`
	BodyMD      string          `json:"body_md"`
	Surfaces    []string        `json:"surfaces"`
	BookScoped  bool            `json:"book_scoped"`
	Status      string          `json:"status"`
	Source      string          `json:"source"`
	UsedCount   int64           `json:"used_count"`
	CreatedAt   time.Time       `json:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at"`
}

const skillCols = `skill_id, plugin_id, tier, owner_user_id, book_id, slug, description,
	frontmatter, body_md, surfaces, book_scoped, status, source, used_count, created_at, updated_at`

func scanSkill(row interface{ Scan(...any) error }, s *skillRow) error {
	return row.Scan(&s.SkillID, &s.PluginID, &s.Tier, &s.OwnerUserID, &s.BookID, &s.Slug,
		&s.Description, &s.Frontmatter, &s.BodyMD, &s.Surfaces, &s.BookScoped, &s.Status,
		&s.Source, &s.UsedCount, &s.CreatedAt, &s.UpdatedAt)
}

type skillInput struct {
	Slug        string          `json:"slug"`
	Description string          `json:"description"`
	Surfaces    []string        `json:"surfaces"`
	BodyMD      string          `json:"body_md"`
	Frontmatter json.RawMessage `json:"frontmatter"`
	Tier        string          `json:"tier"`
	BookID      *uuid.UUID      `json:"book_id"`
	Status      string          `json:"status"`
	Source      string          `json:"source"`
}

// validateSkill checks slug/description/size and rejects executable smuggling.
func validateSkill(in *skillInput) (string, bool) {
	if !skillSlugRe.MatchString(in.Slug) {
		return "slug must be lowercase [a-z0-9-], 2-64 chars", false
	}
	if strings.TrimSpace(in.Description) == "" {
		return "description is required", false
	}
	if len(in.BodyMD) > maxSkillBodyBytes {
		return "body exceeds 64 KB (prompt-only skills stay lean)", false
	}
	if scriptsMarkerRe.MatchString(in.BodyMD) {
		return "executable scripts/ content is not allowed (skills are prompt-only)", false
	}
	return "", true
}

func (s *Server) createSkill(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	var in skillInput
	if !decodeJSON(w, r, &in) {
		return
	}
	s.doCreateSkill(w, r, uid, role, &in, "user")
}

// doCreateSkill is shared by createSkill (REST) and the proposal-confirm path.
func (s *Server) doCreateSkill(w http.ResponseWriter, r *http.Request, uid uuid.UUID, role string, in *skillInput, defaultSource string) {
	if msg, ok := validateSkill(in); !ok {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", msg)
		return
	}
	tier := in.Tier
	if tier == "" {
		tier = "user"
	}
	status := in.Status
	if status == "" {
		status = "published"
	}
	source := in.Source
	if source == "" {
		source = defaultSource
	}
	fm := in.Frontmatter
	if len(fm) == 0 {
		fm = json.RawMessage(`{}`)
	}
	surfaces := in.Surfaces
	if surfaces == nil {
		surfaces = []string{}
	}

	var ownerArg, bookArg any
	switch tier {
	case "user":
		ownerArg = uid
	case "system":
		if role != "admin" {
			writeError(w, http.StatusForbidden, "FORBIDDEN", "only admin may create System-tier skills")
			return
		}
	case "book":
		writeError(w, http.StatusNotImplemented, "NOT_IMPLEMENTED", "book-tier skills require grant wiring (deferred D-REG-BOOK-GRANT)")
		return
	default:
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "invalid tier")
		return
	}

	var row skillRow
	err := scanSkill(s.db.QueryRow(r.Context(),
		`INSERT INTO skills (tier, owner_user_id, book_id, slug, description, frontmatter, body_md, surfaces, status, source)
		 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING `+skillCols,
		tier, ownerArg, bookArg, in.Slug, in.Description, string(fm), in.BodyMD, surfaces, status, source,
	), &row)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "DUPLICATE", "a skill with this slug already exists in your scope")
			return
		}
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not create skill")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(role), "skill", "create", &row.SkillID, row.Slug, row.Tier, map[string]any{"source": source})
	s.bumpCatalogVersion(r.Context())
	registryWrites.WithLabelValues("skill", "create").Inc()
	writeJSON(w, http.StatusCreated, row)
}
