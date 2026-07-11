package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"sync"
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

// AtLeast reports whether g satisfies the required level (e.g. edit satisfies
// view+edit but not manage). Ordered: none<view<edit<manage<owner.
func (g GrantLevel) AtLeast(need GrantLevel) bool { return g >= need }

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

// resolveBookAuth is the single local grant resolver (book-service owns both
// `books` and `book_collaborators`; no self-RPC). It returns the caller's grant
// level, the book's OWNER (needed for quota attribution — E0-2 §3d, content always
// bills the owner not an editing collaborator), and the book's lifecycle.
//
// A MISSING book yields (GrantNone, uuid.Nil, "", nil) — never an error, never a
// 404 — so it can't be used as an existence oracle (DESIGN R4 / INV-8 / H13). A
// book that EXISTS but the caller has no grant on yields (GrantNone, owner,
// lifecycle, nil): the owner is known to the resolver but callers collapse `none`
// to a uniform deny, so nothing leaks.
func (s *Server) resolveBookAuth(ctx context.Context, bookID, userID uuid.UUID) (lvl GrantLevel, owner uuid.UUID, lifecycle string, err error) {
	err = s.pool.QueryRow(ctx, `SELECT owner_user_id, lifecycle_state FROM books WHERE id=$1`, bookID).Scan(&owner, &lifecycle)
	if err == pgx.ErrNoRows {
		return GrantNone, uuid.Nil, "", nil
	}
	if err != nil {
		return GrantNone, uuid.Nil, "", err
	}
	if owner == userID {
		return GrantOwner, owner, lifecycle, nil
	}
	var role string
	err = s.pool.QueryRow(ctx, `SELECT role FROM book_collaborators WHERE book_id=$1 AND user_id=$2`, bookID, userID).Scan(&role)
	if err == pgx.ErrNoRows {
		return GrantNone, owner, lifecycle, nil
	}
	if err != nil {
		return GrantNone, owner, "", err
	}
	return roleToLevel(role), owner, lifecycle, nil
}

// resolve dispatches to the injected grant resolver (tests stub it) or, when
// unset, the real local resolver. The nil fallback keeps a struct-literal
// Server (e.g. `&Server{pool: …}` in a future integration test) from panicking
// in this auth chokepoint — production always wires resolveBook via NewServer.
func (s *Server) resolve(ctx context.Context, bookID, userID uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
	if s.resolveBook != nil {
		return s.resolveBook(ctx, bookID, userID)
	}
	return s.resolveBookAuth(ctx, bookID, userID)
}

// resolveGrant resolves just the caller's permission on a book (see
// resolveBookAuth). A MISSING book yields (GrantNone, nil) — no existence oracle.
func (s *Server) resolveGrant(ctx context.Context, bookID, userID uuid.UUID) (GrantLevel, error) {
	lvl, _, _, err := s.resolve(ctx, bookID, userID)
	return lvl, err
}

// resolveAccess resolves the caller's grant AND the book's lifecycle, for the
// /access authority (E0-1 consumers gate edit/manage on lifecycle). On NO grant
// (missing book or no role) it returns an EMPTY lifecycle — same as a missing
// book — so /access can't distinguish exists-but-no-access from missing (R4).
func (s *Server) resolveAccess(ctx context.Context, bookID, userID uuid.UUID) (GrantLevel, string, error) {
	lvl, _, lifecycle, err := s.resolve(ctx, bookID, userID)
	if err != nil {
		return GrantNone, "", err
	}
	if lvl == GrantNone {
		return GrantNone, "", nil
	}
	return lvl, lifecycle, nil
}

