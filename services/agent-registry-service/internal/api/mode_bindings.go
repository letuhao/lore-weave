package api

// WS-3 (C6) — MODE → CAPABILITY BINDING.
//
// A mode ("ask"/"write"/"plan") is not just a prompt nudge: it selects a capability
// PROFILE — which skills are injected, which workflows are PINNED into context, which
// tool categories are hot-seeded. This file owns the record's storage, its 3-tier
// tenancy resolution, and the user-facing CRUD.
//
// Why a PIN and not just an advertisement: measured on S06 (docs/eval/discoverability/
// 2026-07-11-S06-flagship-retest.md) a mid-tier model had the right workflow ADVERTISED
// and a steering directive telling it to load one, and still improvised — because the
// user never ASKED for it; they only assented to the agent's own offer ("yeah do it").
// Pinning renders the rail into context from turn 1, so the model never has to recognise
// that a workflow applies.
//
// Tenancy (CLAUDE.md User Boundaries): System is admin-seeded + read-only to users;
// per-user and per-book rows are the user's own. Effective = UNION(system, user, book)
// MINUS the union of every tier's disable_workflows. The subtractive field is what keeps
// this an honest user setting: a pure union would leave a user unable to turn OFF a
// System pin, which is a global flag wearing a setting's clothes.

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/go-chi/chi/v5"
	"github.com/loreweave/grantclient"
)

var validModes = map[string]bool{"ask": true, "write": true, "plan": true}

// validCategories is contract C1 — the frozen closed set of tool categories
// (docs/specs/2026-07-09-agent-discoverability-and-workflow/contracts.md §C1; source of
// truth GROUP_DIRECTORY in ai-gateway find-tools.ts, mirrored in chat-service
// tool_discovery.py). `admin` is deliberately excluded (RS256-segregated catalog, OQ2).
//
// It is enumerated here because a `seed_tool_categories` value is a CLOSED-SET arg and an
// unknown one seeds exactly zero tools — stored, echoed back by GET as the effective
// value, and doing nothing forever. That is the write-only-behavior bug the Settings &
// Config standard names outright; the sibling `inject_workflows` already rejects an
// unpinnable slug at the write, and these two must not be held to a lower bar.
var validCategories = map[string]bool{
	"book": true, "catalog": true, "composition": true, "glossary": true, "jobs": true,
	"knowledge": true, "plan": true, "registry": true, "research": true, "settings": true,
	"story": true, "translation": true,
}

// skillCodeVisible reports whether `code` names a skill this caller could actually have
// injected — System-tier, or one of their own. chat-service filters an unknown code out
// silently, so an unvalidated write would be a setting that never takes effect.
func (s *Server) skillCodeVisible(ctx context.Context, uid uuid.UUID, code string) bool {
	var one int
	err := s.db.QueryRow(ctx,
		`SELECT 1 FROM skills
		  WHERE slug = $1 AND status = 'published'
		    AND (tier = 'system' OR (tier = 'user' AND owner_user_id = $2))
		  LIMIT 1`, code, uid).Scan(&one)
	return err == nil
}

// ModeBinding is the C6 record — the effective (resolved) shape the chat-service reads.
type ModeBinding struct {
	Mode               string   `json:"mode"`
	InjectSkills       []string `json:"inject_skills"`
	InjectWorkflows    []string `json:"inject_workflows"`
	SeedToolCategories []string `json:"seed_tool_categories"`
	DisableWorkflows   []string `json:"disable_workflows"`
	// Sources carries the per-tier contribution so the effective value AND the tier it
	// came from are both visible (Settings & Config: no silent hidden default).
	Sources map[string]*ModeBindingRow `json:"sources,omitempty"`
}

// ModeBindingRow is one tier's stored contribution.
type ModeBindingRow struct {
	Tier               string   `json:"tier"`
	InjectSkills       []string `json:"inject_skills"`
	InjectWorkflows    []string `json:"inject_workflows"`
	SeedToolCategories []string `json:"seed_tool_categories"`
	DisableWorkflows   []string `json:"disable_workflows"`
}

