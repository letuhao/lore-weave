package api

import (
	"context"
	"encoding/json"
	"net/http"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
)

// listUserWorkflows — the JWT-authed, FE-facing list of workflows a user can see (M5 workflow rack).
//
// Until now `workflows` was reachable only via `toolListWorkflows` (MCP, for the agent) and
// `GET /internal/workflows` (X-Internal-Token, for the step-runner). The FE had no way to render the
// recipe rack the user picks from — the gap the Track-C audit flagged for M5. This adds it, with the
// SAME visibility the agent sees (System + the user's own + an optional book-tier set behind a
// ≥view grant), so the rack and the agent never disagree about which recipes exist.
//
// Light projection only (slug/title/description/tier) — the rack lists; the full step defs come from
// the step-runner's own read. Deliberately NOT the 44KB-bloat mistake.
func (s *Server) listUserWorkflows(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	if s.db == nil {
		writeError(w, http.StatusServiceUnavailable, "NO_DB", "database unavailable")
		return
	}

	// Optional book scope: include that book's book-tier workflows too, but only behind a grant
	// (anti-oracle — a non-grantee simply doesn't see them, no existence leak).
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

	surface := r.URL.Query().Get("surface") // optional filter (e.g. "chat")

	// S-12: expose workflow_id (so the FE can get/delete/enable by id) + the EFFECTIVE
	// enabled state (LEFT JOIN the per-user override; else published-default). Separate
	// REST struct — the MCP `workflowMeta` output contract stays untouched.
	rows, err := s.db.Query(r.Context(), `
SELECT wf.workflow_id, wf.slug, wf.title, wf.description, wf.tier, wf.status, wf.surfaces, we.enabled
FROM workflows wf
LEFT JOIN workflow_enablement we ON we.workflow_id = wf.workflow_id AND we.owner_user_id = $1
WHERE wf.status = 'published'
  AND ( wf.tier = 'system'
        OR (wf.tier = 'user' AND wf.owner_user_id = $1)
        OR (wf.tier = 'book' AND wf.book_id = $2) )
ORDER BY wf.tier, wf.slug`, uid, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to list workflows")
		return
	}
	defer rows.Close()

	out := struct {
		Workflows []restWorkflowListItem `json:"workflows"`
	}{Workflows: []restWorkflowListItem{}}
	for rows.Next() {
		var m restWorkflowListItem
		var surfaces []string
		var override *bool
		if err := rows.Scan(&m.WorkflowID, &m.Slug, &m.Title, &m.Description, &m.Tier, &m.Status, &surfaces, &override); err != nil {
			continue
		}
		if surface != "" && len(surfaces) > 0 && !contains(surfaces, surface) {
			continue
		}
		m.Enabled = skillEnabled(m.Status, override) // shared effective-enablement rule
		out.Workflows = append(out.Workflows, m)
	}
	writeJSON(w, http.StatusOK, out)
}

// restWorkflowListItem is the FE-facing list projection — like workflowMeta but with the
// workflow_id (for by-id get/delete/enablement) and the effective per-user `enabled`.
type restWorkflowListItem struct {
	WorkflowID  string `json:"workflow_id"`
	Slug        string `json:"slug"`
	Title       string `json:"title"`
	Description string `json:"description"`
	Tier        string `json:"tier"`
	Status      string `json:"status"`
	Enabled     bool   `json:"enabled"`
}

// restWorkflow is the FE-facing single-workflow shape (the getWorkflowOut fields + the
// id, status, and effective enabled the GUI needs).
type restWorkflow struct {
	WorkflowID  string            `json:"workflow_id"`
	Slug        string            `json:"slug"`
	Title       string            `json:"title"`
	Description string            `json:"description"`
	Tier        string            `json:"tier"`
	Surfaces    []string          `json:"surfaces"`
	Inputs      map[string]string `json:"inputs"`
	Steps       []workflowStepIn  `json:"steps"`
	NotesMD     string            `json:"notes_md"`
	Status      string            `json:"status"`
	Enabled     bool              `json:"enabled"`
}

// scanRestWorkflowByID loads a single workflow by id + its effective per-user enablement.
// visibleOnly=true restricts to System ∪ the caller's own (the get-one first pass);
// visibleOnly=false loads ANY tier (the book-tier fallback, gated by the caller after).
func (s *Server) scanRestWorkflowByID(ctx context.Context, uid, wfID uuid.UUID, visibleOnly bool) (*restWorkflow, error) {
	where := "wf.workflow_id = $2"
	if visibleOnly {
		where += " AND (wf.tier = 'system' OR (wf.tier = 'user' AND wf.owner_user_id = $1))"
	}
	var wf restWorkflow
	var surfaces []string
	var inputsJSON, stepsJSON []byte
	var override *bool
	err := s.db.QueryRow(ctx, `
SELECT wf.workflow_id, wf.slug, wf.title, wf.description, wf.tier, wf.surfaces, wf.inputs, wf.steps,
       wf.notes_md, wf.status, we.enabled
FROM workflows wf
LEFT JOIN workflow_enablement we ON we.workflow_id = wf.workflow_id AND we.owner_user_id = $1
WHERE `+where, uid, wfID).
		Scan(&wf.WorkflowID, &wf.Slug, &wf.Title, &wf.Description, &wf.Tier, &surfaces, &inputsJSON, &stepsJSON,
			&wf.NotesMD, &wf.Status, &override)
	if err != nil {
		return nil, err
	}
	_ = json.Unmarshal(inputsJSON, &wf.Inputs)
	_ = json.Unmarshal(stepsJSON, &wf.Steps)
	if wf.Inputs == nil {
		wf.Inputs = map[string]string{}
	}
	if wf.Steps == nil {
		wf.Steps = []workflowStepIn{}
	}
	if surfaces == nil {
		surfaces = []string{}
	}
	wf.Surfaces = surfaces
	wf.Enabled = skillEnabled(wf.Status, override)
	return &wf, nil
}

