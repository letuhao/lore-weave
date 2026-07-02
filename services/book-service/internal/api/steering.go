package api

// RAID C1 — per-book steering store (DR-C1,
// docs/specs/2026-07-02-raid-loadbearing-decision-records.md).
//
// Author-written per-book rules ("story bible as steering" — the Cursor-rules /
// Kiro-steering analog). chat-service fetches the enabled entries via the
// internal route below and renders the matching ones into every book-scoped
// chat turn as a `<steering>` system part.
//
// Tenancy (CLAUDE.md checklist): book_id is the scope key on every query.
// Writes (create/update/delete) need the EDIT grant — same tier as editing
// chapters (an edit-collaborator CAN author steering; a VIEW grantee cannot).
// Reads (list) need VIEW — steering renders into any collaborator's chat.
//
// inclusion_mode semantics (rendered by chat-service):
//   always      — included in every book-scoped turn
//   scene_match — included when match_pattern (case-insensitive substring,
//                 regex-special chars literal in v1) matches the active
//                 chapter/scene title
//   manual      — included when "#name" appears in the user message
//   auto        — v1: triggered like manual (#name); model-pull is a follow-up
//
// Caps (DR-C1 — steering is taxed every turn, keep tight): body <= 8000 chars,
// <= 20 rows per book. Over-cap and enum violations are 422; a duplicate name
// within the book is 409 (UNIQUE(book_id, name)).

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

const (
	maxSteeringBodyChars   = 8000
	maxSteeringRowsPerBook = 20
	maxSteeringNameChars   = 200
)

// steeringAutoModeNote is the v1-honesty string surfaced on the API (DR-C1):
// authors must not be misled into thinking `auto` is model-driven yet.
const steeringAutoModeNote = "'auto' v1: triggered like manual (#name); model-pull is a follow-up"

func validSteeringMode(mode string) bool {
	switch mode {
	case "always", "scene_match", "manual", "auto":
		return true
	}
	return false
}

type steeringRow struct {
	ID            uuid.UUID `json:"id"`
	BookID        uuid.UUID `json:"book_id"`
	Name          string    `json:"name"`
	Body          string    `json:"body"`
	InclusionMode string    `json:"inclusion_mode"`
	MatchPattern  *string   `json:"match_pattern"`
	Enabled       bool      `json:"enabled"`
	AuthorUserID  uuid.UUID `json:"author_user_id"`
	CreatedAt     time.Time `json:"created_at"`
	UpdatedAt     time.Time `json:"updated_at"`
}

// steeringInput is the create/update payload. PUT is full-replace: omitted
// inclusion_mode falls back to the 'always' default, omitted enabled to true.
type steeringInput struct {
	Name          string  `json:"name"`
	Body          string  `json:"body"`
	InclusionMode *string `json:"inclusion_mode"`
	MatchPattern  *string `json:"match_pattern"`
	Enabled       *bool   `json:"enabled"`
}

