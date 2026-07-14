package api

import (
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

	rows, err := s.db.Query(r.Context(), `
SELECT slug, title, description, tier, status, surfaces FROM workflows
WHERE status = 'published'
  AND ( tier = 'system'
        OR (tier = 'user' AND owner_user_id = $1)
        OR (tier = 'book' AND book_id = $2) )
ORDER BY tier, slug`, uid, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "failed to list workflows")
		return
	}
	defer rows.Close()

	out := struct {
		Workflows []workflowMeta `json:"workflows"`
	}{Workflows: []workflowMeta{}}
	for rows.Next() {
		var m workflowMeta
		var surfaces []string
		if err := rows.Scan(&m.Slug, &m.Title, &m.Description, &m.Tier, &m.Status, &surfaces); err != nil {
			continue
		}
		if surface != "" && len(surfaces) > 0 && !contains(surfaces, surface) {
			continue
		}
		out.Workflows = append(out.Workflows, m)
	}
	writeJSON(w, http.StatusOK, out)
}
