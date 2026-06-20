"""The THREE scope guards (H15) — book-scoped, user-scoped, project-scoped.

A tool declares its scope via `_meta.scope`; the matching guard runs server-side
before the handler body, enforcing that the envelope caller (`ToolContext.user_id`)
may act on the named resource. All guards are **fail-closed**: any resolver error,
timeout, or ambiguity → deny (raise the H13 uniform error), never allow.

  - `require_book_owner(resolver, level)` — the book-ownership guard (SEC-2),
    extracted in spirit from glossary `verifyBookOwner`. Resolves the caller's
    grant level on a book via an injected resolver and requires >= `level`. Wraps
    the resolver in a ~60s POSITIVE-ONLY cache (a denial is never cached, so a
    freshly-granted user is never stale-denied; a revoke takes effect within TTL).

  - `require_user_scope(owner_of)` — built fresh. For user-global resources
    (settings/models) that have NO book_id: checks `resource.user_id == caller`.
    `owner_of(ctx, resource_id) -> UUID` returns the row's owner.

  - `require_project(owner_of=None)` — built fresh. Requires a project_id in the
    envelope; optionally checks project membership/ownership via `owner_of`.

A guard returns a verified value (the grant level / resolved owner) on success so
the handler can use it; on denial it raises `uniform_not_accessible()` (H13 — a
denied caller and a missing resource look identical, no enumeration oracle).
"""

from __future__ import annotations

import time
from typing import Awaitable, Callable, Protocol
from uuid import UUID

from .context import ToolContext
from .errors import uniform_not_accessible

__all__ = [
    "GrantResolver",
    "OwnerResolver",
    "require_book_owner",
    "require_user_scope",
    "require_project",
]

# Default positive-grant cache TTL (~60s per C-KIT-PY; matches the platform grant
# SDK's revoke SLA neighbourhood).
DEFAULT_GRANT_CACHE_TTL_S = 60.0


class GrantResolver(Protocol):
    """Resolves the integer grant level a user holds on a book. The consuming
    service injects this (typically wrapping `loreweave_grants.GrantClient`). Higher
    int = more permission; 0 = no access. Must be fail-closed itself (return 0 on a
    backend error)."""

    async def __call__(self, book_id: UUID, user_id: UUID) -> int: ...


# owner_of(ctx, resource_id) -> the UUID of the user who owns the resource row.
# May be sync or async; raising signals "not found" → guard denies uniformly.
OwnerResolver = Callable[[ToolContext, UUID], "UUID | Awaitable[UUID]"]


async def _maybe_await(value):
    if hasattr(value, "__await__"):
        return await value
    return value


def require_book_owner(
    resolver: GrantResolver,
    level: int,
    *,
    cache_ttl_s: float = DEFAULT_GRANT_CACHE_TTL_S,
    now: Callable[[], float] = time.monotonic,
):
    """Build an async book-ownership guard requiring grant >= `level` (SEC-2).

    Returns an async callable ``guard(ctx, book_id) -> int`` that returns the
    verified grant level on success and raises the H13 uniform error on denial.
    Fail-closed: a resolver exception is treated as level 0 (deny). A POSITIVE
    grant is cached for `cache_ttl_s`; denials are never cached.
    """
    # key "user_id:book_id" -> (level, expiry)
    cache: dict[str, tuple[int, float]] = {}

    async def guard(ctx: ToolContext, book_id: UUID) -> int:
        key = f"{ctx.user_id}:{book_id}"
        hit = cache.get(key)
        if hit is not None and now() < hit[1]:
            resolved = hit[0]
        else:
            try:
                resolved = await resolver(book_id, ctx.user_id)
            except Exception as exc:  # noqa: BLE001 — fail closed on ANY resolver error
                raise uniform_not_accessible(exc) from exc
            if resolved > 0:
                cache[key] = (resolved, now() + cache_ttl_s)
        if resolved < level:
            raise uniform_not_accessible()
        return resolved

    return guard


def require_user_scope(owner_of: OwnerResolver):
    """Build a user-scope guard: `resource.user_id == caller` (H15, built fresh).

    For user-global resources (settings/models) with no book_id. Returns an async
    callable ``guard(ctx, resource_id) -> UUID`` returning the verified owner on
    success; raises the H13 uniform error if the resource is missing OR owned by
    someone else (indistinguishable). Fail-closed on any `owner_of` error.
    """

    async def guard(ctx: ToolContext, resource_id: UUID) -> UUID:
        try:
            owner = await _maybe_await(owner_of(ctx, resource_id))
            owner_uuid = owner if isinstance(owner, UUID) else UUID(str(owner))
        except Exception as exc:  # noqa: BLE001 — missing/lookup error → uniform deny
            raise uniform_not_accessible(exc) from exc
        if owner_uuid != ctx.user_id:
            raise uniform_not_accessible()
        return owner_uuid

    return guard


def require_project(owner_of: OwnerResolver | None = None):
    """Build a project-scope guard (H15, built fresh).

    Requires a `project_id` in the envelope. When `owner_of` is provided it must
    return the user who owns/may-access the project; the guard then checks
    membership (`owner == caller`). With no `owner_of`, it only asserts the call
    carries a project envelope (the lightest project scoping).

    Returns an async callable ``guard(ctx) -> UUID`` (the verified project_id);
    raises the H13 uniform error when there is no project envelope or the caller is
    not a member. Fail-closed.
    """

    async def guard(ctx: ToolContext) -> UUID:
        if ctx.project_id is None:
            raise uniform_not_accessible()
        if owner_of is not None:
            try:
                owner = await _maybe_await(owner_of(ctx, ctx.project_id))
                owner_uuid = owner if isinstance(owner, UUID) else UUID(str(owner))
            except Exception as exc:  # noqa: BLE001 — fail closed
                raise uniform_not_accessible(exc) from exc
            if owner_uuid != ctx.user_id:
                raise uniform_not_accessible()
        return ctx.project_id

    return guard
