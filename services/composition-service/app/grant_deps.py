"""E0-4c collaboration access layer for composition-service.

The book grant is the single chokepoint deciding whether a caller may compose on
a book. ``authorize_book`` resolves the caller's grant on the book and gates by
the operation's required tier (PO-locked, E0-4 design §E0-4c):

  - read-pack (context assembly, grounding) → VIEW
  - prose-gen (engine), create-work, patch-work → EDIT

Anti-oracle (matches E0-2/E0-3/E0-4a): ``none`` (no grant / missing book) →
``OwnershipError`` which the routers already map to **404** (no existence
oracle); a grantee under the required tier → ``InsufficientGrant`` → **403**.

composition_work — and every table in the book package — is PER-BOOK, not
per-user (BPS-1/2/8; `docs/specs/2026-07-01-writing-studio/00A_BOOK_PACKAGE_STRUCTURE.md`
+ `25_package_migration_master.md` PM-14, which supersede the earlier PO
decision that kept composition_work caller-keyed). Rows carry ``created_by`` as
a plain ACTOR stamp (who did it — spend/audit attribution under BYOK), never a
scope key; no repo query filters on the actor. Access is decided HERE, before
the repo, by the caller's E0 grant on the row's ``book_id``. What the old
decision protected (per-user model-refs) lives in per-user settings surfaces
(PM-15); the Work's pinned embed model stays on the shared manifest as a
TECHNICAL PIN, resolved per-caller at use (OQ-9). Shared artifacts (prose
drafts) live in book-service, already grant-honored by E0-2.
"""

from uuid import UUID

from app.db.repositories.works import WorksRepo
from app.grant_client import GrantClient, GrantLevel
from app.packer.pack import OwnershipError

__all__ = ["GrantLevel", "InsufficientGrant", "GrantAuthorityUnavailable",
           "authorize_book", "book_id_for_project"]


class InsufficientGrant(Exception):
    """The caller holds a grant on the book but below the tier this operation
    requires. Distinct from OwnershipError (no grant) so routers map it to 403,
    not 404 — a grantee already knows the book exists, so there's no oracle."""


class GrantAuthorityUnavailable(OwnershipError):
    """The grant could not be resolved because the AUTHORITY was unreachable.

    🔴 A SUBCLASS OF `OwnershipError`, AND THAT IS THE WHOLE SAFETY OF THIS CHANGE. 63 sites
    across 28 files catch `OwnershipError` / `InsufficientGrant` and map them to the uniform
    404/403. A NEW exception type none of them named would escape every one of those handlers
    and turn a book-service outage into a 500 across the entire service — a worse defect than
    the bare refusal this row is about. As a subclass, every existing handler catches it exactly
    as before and the mapping is byte-identical; a site that wants to tell the two apart catches
    the subclass FIRST, which is the ordering rule this repo already records for SDK errors.


    🔴 THIS IS NOT A FACT ABOUT THE CALLER'S DATA, which is the whole reason it is its own
    exception. Until 2026-08-31 a book-service outage resolved to NONE and became an
    `OwnershipError` — indistinguishable from "you have no grant on this book" — so a route
    answered a permission refusal to an OUTAGE. Measured live: a real confirm token redeemed
    against an instance whose book-service was unreachable produced

        403 {"code": "action_error"}

    with no detail, while the SDK logged "grant authority unavailable (fail-closed deny): All
    connection attempts failed" one frame away. The reason was known and thrown away.

    THE DENY IS UNCHANGED AND MUST STAY SO. Fail-closed on an unreachable authority is correct;
    this only lets the route say the refusal is RETRYABLE rather than about the caller. It is the
    same principle the platform already accepted one layer up, where composition's confirm route
    names its BookClientError 502 because an upstream failure is not a fact about the caller's
    data — and the Python mirror of `grantclient.ErrUnavailable`, which the Go SDK has carried
    all along (owner ruling 2026-08-31, DQ-T66 (a)).

    NO ORACLE. It discloses nothing about whether the book exists or who may reach it: the
    authority was down, so NOBODY could have been resolved. That is why raising it does not
    reopen the anti-oracle hole `OwnershipError` exists to close.
    """


async def authorize_book(
    grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel
) -> GrantLevel:
    """Resolve + gate the caller's grant on ``book_id``. Returns the level on
    success; raises OwnershipError (none → 404), InsufficientGrant (under-tier
    → 403), or GrantAuthorityUnavailable (authority down → retryable).

    Fail-closed throughout: an outage still DENIES, and the only thing that changed on
    2026-08-31 is that it denies with a reason the caller can act on."""
    lvl = await grant.resolve_grant(book_id, caller)
    if lvl == GrantLevel.NONE:
        # Asked only on the DENY path, and only after the deny is already decided — so the
        # happy path is untouched and no grant is ever softened by it.
        if getattr(grant, "last_denial_was_unavailable", None) and \
                grant.last_denial_was_unavailable(book_id, caller):
            raise GrantAuthorityUnavailable(
                "the grant authority could not be reached, so access could not be checked")
        raise OwnershipError("caller has no grant on the book")
    if not lvl.at_least(need):
        raise InsufficientGrant(
            f"caller grant {lvl.name.lower()} is below required {need.name.lower()}"
        )
    return lvl


async def book_id_for_project(
    works: WorksRepo, grant: GrantClient, project_id: UUID, caller: UUID, need: GrantLevel
) -> UUID:
    """PM-8 HTTP mirror of MCP's ``_book_or_deny``: resolve ``project_id`` to its
    Work's ``book_id`` via the ids-only ``WorksRepo.scope_meta`` (un-user-scoped,
    anti-oracle — ids only, never row content), then gate the caller's book grant
    at the required tier. Returns the ``book_id`` on success. A missing project
    raises ``OwnershipError`` — the routers' existing mapping turns both "no such
    project" and "no grant" into the same uniform 404 (no existence oracle);
    under-tier raises ``InsufficientGrant`` → 403 as usual."""
    meta = await works.scope_meta(project_id)
    if meta is None:
        raise OwnershipError("no work for project")
    await authorize_book(grant, meta.book_id, caller, need)
    return meta.book_id