func emptyStrings(v []string) []string {
	if v == nil {
		return []string{}
	}
	return v
}

// unionAppend appends the values of src not already in dst, preserving order.
func unionAppend(dst, src []string) []string {
	seen := make(map[string]bool, len(dst))
	for _, v := range dst {
		seen[v] = true
	}
	for _, v := range src {
		v = strings.TrimSpace(v)
		if v == "" || seen[v] {
			continue
		}
		seen[v] = true
		dst = append(dst, v)
	}
	return dst
}

func without(src, remove []string) []string {
	if len(remove) == 0 {
		return src
	}
	drop := make(map[string]bool, len(remove))
	for _, v := range remove {
		drop[v] = true
	}
	out := make([]string, 0, len(src))
	for _, v := range src {
		if !drop[v] {
			out = append(out, v)
		}
	}
	return out
}

// resolveModeBinding merges System ∪ per-user ∪ per-book for one mode, then subtracts
// every tier's disable_workflows. Returns nil when no tier declares anything for the
// mode (⇒ the caller behaves exactly as it did before this feature existed).
func (s *Server) resolveModeBinding(ctx context.Context, uid, bookID uuid.UUID, mode string) *ModeBinding {
	if s.db == nil || !validModes[mode] {
		return nil
	}
	rows, err := s.db.Query(ctx,
		`SELECT tier, inject_skills, inject_workflows, seed_tool_categories, disable_workflows
		   FROM mode_bindings
		  WHERE mode = $3 AND (
		        tier = 'system'
		     OR (tier = 'user' AND owner_user_id = $1)
		     OR (tier = 'book' AND book_id = $2))
		  ORDER BY CASE tier WHEN 'system' THEN 0 WHEN 'user' THEN 1 ELSE 2 END`,
		uid, nullUUID(bookID), mode)
	if err != nil {
		return nil
	}
	defer rows.Close()

	tiers := []ModeBindingRow{}
	for rows.Next() {
		var r ModeBindingRow
		if err := rows.Scan(&r.Tier, &r.InjectSkills, &r.InjectWorkflows, &r.SeedToolCategories, &r.DisableWorkflows); err != nil {
			continue
		}
		tiers = append(tiers, r)
	}
	return mergeModeBindings(mode, tiers)
}

// mergeModeBindings is the C6 tenancy resolution, kept PURE so it is directly testable
// (the interesting behavior is here, not in the SQL): union the tiers in precedence
// order, then subtract every tier's disable_workflows LAST — that subtraction is what
// lets a user veto a System pin. `tiers` must arrive ordered system → user → book.
// No rows ⇒ nil ⇒ the caller behaves exactly as it did before this feature existed.
func mergeModeBindings(mode string, tiers []ModeBindingRow) *ModeBinding {
	if len(tiers) == 0 {
		return nil
	}
	out := &ModeBinding{Mode: mode, Sources: map[string]*ModeBindingRow{}}
	for _, r := range tiers {
		out.InjectSkills = unionAppend(out.InjectSkills, r.InjectSkills)
		out.InjectWorkflows = unionAppend(out.InjectWorkflows, r.InjectWorkflows)
		out.SeedToolCategories = unionAppend(out.SeedToolCategories, r.SeedToolCategories)
		out.DisableWorkflows = unionAppend(out.DisableWorkflows, r.DisableWorkflows)
		rr := r
		rr.InjectSkills = emptyStrings(rr.InjectSkills)
		rr.InjectWorkflows = emptyStrings(rr.InjectWorkflows)
		rr.SeedToolCategories = emptyStrings(rr.SeedToolCategories)
		rr.DisableWorkflows = emptyStrings(rr.DisableWorkflows)
		out.Sources[r.Tier] = &rr
	}
	out.InjectWorkflows = without(out.InjectWorkflows, out.DisableWorkflows)
	out.InjectSkills = emptyStrings(out.InjectSkills)
	out.InjectWorkflows = emptyStrings(out.InjectWorkflows)
	out.SeedToolCategories = emptyStrings(out.SeedToolCategories)
	out.DisableWorkflows = emptyStrings(out.DisableWorkflows)
	return out
}

