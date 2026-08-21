package api

import (
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
)

type bookIntegrityCheck struct {
	Code     string `json:"code"`
	Status   string `json:"status"`
	Severity string `json:"severity"`
	Count    int    `json:"count"`
	Message  string `json:"message"`
}

type bookIntegrityResponse struct {
	BookID    uuid.UUID            `json:"book_id"`
	Status    string               `json:"status"`
	CheckedAt time.Time            `json:"checked_at"`
	Checks    []bookIntegrityCheck `json:"checks"`
}

type integrityQuery struct {
	code     string
	message  string
	query    string
	severity string
}

func (s *Server) checkBookIntegrity(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "GLOSS_UNAUTHORIZED", "valid Bearer token required")
		return
	}
	bookID, ok := parsePathUUID(w, r, "book_id")
	if !ok {
		return
	}
	if !s.requireGrant(w, r.Context(), bookID, userID, grantclient.GrantView) {
		return
	}
	if s.pool == nil {
		writeError(w, http.StatusServiceUnavailable, "GLOSS_NOT_READY", "database unavailable")
		return
	}

	checks := []integrityQuery{
		{code: "active_genres", severity: "error", message: "Active genres must belong to this book.", query: `SELECT COUNT(*) FROM book_active_genres ag LEFT JOIN book_genres g ON g.genre_id = ag.genre_id AND g.book_id = ag.book_id WHERE ag.book_id = $1 AND g.genre_id IS NULL`},
		{code: "kind_genres", severity: "error", message: "Kind-to-genre links must point to genres in this book.", query: `SELECT COUNT(*) FROM book_kind_genres kg JOIN book_kinds k ON k.book_kind_id = kg.kind_id LEFT JOIN book_genres g ON g.genre_id = kg.genre_id AND g.book_id = k.book_id WHERE k.book_id = $1 AND g.genre_id IS NULL`},
		{code: "attributes", severity: "error", message: "Book attributes must point to an existing book kind and genre.", query: `SELECT COUNT(*) FROM book_attributes a LEFT JOIN book_kinds k ON k.book_kind_id = a.kind_id AND k.book_id = a.book_id LEFT JOIN book_genres g ON g.genre_id = a.genre_id AND g.book_id = a.book_id WHERE a.book_id = $1 AND (k.book_kind_id IS NULL OR g.genre_id IS NULL)`},
		{code: "entity_kinds", severity: "error", message: "Entities must point to a kind belonging to this book.", query: `SELECT COUNT(*) FROM glossary_entities e LEFT JOIN book_kinds k ON k.book_kind_id = e.kind_id AND k.book_id = e.book_id WHERE e.book_id = $1 AND e.deleted_at IS NULL AND k.book_kind_id IS NULL`},
		{code: "entity_names", severity: "warning", message: "Active entities should have a name or term attribute.", query: `SELECT COUNT(*) FROM glossary_entities e WHERE e.book_id = $1 AND e.status = 'active' AND e.deleted_at IS NULL AND NOT EXISTS (SELECT 1 FROM entity_attribute_values v JOIN book_attributes a ON a.attr_id = v.attr_def_id WHERE v.entity_id = e.entity_id AND a.book_id = e.book_id AND a.kind_id = e.kind_id AND a.code IN ('name', 'term') AND NULLIF(BTRIM(v.original_value), '') IS NOT NULL)`},
		{code: "entity_attributes", severity: "error", message: "Entity attribute values must use an attribute definition from this book and kind.", query: `SELECT COUNT(*) FROM entity_attribute_values v JOIN glossary_entities e ON e.entity_id = v.entity_id LEFT JOIN book_attributes a ON a.attr_id = v.attr_def_id AND a.book_id = e.book_id AND a.kind_id = e.kind_id WHERE e.book_id = $1 AND e.deleted_at IS NULL AND a.attr_id IS NULL`},
		{code: "chapter_links", severity: "error", message: "Chapter links must point to live entities in this book.", query: `SELECT COUNT(*) FROM chapter_entity_links l JOIN glossary_entities e ON e.entity_id = l.entity_id WHERE e.book_id = $1 AND e.deleted_at IS NOT NULL`},
		{code: "translations", severity: "error", message: "Translations must point to an existing attribute value.", query: `SELECT COUNT(*) FROM attribute_translations t LEFT JOIN entity_attribute_values v ON v.attr_value_id = t.attr_value_id LEFT JOIN glossary_entities e ON e.entity_id = v.entity_id WHERE e.book_id = $1 AND v.attr_value_id IS NULL`},
		{code: "kind_facets", severity: "warning", message: "Entity kind facets must point to kinds in this book.", query: `SELECT COUNT(*) FROM glossary_entities e CROSS JOIN LATERAL unnest(COALESCE(e.kind_labels, '{}'::uuid[])) facet_id LEFT JOIN book_kinds k ON k.book_kind_id = facet_id AND k.book_id = e.book_id WHERE e.book_id = $1 AND e.deleted_at IS NULL AND k.book_kind_id IS NULL`},
	}

	result := bookIntegrityResponse{BookID: bookID, Status: "ok", CheckedAt: time.Now().UTC(), Checks: make([]bookIntegrityCheck, 0, len(checks))}
	for _, check := range checks {
		var count int
		if err := s.pool.QueryRow(r.Context(), check.query, bookID).Scan(&count); err != nil {
			result.Status = "error"
			result.Checks = append(result.Checks, bookIntegrityCheck{Code: check.code, Status: "unavailable", Severity: "error", Message: "Check could not be completed: " + check.message})
			continue
		}
		status := "ok"
		if count > 0 {
			status = "warning"
			if check.severity == "error" {
				result.Status = "error"
				status = "error"
			} else if result.Status == "ok" {
				result.Status = "warning"
			}
		}
		result.Checks = append(result.Checks, bookIntegrityCheck{Code: check.code, Status: status, Severity: check.severity, Count: count, Message: check.message})
	}
	writeJSON(w, http.StatusOK, result)
}
