"""E0-4c collaboration access layer for composition-service.

The book grant is the single chokepoint deciding whether a caller may compose on
a book. ``authorize_book`` resolves the caller's grant on the book and gates by
the operation's required tier (PO-locked, E0-4 design §E0-4c):

  - read-pack (context assembly, grounding) → VIEW
  - prose-gen (engine), create-work, patch-work → EDIT

Anti-oracle (matches E0-2/E0-3/E0-4a): ``none`` (no grant / missing book) →
``OwnershipError`` which the routers already map to **404** (no existence
oracle); a grantee under the required tier → ``InsufficientGrant`` → **403**.

composition_work stays PER-USER (caller-keyed) — the book grant gates ACCESS,
not the work row's ownership (PO decision, mirrors E0-4a settings-per-user: the
work bundles per-user authoring settings/model-refs that must not leak across
collaborators under BYOK). Shared artifacts (prose drafts) live in book-service,
already grant-honored by E0-2.
"""

from uuid import UUID

from app.grant_client import GrantClient, GrantLevel
from app.packer.pack import OwnershipError

__all__ = ["GrantLevel", "InsufficientGrant", "authorize_book"]


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
