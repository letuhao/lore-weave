from loreweave_authn import build_get_current_user

from .config import settings
from .database import get_pool
import asyncpg

# Platform user JWT verifier (shared SDK). ``return_subject=True`` preserves the
# str return shape callers rely on (routers/grant_deps parse it via ``UUID(...)``).
# HS256-pinned, ``exp`` required, ``sub`` must parse as a UUID — fail-closed 401.
get_current_user = build_get_current_user(
    lambda: settings.jwt_secret, return_subject=True
)


async def get_db() -> asyncpg.Pool:
    return get_pool()
