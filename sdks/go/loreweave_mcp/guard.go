package loreweave_mcp

import (
	"context"
	"errors"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
)

// GrantLevel re-exports grantclient.GrantLevel so callers configuring a
// BookOwnerGuard don't need to import grantclient just for the level constants.
type GrantLevel = grantclient.GrantLevel

// Grant level constants (re-exported for ergonomic guard configuration).
const (
	GrantNone   = grantclient.GrantNone
	GrantView   = grantclient.GrantView
	GrantEdit   = grantclient.GrantEdit
	GrantManage = grantclient.GrantManage
	GrantOwner  = grantclient.GrantOwner
)

// ErrNotAccessible is the single uniform sentinel a guard returns when the caller
// may not touch the resource — whether it does not exist OR the caller lacks
// access. Collapsing the two (H13) denies the agent an existence oracle: it can
// never distinguish "no such resource" from "not yours".
var ErrNotAccessible = errors.New("resource not accessible")

// ErrCheckUnavailable is returned when the ownership authority could not be
// reached, so access is UNKNOWN. Distinct from ErrNotAccessible so the caller can
// say "try again" rather than "I can't" (H10) — but still fail closed (deny).
var ErrCheckUnavailable = errors.New("ownership check unavailable, try again")

// Guard is the single ownership-check shape every tool runs before doing work.
// The three constructors below produce the three scope shapes (H15): book-scoped
// (BookOwnerGuard), user-scoped (UserScopeGuard), and project-scoped
// (ProjectGuard). Check returns nil iff userID may access resourceID; otherwise
// ErrNotAccessible (or ErrCheckUnavailable on an authority outage). Every guard
// is fail-closed: any error path denies.
type Guard interface {
	Check(ctx context.Context, userID, resourceID uuid.UUID) error
}

// GrantChecker is the slice of grantclient.Client that BookOwnerGuard needs.
// *grantclient.Client satisfies it directly; tests pass a fake. (The frozen
// C-KIT-GO contract named the concrete *grantclient.Client; we accept this
// interface instead so the guard is unit-testable without a live book-service —
// reported for COMPOSE A reconciliation.)
type GrantChecker interface {
	RequireGrant(ctx context.Context, bookID, userID uuid.UUID, need GrantLevel) error
}

// guardFunc adapts a plain function to the Guard interface.
type guardFunc func(ctx context.Context, userID, resourceID uuid.UUID) error

func (f guardFunc) Check(ctx context.Context, userID, resourceID uuid.UUID) error {
	return f(ctx, userID, resourceID)
}

// BookOwnerGuard checks that userID holds at least `level` on the book
// (resourceID is the book id). The grant resolution + 45-60s positive-only cache
// + fail-closed-on-outage behavior is the grantclient's (DefaultCacheTTL=45s).
// grantclient's ErrForbidden collapses to ErrNotAccessible (H13); ErrUnavailable
// → ErrCheckUnavailable (H10). This is the extracted glossary verifyBookOwner
// spine.
func BookOwnerGuard(grants GrantChecker, level GrantLevel) Guard {
	return guardFunc(func(ctx context.Context, userID, resourceID uuid.UUID) error {
		if grants == nil {
			return ErrCheckUnavailable
		}
		err := grants.RequireGrant(ctx, resourceID, userID, level)
		switch {
		case err == nil:
			return nil
		case errors.Is(err, grantclient.ErrUnavailable):
			return ErrCheckUnavailable
		case errors.Is(err, grantclient.ErrForbidden):
			return ErrNotAccessible
		default:
			// Unknown failure → fail closed, but as "unavailable, try again"
			// rather than a hard "not accessible", since the cause is unknown.
			return ErrCheckUnavailable
		}
	})
}

// UserScopeGuard checks that the resource is owned by the calling user — i.e.
// `resource.user_id == caller`. ownerOf resolves a resource id to its owning
// user id (e.g. a model row → its owner). Built fresh (no existing instance):
// the shape settings/models need, where there is no book and the resource is
// user-global (QA8/E11/H15).
//
// fail-closed: an ownerOf error collapses to ErrNotAccessible (no oracle), and a
// mismatch (resource owned by someone else) is also ErrNotAccessible.
func UserScopeGuard(ownerOf func(ctx context.Context, resID uuid.UUID) (uuid.UUID, error)) Guard {
	return guardFunc(func(ctx context.Context, userID, resourceID uuid.UUID) error {
		if ownerOf == nil {
			return ErrNotAccessible
		}
		owner, err := ownerOf(ctx, resourceID)
		if err != nil {
			return UniformNotAccessible(err)
		}
		if owner != userID || owner == uuid.Nil {
			return ErrNotAccessible
		}
		return nil
	})
}

// ProjectGuard checks that the calling user owns the project the resource belongs
// to. ownerOf resolves a project id to its owning user id. Built fresh — the
// project-scoped shape (H15). Same fail-closed semantics as UserScopeGuard.
func ProjectGuard(ownerOf func(ctx context.Context, projID uuid.UUID) (uuid.UUID, error)) Guard {
	return guardFunc(func(ctx context.Context, userID, resourceID uuid.UUID) error {
		if ownerOf == nil {
			return ErrNotAccessible
		}
		owner, err := ownerOf(ctx, resourceID)
		if err != nil {
			return UniformNotAccessible(err)
		}
		if owner != userID || owner == uuid.Nil {
			return ErrNotAccessible
		}
		return nil
	})
}

// UniformNotAccessible collapses an arbitrary ownership/lookup error to the
// single caller-visible outcome (H13): no error → nil; an authority-outage
// (grantclient.ErrUnavailable / ErrCheckUnavailable) → ErrCheckUnavailable
// ("try again"); everything else (not-found, forbidden, decode error) →
// ErrNotAccessible. This is the one place the 403/404 distinction is erased so a
// tool can't be used as an enumeration oracle.
func UniformNotAccessible(err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, grantclient.ErrUnavailable) || errors.Is(err, ErrCheckUnavailable) {
		return ErrCheckUnavailable
	}
	return ErrNotAccessible
}