// validateSteeringInput normalizes + validates a payload. Returns the resolved
// (name, body, mode, pattern, enabled) or writes the HTTP error and ok=false.
// Char caps count runes (matches Postgres char_length, not bytes) so CJK
// steering bodies aren't unfairly truncated at a third of the budget.
func validateSteeringInput(w http.ResponseWriter, in steeringInput) (name, body, mode string, pattern *string, enabled bool, ok bool) {
	name = strings.TrimSpace(in.Name)
	if name == "" {
		writeError(w, http.StatusUnprocessableEntity, "STEERING_VALIDATION_ERROR", "name is required")
		return "", "", "", nil, false, false
	}
	if utf8.RuneCountInString(name) > maxSteeringNameChars {
		writeError(w, http.StatusUnprocessableEntity, "STEERING_VALIDATION_ERROR", "name exceeds 200 characters")
		return "", "", "", nil, false, false
	}
	body = in.Body
	if strings.TrimSpace(body) == "" {
		writeError(w, http.StatusUnprocessableEntity, "STEERING_VALIDATION_ERROR", "body is required")
		return "", "", "", nil, false, false
	}
	if utf8.RuneCountInString(body) > maxSteeringBodyChars {
		writeError(w, http.StatusUnprocessableEntity, "STEERING_VALIDATION_ERROR", "body exceeds 8000 characters (steering is injected into every matching turn — keep it tight)")
		return "", "", "", nil, false, false
	}
	mode = "always"
	if in.InclusionMode != nil && *in.InclusionMode != "" {
		mode = *in.InclusionMode
	}
	if !validSteeringMode(mode) {
		writeError(w, http.StatusUnprocessableEntity, "STEERING_VALIDATION_ERROR",
			"inclusion_mode must be one of always|scene_match|manual|auto ("+steeringAutoModeNote+")")
		return "", "", "", nil, false, false
	}
	if in.MatchPattern != nil {
		trimmed := strings.TrimSpace(*in.MatchPattern)
		if trimmed != "" {
			pattern = &trimmed
		}
	}
	if mode == "scene_match" && pattern == nil {
		writeError(w, http.StatusUnprocessableEntity, "STEERING_VALIDATION_ERROR", "scene_match requires a non-empty match_pattern")
		return "", "", "", nil, false, false
	}
	enabled = true
	if in.Enabled != nil {
		enabled = *in.Enabled
	}
	return name, body, mode, pattern, enabled, true
}

func isUniqueViolation(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == "23505"
}

// listSteering — GET /v1/books/{book_id}/steering (VIEW grant).
// Returns ALL entries (enabled + disabled) so the editor panel can manage them.
func (s *Server) listSteering(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantView); !ok {
		return
	}
	rows, err := s.pool.Query(r.Context(), `
SELECT id, book_id, name, body, inclusion_mode, match_pattern, enabled, author_user_id, created_at, updated_at
FROM book_steering WHERE book_id=$1 ORDER BY created_at, id`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "STEERING_ERROR", "failed to list steering entries")
		return
	}
	defer rows.Close()
	items := make([]steeringRow, 0)
	for rows.Next() {
		var it steeringRow
		if err := rows.Scan(&it.ID, &it.BookID, &it.Name, &it.Body, &it.InclusionMode, &it.MatchPattern, &it.Enabled, &it.AuthorUserID, &it.CreatedAt, &it.UpdatedAt); err != nil {
			writeError(w, http.StatusInternalServerError, "STEERING_ERROR", "failed to scan steering entry")
			return
		}
		items = append(items, it)
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": len(items)})
}