// authBook is the E0-2 grant chokepoint for book-service's OWN per-book routes.
// It authenticates the caller, resolves their grant locally, and enforces `need`,
// writing the uniform HTTP error + returning ok=false on any failure:
//
//	401 — no/invalid token
//	404 — grant `none` (missing book OR no grant: no existence oracle, INV-8/H13)
//	403 — caller has access but below `need` (they already know it exists)
//	503 — DB error resolving the grant (fail-closed)
//
// It does NOT gate on lifecycle — book-service handlers carry their own precise
// per-state checks (patchBook 409 on non-active, transition handlers validate
// bState/cState). The returned `owner` is the book's owner (for quota
// attribution, §3d); `lifecycle` is the book's state if the caller wants it.
func (s *Server) authBook(w http.ResponseWriter, r *http.Request, bookID uuid.UUID, need GrantLevel) (caller, owner uuid.UUID, lifecycle string, ok bool) {
	caller, authed := s.requireUserID(r)
	if !authed {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return uuid.Nil, uuid.Nil, "", false
	}
	lvl, owner, lc, err := s.resolve(r.Context(), bookID, caller)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "RESOLVE_FAILED", "grant resolution failed")
		return uuid.Nil, uuid.Nil, "", false
	}
	// P2·F tenant-boundary audit. A crossing exists only when the book has a KNOWN
	// owner that is NOT the caller (owner==Nil ⇒ missing book, no tenant to cross;
	// owner==caller ⇒ own book). Emit 'granted' when the caller's grant satisfies
	// `need`, 'denied' otherwise (under-grant 403 OR no-grant-on-existing-book 404).
	// Coalesced first-per-window; fire-and-forget, never blocks the response.
	if s.emitTenantAudit != nil && owner != uuid.Nil && owner != caller {
		outcome := auditOutcomeGranted
		if lvl == GrantNone || !lvl.AtLeast(need) {
			outcome = auditOutcomeDenied
		}
		s.emitTenantAudit(caller, bookID, owner, outcome)
	}
	if lvl == GrantNone {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return uuid.Nil, uuid.Nil, "", false
	}
	if !lvl.AtLeast(need) {
		writeError(w, http.StatusForbidden, "BOOK_FORBIDDEN", "insufficient access")
		return uuid.Nil, uuid.Nil, "", false
	}
	return caller, owner, lc, true
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
	lvl, owner, lifecycle, err := s.resolve(r.Context(), bookID, userID)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "RESOLVE_FAILED", "grant resolution failed")
		return
	}
	resp := map[string]string{"grant_level": lvl.String(), "lifecycle_state": lifecycle}
	// owner_user_id lets a grant-holder consumer resolve a cross-tenant read of the
	// owner's per-(user,book) rows (e.g. the book-tier model settings). Returned ONLY
	// to a grantee (lvl != none) so a non-grantee never gets an owner/existence oracle.
	if lvl != GrantNone && owner != uuid.Nil {
		resp["owner_user_id"] = owner.String()

		// WS-1.2 (D16) — `kind` rides the access contract, behind the SAME grant gate.
		//
		// Every downstream egress surface (wiki, public-MCP, notifications, catalog,
		// statistics) resolves access through here. Without `kind` they CANNOT enforce the
		// diary taint even if they want to — they have no way to ask "is this private?".
		// This is the enabling half of D16, exactly like the kg_indexed filter was the
		// enabling half of publish-independent indexing.
		//
		// Gated behind lvl != GrantNone for the same reason owner_user_id is: an ungated
		// `kind` would be an ORACLE — a stranger could probe any book id and learn which
		// users keep a diary, which is itself sensitive.
		// `kind` is the privacy taint every downstream egress guard keys on. review-impl:
		// swallowing the lookup error and answering 200 WITHOUT it is a fail-open by
		// construction — a consumer that expects `kind` and does not find it will treat the
		// book as untainted. So a real DB error must FAIL the request (503), not silently
		// omit the field. (s.pool is nil only in the pure-unit grant tests, which have no
		// database; there the field is legitimately absent and the DB-level locks still hold.)
		if s.pool != nil {
			var kind string
			if err := s.pool.QueryRow(r.Context(),
				`SELECT kind FROM books WHERE id=$1`, bookID).Scan(&kind); err != nil {
				writeError(w, http.StatusServiceUnavailable, "RESOLVE_FAILED",
					"could not resolve book kind (the privacy taint must not be silently omitted)")
				return
			}
			resp["kind"] = kind
		}
	}
	writeJSON(w, http.StatusOK, resp)
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
	// E0-5 — display label for the collaborators panel, enriched from auth-service
	// (best-effort; "" when auth is unreachable or the user has no display name).
	DisplayName string `json:"display_name"`
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
	s.enrichDisplayNames(r.Context(), out)
	writeJSON(w, http.StatusOK, map[string]any{"collaborators": out})
}

// enrichDisplayNames fills each row's DisplayName from auth-service concurrently
// (best-effort: a failed/slow lookup leaves "" — the list never blocks on auth).
// Collaborator lists are tiny (owner-curated), so the fan-out is bounded in practice.
func (s *Server) enrichDisplayNames(ctx context.Context, rows []collaboratorRow) {
	if len(rows) == 0 {
		return
	}
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	var wg sync.WaitGroup
	for i := range rows {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			rows[i].DisplayName = s.authDisplayName(ctx, rows[i].UserID)
		}(i)
	}
	wg.Wait()
}