// getWorkflow — GET /v1/workflows/{workflow_id}. Mirrors getSkill: System ∪ own first,
// then a book-tier fallback the caller must hold ≥edit on (authorizeRowWrite).
func (s *Server) getWorkflow(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	if s.db == nil {
		writeError(w, http.StatusServiceUnavailable, "NO_DB", "database unavailable")
		return
	}
	wfID, ok := parseUUIDParam(w, r, "workflow_id")
	if !ok {
		return
	}
	wf, err := s.scanRestWorkflowByID(r.Context(), uid, wfID, true)
	if err != nil {
		// Book-tier fallback: a READ needs only ≥VIEW (mirror listUserWorkflows + the MCP
		// get — NOT authorizeRowWrite's ≥edit, which would 404 a view-grantee who can see
		// the row in the list but not open it). Anti-oracle: no grant ⇒ plain not-found.
		full, e := s.scanRestWorkflowByID(r.Context(), uid, wfID, false)
		if e == nil && full.Tier == "book" {
			var book *uuid.UUID
			if qe := s.db.QueryRow(r.Context(), `SELECT book_id FROM workflows WHERE workflow_id = $1`, wfID).Scan(&book); qe == nil && book != nil {
				if okg, _ := s.bookGrantOK(r.Context(), *book, uid, grantclient.GrantView); okg {
					writeJSON(w, http.StatusOK, full)
					return
				}
			}
		}
		writeError(w, http.StatusNotFound, "NOT_FOUND", "workflow not found")
		return
	}
	writeJSON(w, http.StatusOK, wf)
}

// deleteWorkflow — DELETE /v1/workflows/{workflow_id}. Mirrors deleteSkill: owner-scoped;
// System-tier delete needs admin scope (authorizeRowWrite); book-tier needs ≥edit grant.
func (s *Server) deleteWorkflow(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	if s.db == nil {
		writeError(w, http.StatusServiceUnavailable, "NO_DB", "database unavailable")
		return
	}
	wfID, ok := parseUUIDParam(w, r, "workflow_id")
	if !ok {
		return
	}
	var tier, slug string
	var owner, book *uuid.UUID
	if err := s.db.QueryRow(r.Context(), `SELECT tier, owner_user_id, slug, book_id FROM workflows WHERE workflow_id = $1`, wfID).Scan(&tier, &owner, &slug, &book); err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "workflow not found")
		return
	}
	if !s.authorizeRowWrite(w, r, tier, owner, book, uid) {
		// Anti-oracle: a non-System row the caller can't write reads as not-found;
		// a System row (admin-gated) keeps authorizeRowWrite's own 401/403.
		if tier != "system" {
			writeError(w, http.StatusNotFound, "NOT_FOUND", "workflow not found")
		}
		return
	}
	if _, err := s.db.Exec(r.Context(), `DELETE FROM workflows WHERE workflow_id = $1`, wfID); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not delete workflow")
		return
	}
	s.audit(r.Context(), uid, actorKindOf(tier), "workflow", "delete", &wfID, slug, tier, nil)
	s.bumpCatalogVersion(r.Context())
	registryWrites.WithLabelValues("workflow", "delete").Inc()
	w.WriteHeader(http.StatusNoContent)
}

// setWorkflowEnabled — PUT /v1/workflows/{workflow_id}/enablement. Mirrors setSkillEnabled:
// a PER-USER override for ANY visible workflow (incl. System — a tenancy-safe preference,
// see SD-1). Not a shared-row write; the shared-row guard is on delete.
func (s *Server) setWorkflowEnabled(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	if s.db == nil {
		writeError(w, http.StatusServiceUnavailable, "NO_DB", "database unavailable")
		return
	}
	wfID, ok := parseUUIDParam(w, r, "workflow_id")
	if !ok {
		return
	}
	// Must be visible to the caller (System ∪ own ∪ book-with-view). Reuse the by-id
	// loader for System∪own; a book-tier workflow needs a ≥view grant on its book.
	if _, err := s.scanRestWorkflowByID(r.Context(), uid, wfID, true); err != nil {
		var tier string
		var book *uuid.UUID
		if qe := s.db.QueryRow(r.Context(), `SELECT tier, book_id FROM workflows WHERE workflow_id = $1`, wfID).Scan(&tier, &book); qe != nil ||
			tier != "book" || book == nil {
			writeError(w, http.StatusNotFound, "NOT_FOUND", "workflow not found")
			return
		}
		if okg, _ := s.bookGrantOK(r.Context(), *book, uid, grantclient.GrantView); !okg {
			writeError(w, http.StatusNotFound, "NOT_FOUND", "workflow not found")
			return
		}
	}
	var body struct {
		Enabled bool `json:"enabled"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	if _, err := s.db.Exec(r.Context(),
		`INSERT INTO workflow_enablement (workflow_id, owner_user_id, enabled) VALUES ($1,$2,$3)
		 ON CONFLICT (workflow_id, owner_user_id) DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = now()`,
		wfID, uid, body.Enabled); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not set workflow enablement")
		return
	}
	action := "disable"
	if body.Enabled {
		action = "enable"
	}
	s.audit(r.Context(), uid, "user", "workflow", action, &wfID, "", "", nil)
	s.bumpCatalogVersion(r.Context())
	writeJSON(w, http.StatusOK, map[string]any{"workflow_id": wfID, "enabled": body.Enabled})
}
