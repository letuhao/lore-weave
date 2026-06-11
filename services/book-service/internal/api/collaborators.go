package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// GrantLevel is the ordered permission a user holds on a book.
// E0 (collaboration-permissions): none < view < edit < manage < owner.
type GrantLevel int

const (
	GrantNone   GrantLevel = 0
	GrantView   GrantLevel = 1
	GrantEdit   GrantLevel = 2
	GrantManage GrantLevel = 3
	GrantOwner  GrantLevel = 4
)

func (g GrantLevel) String() string {
	switch g {
	case GrantOwner:
		return "owner"
	case GrantManage:
		return "manage"
	case GrantEdit:
		return "edit"
	case GrantView:
		return "view"
	default:
		return "none"
	}
}

// roleToLevel maps a stored book_collaborators.role to a GrantLevel.
// Unknown/empty → GrantNone (default-deny — never silently grant).
func roleToLevel(role string) GrantLevel {
	switch role {
	case "manage":
		return GrantManage
	case "edit":
		return GrantEdit
	case "view":
		return GrantView
	default:
		return GrantNone
	}
}

// validCollaboratorRole reports whether role is grantable. Owner is implicit
// (derived from books.owner_user_id) and is NOT a grantable role.
func validCollaboratorRole(role string) bool {
	return role == "view" || role == "edit" || role == "manage"
}

// resolveGrant resolves the caller's permission on a book, locally (book-service
// owns both `books` and `book_collaborators`). Owner is implicit via
// owner_user_id; otherwise the stored role; else none. A MISSING book yields
// (GrantNone, nil) — never an error and never a 404 — so callers cannot use it
// as an existence oracle (DESIGN R4 / INV-8 / H13).
func (s *Server) resolveGrant(ctx context.Context, bookID, userID uuid.UUID) (GrantLevel, error) {
	var owner uuid.UUID
	err := s.pool.QueryRow(ctx, `SELECT owner_user_id FROM books WHERE id=$1`, bookID).Scan(&owner)
	if err == pgx.ErrNoRows {
		return GrantNone, nil
	}
	if err != nil {
		return GrantNone, err
	}
	if owner == userID {
		return GrantOwner, nil
	}
	var role string
	err = s.pool.QueryRow(ctx, `SELECT role FROM book_collaborators WHERE book_id=$1 AND user_id=$2`, bookID, userID).Scan(&role)
	if err == pgx.ErrNoRows {
		return GrantNone, nil
	}
	if err != nil {
		return GrantNone, err
	}
	return roleToLevel(role), nil
}

// resolveAccess resolves both the caller's grant AND the book's lifecycle in one
// query, for the /access authority (E0-1 consumers gate edit/manage on lifecycle).
// A MISSING book yields (GrantNone, "", nil) — never an error, never a 404 (R4):
// grant is `none` and lifecycle is "" (absent), so it's still no existence oracle.
func (s *Server) resolveAccess(ctx context.Context, bookID, userID uuid.UUID) (GrantLevel, string, error) {
	var owner uuid.UUID
	var lifecycle string
	err := s.pool.QueryRow(ctx, `SELECT owner_user_id, lifecycle_state FROM books WHERE id=$1`, bookID).Scan(&owner, &lifecycle)
	if err == pgx.ErrNoRows {
		return GrantNone, "", nil
	}
	if err != nil {
		return GrantNone, "", err
	}
	if owner == userID {
		return GrantOwner, lifecycle, nil
	}
	var role string
	err = s.pool.QueryRow(ctx, `SELECT role FROM book_collaborators WHERE book_id=$1 AND user_id=$2`, bookID, userID).Scan(&role)
	if err == pgx.ErrNoRows {
		// No grant → return EMPTY lifecycle (same as a missing book), so /access
		// can't be used to distinguish exists-but-no-access from missing (R4).
		return GrantNone, "", nil
	}
	if err != nil {
		return GrantNone, "", err
	}
	return roleToLevel(role), lifecycle, nil
}

// getBookAccess (internal) — the single authority every service calls to resolve
// a (user, book) grant. Always 200 with a level + the book's lifecycle_state;
// `none` covers both missing-book and no-grant (zero existence oracle, R4).
// Fail-closed: a DB error → 503 so callers deny rather than assume access.
func (s *Server) getBookAccess(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BAD_BOOK_ID", "invalid book id")
		return
	}
	userID, err := uuid.Parse(r.URL.Query().Get("user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BAD_USER_ID", "invalid user_id")
		return
	}
	lvl, lifecycle, err := s.resolveAccess(r.Context(), bookID, userID)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "RESOLVE_FAILED", "grant resolution failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"grant_level": lvl.String(), "lifecycle_state": lifecycle})
}

