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

__all__ = ["GrantLevel", "InsufficientGrant", "authorize_book", "book_id_for_project"]


class InsufficientGrant(Exception):
    """The caller holds a grant on the book but below the tier this operation
    requires. Distinct from OwnershipError (no grant) so routers map it to 403,
    not 404 — a grantee already knows the book exists, so there's no oracle."""


async def authorize_book(
    grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel
) -> GrantLevel:
    """Resolve + gate the caller's grant on ``book_id``. Returns the level on
    success; raises OwnershipError (none → 404) or InsufficientGrant (under-tier
    → 403). Fail-closed: a book-service outage resolves to NONE → OwnershipError."""
    lvl = await grant.resolve_grant(book_id, caller)
    if lvl == GrantLevel.NONE:
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