// authResolveByEmail asks auth-service for the user behind an invite email (E0-5).
// Returns (userID, displayName, found, err): found=false on a 404 (no such active
// user → the caller surfaces a clean "no user with that email"); err only on a
// transport/non-404 failure (the caller fails the invite rather than guessing).
func (s *Server) authResolveByEmail(ctx context.Context, email string) (uuid.UUID, string, bool, error) {
	u := fmt.Sprintf("%s/internal/users/by-email?email=%s",
		strings.TrimRight(s.cfg.AuthServiceInternalURL, "/"), url.QueryEscape(email))
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return uuid.Nil, "", false, err
	}
	req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	resp, err := internalClient.Do(req)
	if err != nil {
		return uuid.Nil, "", false, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound {
		return uuid.Nil, "", false, nil
	}
	if resp.StatusCode != http.StatusOK {
		return uuid.Nil, "", false, fmt.Errorf("auth by-email: status %d", resp.StatusCode)
	}
	var body struct {
		UserID      string `json:"user_id"`
		DisplayName string `json:"display_name"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return uuid.Nil, "", false, err
	}
	id, err := uuid.Parse(body.UserID)
	if err != nil {
		return uuid.Nil, "", false, err
	}
	return id, body.DisplayName, true, nil
}

// authDisplayName resolves a user_id → display_name via auth-service (E0-5 list
// enrichment). Best-effort: any failure → "" (never errors the list).
func (s *Server) authDisplayName(ctx context.Context, userID uuid.UUID) string {
	u := fmt.Sprintf("%s/internal/users/%s/profile",
		strings.TrimRight(s.cfg.AuthServiceInternalURL, "/"), userID.String())
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return ""
	}
	req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	resp, err := internalClient.Do(req)
	if err != nil {
		return ""
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return ""
	}
	var body struct {
		DisplayName string `json:"display_name"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return ""
	}
	return body.DisplayName
}

// inviteCollaborator (owner-only, E0-5) — grant a collaborator by EMAIL. Resolves
// the email to a user via auth-service, then upserts the role (identical write +
// audit + instant-revoke as putCollaborator). 404 when no active user has that
// email (uniform with a missing book — the owner can't probe the user table). The
// owner can't invite themselves. Returns {user_id, role, display_name}.
func (s *Server) inviteCollaborator(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BAD_BOOK_ID", "invalid book id")
		return
	}
	ownerID, ok := s.requireBookOwner(w, r, bookID)
	if !ok {
		return
	}
	var body struct {
		Email string `json:"email"`
		Role  string `json:"role"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || strings.TrimSpace(body.Email) == "" || !validCollaboratorRole(body.Role) {
		writeError(w, http.StatusBadRequest, "BAD_INVITE", "email and role (view|edit|manage) are required")
		return
	}
	targetID, displayName, found, err := s.authResolveByEmail(r.Context(), strings.TrimSpace(body.Email))
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "AUTH_UNAVAILABLE", "could not resolve the email")
		return
	}
	if !found {
		writeError(w, http.StatusNotFound, "USER_NOT_FOUND", "no user with that email")
		return
	}
	if targetID == ownerID {
		writeError(w, http.StatusBadRequest, "CANNOT_GRANT_OWNER", "you already have full access")
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
	// A re-invite at a lower role is a downgrade → drop the cached grant at once.
	if err := insertGrantRevokeOutbox(r.Context(), tx, bookID, targetID); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "audit failed")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "DB_ERROR", "commit failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{
		"user_id": targetID.String(), "role": body.Role, "display_name": displayName,
	})
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
	// D-GRANT-INSTANT-REVOKE: a role change must drop the target's cached grant so a
	// downgrade takes effect at once (not after the 45s TTL). Same tx (transactional).
	if err := insertGrantRevokeOutbox(r.Context(), tx, bookID, targetID); err != nil {
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
		// D-GRANT-INSTANT-REVOKE: drop the revoked user's cached grant immediately.
		if err := insertGrantRevokeOutbox(r.Context(), tx, bookID, targetID); err != nil {
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

// insertGrantRevokeOutbox writes a grant cache-invalidation event in the given tx
// (D-GRANT-INSTANT-REVOKE). aggregate_type='grant_revoke' → the worker-infra relay
// ships it to loreweave:events:grant_revoke, which every grant client tails to drop
// its cached (user,book) grant immediately rather than waiting out the 45s TTL.
// Transactional with the collaborator change; a lost relay delivery degrades to the
// TTL (fail-safe). Emitted on BOTH a downgrade (role change) and a revoke (delete) —
// over-emitting on an upgrade is harmless (just an extra re-fetch).
func insertGrantRevokeOutbox(ctx context.Context, tx pgx.Tx, bookID, userID uuid.UUID) error {
	payloadJSON, err := json.Marshal(map[string]any{"user_id": userID, "book_id": bookID})
	if err != nil {
		return fmt.Errorf("grant-revoke outbox marshal: %w", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
		VALUES ('grant_revoke', $1, 'grant.revoked', $2)
	`, bookID, payloadJSON); err != nil {
		return fmt.Errorf("grant-revoke outbox insert: %w", err)
	}
	return nil
}
