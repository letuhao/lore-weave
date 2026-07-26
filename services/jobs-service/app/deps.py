"""Auth + DB dependencies.

The owner-scoped read API VERIFIES the JWT signature (HS256 with the shared
`JWT_SECRET`) — owner scoping is a security boundary (the spec forbids any
cross-tenant job leak in list/detail/stream), so a blind/unverified decode is
NOT acceptable here. Mirrors campaign-service `deps.py`.
"""

import asyncpg
from loreweave_authn import build_get_current_user

from .config import settings
from .database import get_pool

# Resolve the acting user from a signature-verified bearer JWT. Returns the `sub`
# claim string (the owner_user_id every job query filters on) via the shared
# `loreweave_authn` verifier (HS256-pinned, exp REQUIRED, sub→UUID). `return_subject`
# preserves the prior `str(sub)` return shape callers depend on.
get_current_user = build_get_current_user(lambda: settings.jwt_secret, return_subject=True)


async def get_db() -> asyncpg.Pool:
    return get_pool()
