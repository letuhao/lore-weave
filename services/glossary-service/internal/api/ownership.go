package api

import (
	"context"
	"errors"
	"log/slog"
	"net/http"

	"github.com/google/uuid"

	"github.com/loreweave/grantclient"
	lwmcp "github.com/loreweave/loreweave_mcp"
)

// Grant sentinels for the book-scoped guards (E0-1 collaboration model).
var (
	// ErrNotAccessible — the caller's grant does not satisfy the required level
	// (covers not-a-collaborator AND missing book — deliberately UNIFORM, H13/R4,
	// so a tool can't be used as an existence oracle).
	ErrNotAccessible = errors.New("book not accessible")
	// ErrBookUnavailable — book-service couldn't be reached, so the grant is
	// UNKNOWN → fail closed (deny), never assume access.
	ErrBookUnavailable = errors.New("book grant unavailable")
	// ErrBookInactive — the caller has the grant, but the book is trashed/
	// purge_pending and the operation needs edit or higher (reads are still OK).
	ErrBookInactive = errors.New("book not in an editable state")
)

// buildGrantClient constructs the shared grant client from config. Returns nil
// when book-service coordinates are absent (mirrors the nil-on-misconfig pattern
// used for other optional clients) — the guards then fail closed. Logs loudly so
// a permanent deny-everything is debuggable.
func buildGrantClient(bookServiceURL, internalToken string) *grantclient.Client {
	gc, err := grantclient.NewClient(grantclient.Options{
		BaseURL:       bookServiceURL,
		InternalToken: internalToken,
	})
	if err != nil {
		slog.Error("glossary: grantclient init failed; ALL book-scoped guards will fail closed until fixed", "err", err)
		return nil
	}
	return gc
}

// checkGrant resolves the caller's grant on bookID and returns nil iff it
// satisfies need. For need>=edit it ALSO requires the book be active
// (trashed/purge_pending → ErrBookInactive); reads (view) are allowed on an
// inactive book. Fail-closed on a missing client or an unreachable book-service.
func (s *Server) checkGrant(ctx context.Context, bookID, userID uuid.UUID, need grantclient.GrantLevel) error {
	if s.grantClient == nil {
		return ErrBookUnavailable
	}
	acc, err := s.grantClient.ResolveAccess(ctx, bookID, userID)
	if err != nil {
		return ErrBookUnavailable
	}
	// P2·F tenant-boundary audit. A caller with a REAL sub-owner grant
	// (view/edit/manage) is a collaborator crossing into the book owner's tenant.
	// Emit 'granted' when the grant satisfies `need`, 'denied' otherwise. Skip
	// Level==none (indistinguishable from a missing book here — no confirmed
	// tenant) and Level==owner (own tenant). See tenant_audit.go.
	if s.emitTenantAudit != nil &&
		acc.Level > grantclient.GrantNone && acc.Level < grantclient.GrantOwner {
		outcome := auditOutcomeGranted
		if !acc.Level.AtLeast(need) {
			outcome = auditOutcomeDenied
		}
		s.emitTenantAudit(userID, bookID, outcome)
	}
	if !acc.Level.AtLeast(need) {
		return ErrNotAccessible
	}
	// OD-8 (owned-books-only): a PUBLIC MCP key (X-Mcp-Key-Id in ctx) reaches a
	// book ONLY as its OWNER, never via a collaboration grant. A share never
	// confers OWNER (E0: none<view<edit<manage<owner), so requiring OWNER here is
	// exactly "owned, not shared". Applied as a SEPARATE check (not by mutating
	// `need`) so it doesn't disturb the write-active gate below — a public OWNER
	// read on a trashed book stays allowed. First-party/HTTP calls are unaffected.
	if lwmcp.OwnerOnlyFromCtx(ctx) && !acc.Level.AtLeast(grantclient.GrantOwner) {
		return ErrNotAccessible
	}
	if need >= grantclient.GrantEdit && !acc.Active() {
		return ErrBookInactive
	}
	return nil
}

// requireGrant is the HTTP-handler guard. It writes the appropriate error
// response and returns false on deny; true means the caller may proceed.
func (s *Server) requireGrant(w http.ResponseWriter, ctx context.Context, bookID, userID uuid.UUID, need grantclient.GrantLevel) bool {
	switch err := s.checkGrant(ctx, bookID, userID, need); {
	case err == nil:
		return true
	case errors.Is(err, ErrBookUnavailable):
		writeError(w, http.StatusServiceUnavailable, "GLOSS_UPSTREAM_UNAVAILABLE", "book service unavailable")
	case errors.Is(err, ErrBookInactive):
		writeError(w, http.StatusConflict, "GLOSS_BOOK_INVALID_LIFECYCLE", "book is not in an editable state")
	default: // ErrNotAccessible (under-grant or missing book — uniform 403, no oracle)
		writeError(w, http.StatusForbidden, "GLOSS_FORBIDDEN", "forbidden")
	}
	return false
}
