package api

import (
	"context"
	"net/http"

	"github.com/google/uuid"
)

// resolveEnabled implements the D1 precedence: book override → user override →
// tier default (on). A nil pointer means "no explicit override at that scope".
// Pure + tested directly (REG-P0-04 matrix).
func resolveEnabled(defaultOn bool, userOverride, bookOverride *bool) bool {
	if bookOverride != nil {
		return *bookOverride
	}
	if userOverride != nil {
		return *userOverride
	}
	return defaultOn
}

// loadOverrides fetches the user- and book-scope enablement overrides (if any)
// for one plugin in one resolution context. bookID may be uuid.Nil (no book).
func (s *Server) loadOverrides(ctx context.Context, pluginID, uid, bookID uuid.UUID) (userOverride, bookOverride *bool) {
	rows, err := s.db.Query(ctx,
		`SELECT scope, enabled FROM plugin_enablement
		 WHERE plugin_id = $1
		   AND ((scope = 'user' AND owner_user_id = $2)
		        OR (scope = 'book' AND book_id = $3))`,
		pluginID, uid, nullUUID(bookID))
	if err != nil {
		return nil, nil
	}
	defer rows.Close()
	for rows.Next() {
		var scope string
		var enabled bool
		if err := rows.Scan(&scope, &enabled); err != nil {
			continue
		}
		e := enabled
		switch scope {
		case "user":
			userOverride = &e
		case "book":
			bookOverride = &e
		}
	}
	return userOverride, bookOverride
}

type putEnablementReq struct {
	Scope   string     `json:"scope"` // 'user' | 'book'
	BookID  *uuid.UUID `json:"book_id"`
	Enabled bool       `json:"enabled"`
}

func (s *Server) putEnablement(w http.ResponseWriter, r *http.Request) {
	uid, role, ok := s.requireUser(w, r)
	if !ok {
		return
	}
	pid, ok := parseUUIDParam(w, r, "plugin_id")
	if !ok {
		return
	}
	// The plugin must be visible to the caller (System ∪ own) to toggle it.
	if _, err := s.loadVisiblePlugin(r, uid, pid); err != nil {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "plugin not found")
		return
	}
	var req putEnablementReq
	if !decodeJSON(w, r, &req) {
		return
	}
	switch req.Scope {
	case "user":
		_, err := s.db.Exec(r.Context(),
			`INSERT INTO plugin_enablement (plugin_id, scope, owner_user_id, enabled)
			 VALUES ($1,'user',$2,$3)
			 ON CONFLICT (plugin_id, owner_user_id) WHERE scope = 'user'
			 DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = now()`,
			pid, uid, req.Enabled)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "could not set enablement")
			return
		}
	case "book":
		// DL-2: book-scope override write needs an E0 grant check on book_id.
		// Deferred until the book-grant client is wired; the resolver already
		// honors book overrides so no behavior is lost once writes land.
		writeError(w, http.StatusNotImplemented, "NOT_IMPLEMENTED", "book-scope enablement requires grant wiring (deferred D-REG-BOOK-GRANT)")
		return
	default:
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "scope must be 'user' or 'book'")
		return
	}
	action := "disable"
	if req.Enabled {
		action = "enable"
	}
	s.audit(r.Context(), uid, actorKindOf(role), "enablement", action, &pid, "", "", map[string]any{"scope": req.Scope})
	s.bumpCatalogVersion(r.Context())
	registryWrites.WithLabelValues("enablement", action).Inc()
	writeJSON(w, http.StatusOK, map[string]any{"plugin_id": pid, "scope": req.Scope, "enabled": req.Enabled})
}

func nullUUID(id uuid.UUID) any {
	if id == uuid.Nil {
		return nil
	}
	return id
}
