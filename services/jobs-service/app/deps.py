"""Auth + DB dependencies.

The owner-scoped read API VERIFIES the JWT signature (HS256 with the shared
`JWT_SECRET`) — owner scoping is a security boundary (the spec forbids any
cross-tenant job leak in list/detail/stream), so a blind/unverified decode is
NOT acceptable here. Mirrors campaign-service `deps.py`.
"""

import asyncpg
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .database import get_pool

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    """Resolve the acting user from a signature-verified bearer JWT. Returns the
    `sub` claim (the owner_user_id every job query filters on)."""
    token = credentials.credentials
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    sub = data.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing sub")
    return str(sub)


async def get_db() -> asyncpg.Pool:
    return get_pool()