// createSteering — POST /v1/books/{book_id}/steering (owner or EDIT grant).
func (s *Server) createSteering(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	caller, _, _, ok := s.authBook(w, r, bookID, GrantEdit)
	if !ok {
		return
	}
	var in steeringInput
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	name, body, mode, pattern, enabled, ok := validateSteeringInput(w, in)
	if !ok {
		return
	}
	ctx := r.Context()
	// Row cap (soft, DR-C1): refuse the 21st entry. COUNT-then-INSERT has a
	// theoretical race, acceptable for a soft cap on a human-authored resource.
	var n int
	if err := s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM book_steering WHERE book_id=$1`, bookID).Scan(&n); err != nil {
		writeError(w, http.StatusInternalServerError, "STEERING_ERROR", "failed to check steering cap")
		return
	}
	if n >= maxSteeringRowsPerBook {
		writeError(w, http.StatusUnprocessableEntity, "STEERING_LIMIT_REACHED",
			"steering limit reached (20 entries per book) — delete or merge an entry first")
		return
	}
	var it steeringRow
	err := s.pool.QueryRow(ctx, `
INSERT INTO book_steering (book_id, name, body, inclusion_mode, match_pattern, enabled, author_user_id)
VALUES ($1,$2,$3,$4,$5,$6,$7)
RETURNING id, book_id, name, body, inclusion_mode, match_pattern, enabled, author_user_id, created_at, updated_at
`, bookID, name, body, mode, pattern, enabled, caller).
		Scan(&it.ID, &it.BookID, &it.Name, &it.Body, &it.InclusionMode, &it.MatchPattern, &it.Enabled, &it.AuthorUserID, &it.CreatedAt, &it.UpdatedAt)
	if isUniqueViolation(err) {
		writeError(w, http.StatusConflict, "STEERING_NAME_CONFLICT", "a steering entry with this name already exists on this book")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "STEERING_ERROR", "failed to create steering entry")
		return
	}
	writeJSON(w, http.StatusCreated, it)
}

// updateSteering — PUT /v1/books/{book_id}/steering/{steering_id} (owner or
// EDIT grant). Full-replace semantics. The UPDATE is scoped by id AND book_id
// so an id from another book uniformly 404s (tenancy — never cross-book).
func (s *Server) updateSteering(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	steeringID, ok := parseUUIDParam(w, r, "steering_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantEdit); !ok {
		return
	}
	var in steeringInput
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	name, body, mode, pattern, enabled, ok := validateSteeringInput(w, in)
	if !ok {
		return
	}
	var it steeringRow
	err := s.pool.QueryRow(r.Context(), `
UPDATE book_steering
SET name=$3, body=$4, inclusion_mode=$5, match_pattern=$6, enabled=$7, updated_at=now()
WHERE id=$1 AND book_id=$2
RETURNING id, book_id, name, body, inclusion_mode, match_pattern, enabled, author_user_id, created_at, updated_at
`, steeringID, bookID, name, body, mode, pattern, enabled).
		Scan(&it.ID, &it.BookID, &it.Name, &it.Body, &it.InclusionMode, &it.MatchPattern, &it.Enabled, &it.AuthorUserID, &it.CreatedAt, &it.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "STEERING_NOT_FOUND", "steering entry not found")
		return
	}
	if isUniqueViolation(err) {
		writeError(w, http.StatusConflict, "STEERING_NAME_CONFLICT", "a steering entry with this name already exists on this book")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "STEERING_ERROR", "failed to update steering entry")
		return
	}
	writeJSON(w, http.StatusOK, it)
}

// deleteSteering — DELETE /v1/books/{book_id}/steering/{steering_id} (owner or
// EDIT grant). Scoped by id AND book_id; missing → 404.
func (s *Server) deleteSteering(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	steeringID, ok := parseUUIDParam(w, r, "steering_id")
	if !ok {
		return
	}
	if _, _, _, ok := s.authBook(w, r, bookID, GrantEdit); !ok {
		return
	}
	tag, err := s.pool.Exec(r.Context(),
		`DELETE FROM book_steering WHERE id=$1 AND book_id=$2`, steeringID, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "STEERING_ERROR", "failed to delete steering entry")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "STEERING_NOT_FOUND", "steering entry not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// getInternalBookSteering — GET /internal/books/{book_id}/steering
// (internal-token gated in the router). chat-service's render path: returns
// ONLY enabled entries, projected to the fields the selector needs. The caller
// has already authorized the user against the book (chat sessions are
// book-scoped through the FE contract; mirrors getInternalReaderLanguage's
// trust model), so no per-user grant check here.
func (s *Server) getInternalBookSteering(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BAD_BOOK_ID", "invalid book id")
		return
	}
	rows, err := s.pool.Query(r.Context(), `
SELECT id, name, body, inclusion_mode, match_pattern
FROM book_steering WHERE book_id=$1 AND enabled=true ORDER BY created_at, id`, bookID)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "RESOLVE_FAILED", "steering resolution failed")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		var id uuid.UUID
		var name, body, mode string
		var pattern *string
		if err := rows.Scan(&id, &name, &body, &mode, &pattern); err != nil {
			writeError(w, http.StatusServiceUnavailable, "RESOLVE_FAILED", "steering scan failed")
			return
		}
		items = append(items, map[string]any{
			"id":             id,
			"name":           name,
			"body":           body,
			"inclusion_mode": mode,
			"match_pattern":  pattern,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}