// ---------------------------------------------------------------------------
// Public CRUD — the binding is a USER SETTING (a translator does not want the
// co-writer rail), so it must be authorable, not an env flag.
// ---------------------------------------------------------------------------

type modeBindingIn struct {
	InjectSkills       []string `json:"inject_skills"`
	InjectWorkflows    []string `json:"inject_workflows"`
	SeedToolCategories []string `json:"seed_tool_categories"`
	DisableWorkflows   []string `json:"disable_workflows"`
}

// cleanList trims, drops blanks, dedups, and caps the list length.
func cleanList(in []string) ([]string, bool) {
	out := []string{}
	seen := map[string]bool{}
	for _, v := range in {
		v = strings.TrimSpace(v)
		if v == "" || seen[v] {
			continue
		}
		if len(v) > 128 {
			return nil, false
		}
		seen[v] = true
		out = append(out, v)
	}
	if len(out) > 32 {
		return nil, false
	}
	return out, true
}

// workflowVisibleInBook reports whether EVERY grantee of `bookID` will see `slug` on a
// turn scoped to that book. The predicate deliberately mirrors internalWorkflows' own
// book-tier arm (System ∪ that book's rows) — if the two ever disagree, a book-tier pin
// that validates at the write silently no-ops at turn time, which is the failure this
// check exists to prevent.
func (s *Server) workflowVisibleInBook(ctx context.Context, bookID uuid.UUID, slug string) bool {
	var one int
	err := s.db.QueryRow(ctx,
		`SELECT 1 FROM workflows
		  WHERE slug = $1 AND status = 'published'
		    AND (tier = 'system' OR (tier = 'book' AND book_id = $2))
		  LIMIT 1`, slug, bookID).Scan(&one)
	return err == nil
}

// getModeBinding — GET /v1/agent-registry/mode-bindings/{mode}[?book_id=]
// Returns the EFFECTIVE binding plus its per-tier sources (effective value + source tier).
func (s *Server) getModeBinding(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	if s.db == nil {
		writeError(w, http.StatusServiceUnavailable, "NO_DB", "database unavailable")
		return
	}
	mode := chi.URLParam(r, "mode")
	if !validModes[mode] {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "mode must be one of: ask, write, plan")
		return
	}
	bookID := uuid.Nil
	if v := r.URL.Query().Get("book_id"); v != "" {
		b, err := uuid.Parse(v)
		if err != nil {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "book_id must be a uuid")
			return
		}
		if ok, reason := s.bookGrantOK(r.Context(), b, uid, grantclient.GrantView); !ok {
			writeError(w, http.StatusForbidden, "FORBIDDEN", reason)
			return
		}
		bookID = b
	}
	binding := s.resolveModeBinding(r.Context(), uid, bookID, mode)
	if binding == nil {
		binding = &ModeBinding{
			Mode: mode, InjectSkills: []string{}, InjectWorkflows: []string{},
			SeedToolCategories: []string{}, DisableWorkflows: []string{},
		}
	}
	writeJSON(w, http.StatusOK, binding)
}

