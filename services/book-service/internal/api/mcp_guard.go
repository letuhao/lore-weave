package api

// S-BOOK (MCP fan-out) — the per-tool ownership guard for book-service's /mcp
// server. It reuses book-service's OWN local grant resolver (resolveGrant —
// book-service owns both `books` and `book_collaborators`, no self-RPC) rather
// than the kit's grantclient-backed BookOwnerGuard, which is bound to the
// HTTP grantclient (book-service is the grant authority itself, so wiring an
// HTTP client back to itself would be wrong). It DOES adopt the kit's uniform
// error sentinels + UniformNotAccessible (H13: no existence oracle) so the MCP
// surface collapses 403/404 the same way every other kit provider does.
//
// KIT-GAP NOTE (reported to integrator): the frozen C-KIT-GO BookOwnerGuard
// takes a grantclient.GrantChecker. book-service is the grant SSOT and resolves
// grants in-process, so it cannot satisfy that shape without an HTTP loop back
// to itself. We therefore use the kit's error sentinels + UniformNotAccessible
// (the H13 contract) but a LOCAL guard over resolveGrant. No kit edit needed.

import (
	"context"

	"github.com/google/uuid"

	lwmcp "github.com/loreweave/loreweave_mcp"
)

// mcpRequireGrant checks that `userID` holds at least `need` on `bookID`, using
// book-service's local resolver, and returns the kit's uniform sentinels:
//   - nil               → access granted
//   - ErrNotAccessible  → missing book OR caller lacks the grant (H13 collapse)
//   - ErrCheckUnavailable → the resolver failed (DB outage): "try again", fail-closed
//
// The book's OWNER is returned on success (quota attribution / event payloads).
// A `GrantNone` result is ALWAYS ErrNotAccessible regardless of whether the book
// exists — the resolver already collapses missing-book to GrantNone, so there is
// no existence oracle here either.
func (s *Server) mcpRequireGrant(ctx context.Context, bookID, userID uuid.UUID, need GrantLevel) (owner uuid.UUID, err error) {
	lvl, owner, _, rerr := s.resolve(ctx, bookID, userID)
	if rerr != nil {
		// DB/resolver outage → "unavailable, try again" (fail-closed, H10).
		return uuid.Nil, lwmcp.ErrCheckUnavailable
	}
	if lvl == GrantNone || !lvl.AtLeast(need) {
		// missing book, no grant, or below the required level — one uniform deny.
		return uuid.Nil, lwmcp.ErrNotAccessible
	}
	return owner, nil
}

// mcpOwnershipError maps an mcpRequireGrant error to a caller-visible message.
// ErrCheckUnavailable stays distinct ("try again") so the agent retries rather
// than reporting a false "I can't"; everything else is the uniform "not
// accessible" (H13). It runs UniformNotAccessible first so any future non-kit
// error also collapses correctly.
func mcpOwnershipError(err error) error {
	collapsed := lwmcp.UniformNotAccessible(err)
	if collapsed == lwmcp.ErrCheckUnavailable {
		return errBookCheckUnavailable
	}
	return errBookNotAccessible
}
