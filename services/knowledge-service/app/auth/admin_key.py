"""KM5 — process-cached RS256 admin key resolver (shared).

Both the `auth=admin` confirm branch (kg_actions) and the `/mcp/admin` transport
gate (mcp/admin_server) need THE configured admin key. Resolve it ONCE here:
parse cost + a misconfig log should not repeat per request, and a parse failure
must log loud + disable admin (return None → callers 503/401) rather than
crash-loop the service. A key rotation requires a restart (matches glossary's
load-at-startup model).
"""

from __future__ import annotations

import logging

from app.auth.admin_jwt import AdminKey, AdminTokenInvalid, load_admin_key
from app.config import settings

logger = logging.getLogger(__name__)

__all__ = ["get_admin_key", "reset_admin_key_cache"]

_cached: AdminKey | None = None
_resolved = False


def get_admin_key() -> AdminKey | None:
    """The configured RS256 admin key, or None when System-tier admin is disabled
    (ADMIN_JWT_PUBLIC_KEY_PEM unset/unparseable)."""
    global _cached, _resolved
    if _resolved:
        return _cached
    try:
        _cached = load_admin_key(settings.admin_jwt_public_key_pem)
    except AdminTokenInvalid as exc:
        logger.error(
            "knowledge: ADMIN_JWT_PUBLIC_KEY_PEM parse failed; System-tier admin DISABLED: %s",
            exc,
        )
        _cached = None
    _resolved = True
    return _cached


def reset_admin_key_cache() -> None:
    """Drop the cached key (tests that flip the configured key between cases)."""
    global _cached, _resolved
    _cached = None
    _resolved = False