// putModeBinding — PUT /v1/agent-registry/mode-bindings/{mode}[?book_id=]
// Upserts the CALLER'S OWN tier (user, or book when book_id is given + they hold EDIT).
// The System tier is never writable here (tenancy law: users override into their own
// tier, they never mutate the shared row).
func (s *Server) putModeBinding(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	if s.db == nil {
		writeError(w, http.StatusServiceUnavailable, "NO_DB", "database unavailable")
		return
	}
	mode := chi.URLParam(r, "mode")
	if !validModes[mode] {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "mode must be one of: ask, write, plan")
		return
	}
	var in modeBindingIn
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "invalid JSON body")
		return
	}
	skills, ok1 := cleanList(in.InjectSkills)
	workflows, ok2 := cleanList(in.InjectWorkflows)
	cats, ok3 := cleanList(in.SeedToolCategories)
	disabled, ok4 := cleanList(in.DisableWorkflows)
	if !ok1 || !ok2 || !ok3 || !ok4 {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR",
			"each list holds at most 32 entries of at most 128 chars")
		return
	}

	bookID := uuid.Nil
	if v := r.URL.Query().Get("book_id"); v != "" {
		b, err := uuid.Parse(v)
		if err != nil {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "book_id must be a uuid")
			return
		}
		if ok, reason := s.bookGrantOK(r.Context(), b, uid, grantclient.GrantEdit); !ok {
			writeError(w, http.StatusForbidden, "FORBIDDEN", reason)
			return
		}
		bookID = b
	}

	// A PIN that names a workflow the CONSUMER cannot see is a silent no-op at turn time
	// (Agent Extensibility Standard). Reject it at the write — but validate against the
	// visibility of whoever will CONSUME the binding, which is not always the writer:
	//
	//   - user tier   → the writer is the only consumer  ⇒ System ∪ their own.
	//   - book tier   → EVERY grantee of the book consumes it ⇒ System ∪ that BOOK's rows.
	//
	// Validating a book-tier write against the writer's private set was wrong both ways:
	// it let A pin their own private user-tier workflow into a shared book (invisible to
	// every other grantee, whose turns then ran unpinned while GET still reported the pin
	// as effective), AND it rejected the legitimate case of pinning the book's OWN
	// book-tier workflow, making that whole tier unpinnable.
	// Closed-set validation for the other two lists — same reason, same bar (see
	// validCategories). An unknown value here is not "harmless extra config": it is a
	// setting the GET reports as effective that can never do anything.
	for _, cat := range cats {
		if !validCategories[cat] {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR",
				"'"+cat+"' is not a tool category — it would seed nothing")
			return
		}
	}
	for _, code := range skills {
		if !s.skillCodeVisible(r.Context(), uid, code) {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR",
				"no skill '"+code+"' is visible to you — it cannot be injected")
			return
		}
	}

	for _, slug := range workflows {
		var visible bool
		if bookID != uuid.Nil {
			visible = s.workflowVisibleInBook(r.Context(), bookID, slug)
		} else {
			_, _, _, visible = s.resolveVisibleWorkflowBySlug(r.Context(), uid, slug)
		}
		if !visible {
			scope := "you"
			if bookID != uuid.Nil {
				scope = "this book"
			}
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR",
				"no workflow '"+slug+"' is visible to "+scope+" — it cannot be pinned")
			return
		}
	}

	tier := "user"
	var ownerArg, bookArg any = uid, nil
	if bookID != uuid.Nil {
		tier = "book"
		ownerArg, bookArg = nil, bookID
	}
	conflict := `(owner_user_id, mode) WHERE tier = 'user'`
	if tier == "book" {
		conflict = `(book_id, mode) WHERE tier = 'book'`
	}
	_, err := s.db.Exec(r.Context(),
		`INSERT INTO mode_bindings (tier, owner_user_id, book_id, mode,
		     inject_skills, inject_workflows, seed_tool_categories, disable_workflows)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		 ON CONFLICT `+conflict+` DO UPDATE SET
		     inject_skills = EXCLUDED.inject_skills,
		     inject_workflows = EXCLUDED.inject_workflows,
		     seed_tool_categories = EXCLUDED.seed_tool_categories,
		     disable_workflows = EXCLUDED.disable_workflows,
		     updated_at = now()`,
		tier, ownerArg, bookArg, mode, skills, workflows, cats, disabled)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not save the mode binding")
		return
	}
	binding := s.resolveModeBinding(r.Context(), uid, bookID, mode)
	if binding == nil {
		binding = &ModeBinding{Mode: mode}
	}
	writeJSON(w, http.StatusOK, binding)
}
