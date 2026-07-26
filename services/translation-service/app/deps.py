import asyncpg
from loreweave_authn import bearer_scheme, build_get_current_user

from .config import settings
from .database import get_pool

# P3 (SDK-first) — the platform user-JWT verifier now comes from the shared
# `loreweave_authn` SDK (HS256-pinned, `exp` required, `sub` must parse; uniform
# 401), replacing the inline `jwt.decode(..., algorithms=["HS256"])` this file used
# to hand-roll. `return_subject=True` keeps the prior `-> str` (sub) contract that
# the routers depend on. `bearer_scheme` is re-exported for callers that imported it.
get_current_user = build_get_current_user(lambda: settings.jwt_secret, return_subject=True)

__all__ = ["bearer_scheme", "get_current_user", "get_db"]


async def get_db() -> asyncpg.Pool:
    return get_pool()