// requireBookOwner gates owner-only grant management (D-E0-D). Not-owner and
// not-found both surface as a uniform 403 (no existence oracle). Returns the
// caller's user_id on success.
func (s *Server) requireBookOwner(w http.ResponseWriter, r *http.Request, bookID uuid.UUID) (uuid.UUID, bool) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "UNAUTHENTICATED", "missing or invalid token")
		return uuid.Nil, false
	}
	lvl, err := s.resolveGrant(r.Context(), bookID, userID)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "RESOLVE_FAILED", "grant resolution failed")
		return uuid.Nil, false
	}
	if lvl != GrantOwner {
		writeError(w, http.StatusForbidden, "FORBIDDEN", "not accessible")
		return uuid.Nil, false
	}
	return userID, true
}

type collaboratorRow struct {
	UserID    uuid.UUID `json:"user_id"`
	Role      string    `json:"role"`
	GrantedBy uuid.UUID `json:"granted_by"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

// listCollaborators (owner-only) — the collaborators of a book.
func (s *Server) listCollaborators(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BAD_BOOK_ID", "invalid book id")
		return
	}
	if _, ok := s.requireBookOwner(w, r, bookID); !ok {
		return
	}
	rows, err := s.pool.Query(r.Context(),
		`SELECT user_id, role, granted_by, created_at, updated_at FROM book_collaborators WHERE book_id=$1 ORDER BY created_at`, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "query failed")
		return
	}
	defer rows.Close()
	out := []collaboratorRow{}
	for rows.Next() {
		var c collaboratorRow
		if err := rows.Scan(&c.UserID, &c.Role, &c.GrantedBy, &c.CreatedAt, &c.UpdatedAt); err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "scan failed")
			return
		}
		out = append(out, c)
	}
	writeJSON(w, http.StatusOK, map[string]any{"collaborators": out})
}

// putCollaborator (owner-only) — grant or update a collaborator's role.
// Cannot target the owner; role must be view|edit|manage. Atomically writes
// the row + a `book.collaborator_granted` audit outbox event.
func (s *Server) putCollaborator(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BAD_BOOK_ID", "invalid book id")
		return
	}
	targetID, err := uuid.Parse(chi.URLParam(r, "user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BAD_USER_ID", "invalid user id")
		return
	}
	ownerID, ok := s.requireBookOwner(w, r, bookID)
	if !ok {
		return
	}
	if targetID == ownerID {
		writeError(w, http.StatusBadRequest, "CANNOT_GRANT_OWNER", "owner already has full access")
		return
	}
	var body struct {
		Role string `json:"role"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || !validCollaboratorRole(body.Role) {
		writeError(w, http.StatusBadRequest, "BAD_ROLE", "role must be view|edit|manage")
		return
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "begin failed")
		return
	}
	defer tx.Rollback(r.Context())
	if _, err := tx.Exec(r.Context(), `
		INSERT INTO book_collaborators (book_id, user_id, role, granted_by)
		VALUES ($1, $2, $3, $4)
		ON CONFLICT (book_id, user_id)
		DO UPDATE SET role = EXCLUDED.role, granted_by = EXCLUDED.granted_by, updated_at = now()
	`, bookID, targetID, body.Role, ownerID); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "grant failed")
		return
	}
	if err := insertBookOutbox(r.Context(), tx, "book.collaborator_granted", bookID, map[string]any{
		"book_id": bookID, "user_id": targetID, "role": body.Role, "granted_by": ownerID,
	}); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "audit failed")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "commit failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"user_id": targetID.String(), "role": body.Role})
}

// deleteCollaborator (owner-only) — revoke a collaborator. Idempotent (a
// no-op delete still 200s but emits no event). Atomically deletes the row +
// a `book.collaborator_revoked` audit event when a row was actually removed.
func (s *Server) deleteCollaborator(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BAD_BOOK_ID", "invalid book id")
		return
	}
	targetID, err := uuid.Parse(chi.URLParam(r, "user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BAD_USER_ID", "invalid user id")
		return
	}
	ownerID, ok := s.requireBookOwner(w, r, bookID)
	if !ok {
		return
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "begin failed")
		return
	}
	defer tx.Rollback(r.Context())
	ct, err := tx.Exec(r.Context(), `DELETE FROM book_collaborators WHERE book_id=$1 AND user_id=$2`, bookID, targetID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "revoke failed")
		return
	}
	if ct.RowsAffected() > 0 {
		if err := insertBookOutbox(r.Context(), tx, "book.collaborator_revoked", bookID, map[string]any{
			"book_id": bookID, "user_id": targetID, "revoked_by": ownerID,
		}); err != nil {
			writeError(w, http.StatusInternalServerError, "DB_ERROR", "audit failed")
			return
		}
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "commit failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "revoked"})
}

// insertBookOutbox writes a book-aggregate audit event within the given tx
// (atomic with the grant mutation). Mirrors insertOutboxEvent but with
// aggregate_type='book'.
func insertBookOutbox(ctx context.Context, tx pgx.Tx, eventType string, aggregateID uuid.UUID, payload map[string]any) error {
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("outbox marshal: %w", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
		VALUES ('book', $1, $2, $3)
	`, aggregateID, eventType, payloadJSON); err != nil {
		return fmt.Errorf("outbox insert: %w", err)
	}
	return nil
}
