"""FastAPI dependency shims for the platform user JWT.

Mirrors the shape chat-service (``app/middleware/auth.py``) and composition-service
(``app/middleware/jwt_auth.py``) already hand-roll, so migrating a service is a
thin swap: delete the inline ``jwt.decode`` block and bind the factory to the
service's own secret source.

Example migration (composition-service)::

    from loreweave_authn import build_get_current_user, get_bearer_token
    from app.config import settings

    get_current_user = build_get_current_user(lambda: settings.jwt_secret)
    get_optional_current_user = build_get_current_user(
        lambda: settings.jwt_secret, optional=True
    )
    # get_bearer_token is secret-free — import it directly.

``HTTPBearer(auto_error=False)`` is used so THIS module owns the 401 path
uniformly (FastAPI's default auto-raise returns 403 for missing creds, which the
inline verifiers deliberately avoided).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ._verify import InvalidAccessToken, verify_access_token

__all__ = [
    "bearer_scheme",
    "build_get_current_user",
    "get_bearer_token",
    "get_current_user",
    "get_optional_current_user",
]

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def build_get_current_user(
    secret_provider: Callable[[], str],
    *,
    optional: bool = False,
    return_subject: bool = False,
) -> Callable[..., object]:
    """Build a FastAPI dependency that authenticates the Bearer user JWT.

    Args:
        secret_provider: called per-request to obtain the shared HS256 secret
            (e.g. ``lambda: settings.jwt_secret``). Called lazily so a
            hot-reloaded / rotated secret is picked up without re-import.
        optional: when True the dependency returns ``None`` instead of raising
            for a missing OR invalid token — the pattern used by routes that
            accept EITHER a user JWT OR an internal-token service envelope.
            Identity is still taken ONLY from a VALID ``sub``.
        return_subject: when True the dependency returns the ``sub`` string
            (chat-service's shape); default returns the ``UUID``
            (composition/knowledge's shape).

    Returns:
        A FastAPI dependency callable returning ``UUID`` | ``str`` | ``None``.
    """

    def _dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ):
        if credentials is None:
            if optional:
                return None
            raise _unauthorized("missing bearer token")
        try:
            claims = verify_access_token(credentials.credentials, secret_provider())
        except InvalidAccessToken:
            if optional:
                return None
            raise _unauthorized("invalid token")
        return claims.subject if return_subject else claims.user_id

    return _dependency


def get_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """Return the raw JWT string for FORWARDING to a downstream service.

    Secret-free (does not verify) — use alongside a ``build_get_current_user``
    dependency that authorizes locally, when the endpoint also proxies to a
    downstream service that does its own JWT ownership check. Raises 401 when no
    Bearer credential is present.
    """
    if credentials is None:
        raise _unauthorized("missing bearer token")
    return credentials.credentials


def _env_secret() -> str:
    return os.environ.get("JWT_SECRET", "")


# Convenience dependencies bound to the JWT_SECRET env var — usable directly by a
# service whose secret is exposed as JWT_SECRET, or as a reference for wiring the
# factory to a settings object.
get_current_user = build_get_current_user(_env_secret)
get_optional_current_user = build_get_current_user(_env_secret, optional=True)
