"""C1 DPS-C — KnowledgeReadPort: the graceful-degradation seam (Q6 LOCKED).

The enrichment engine (C6+) reads platform state ONLY through this port, so it
never couples to httpx, base URLs, or the down/up state of knowledge-service.
Three implementations:

  * KnowledgeReadHttp   — wraps the real KnowledgeClient; on a typed client
    error it DEGRADES to typed empties rather than propagating, so a down KG
    can never crash enrichment (Q6). Empty data (zero graph-stats) is returned
    as-is — that is a valid state, not a failure.
  * NullKnowledgeRead   — always returns typed empties; used when the platform
    dependency is intentionally absent (local dev, tests, feature-flag off).
    It NEVER raises and NEVER returns None.
  * CachedKnowledgeRead — TTL wrapper over any port for hot graph-stats reads;
    caches per (jwt-hash, project_id) for `ttl_s` seconds.

Q2 LOCKED: this is a READ port only. There is no write method anywhere.
"""

from __future__ import annotations

import hashlib
import time
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.clients.knowledge import (
    BuiltContext,
    GraphStats,
    KnowledgeClient,
    KnowledgeServiceError,
)

__all__ = [
    "KnowledgeReadPort",
    "KnowledgeReadHttp",
    "NullKnowledgeRead",
    "CachedKnowledgeRead",
]


@runtime_checkable
class KnowledgeReadPort(Protocol):
    """Read-only seam over knowledge-service. All methods return typed values
    and MUST NOT raise on a downstream outage (impls degrade to empties)."""

    async def get_graph_stats(self, *, jwt: str, project_id: UUID) -> GraphStats: ...

    async def build_context(
        self, *, user_id: UUID, project_id: UUID | None = ..., message: str = ...
    ) -> BuiltContext: ...


class KnowledgeReadHttp:
    """Real port: delegates to KnowledgeClient, degrading to typed empties on a
    typed client error (Q6). Does not swallow programming errors — only the
    client's own `KnowledgeServiceError` is treated as a degradation signal."""

    def __init__(self, client: KnowledgeClient) -> None:
        self._client = client

    async def get_graph_stats(self, *, jwt: str, project_id: UUID) -> GraphStats:
        try:
            return await self._client.get_graph_stats(jwt=jwt, project_id=project_id)
        except KnowledgeServiceError:
            return GraphStats(project_id=project_id)

    async def build_context(
        self, *, user_id: UUID, project_id: UUID | None = None, message: str = ""
    ) -> BuiltContext:
        try:
            return await self._client.build_context(
                user_id=user_id, project_id=project_id, message=message
            )
        except KnowledgeServiceError:
            return BuiltContext()


class NullKnowledgeRead:
    """Degradation impl: typed empties, always. Never raises, never None."""

    async def get_graph_stats(self, *, jwt: str, project_id: UUID) -> GraphStats:
        return GraphStats(project_id=project_id)

    async def build_context(
        self, *, user_id: UUID, project_id: UUID | None = None, message: str = ""
    ) -> BuiltContext:
        return BuiltContext()


class CachedKnowledgeRead:
    """TTL cache wrapper for hot graph-stats reads. Delegates non-cached calls
    straight through. JWT is hashed (never stored raw) for the cache key."""

    def __init__(self, inner: KnowledgeReadPort, *, ttl_s: float = 30.0) -> None:
        self._inner = inner
        self._ttl = ttl_s
        self._cache: dict[tuple[str, str], tuple[float, GraphStats]] = {}

    async def get_graph_stats(self, *, jwt: str, project_id: UUID) -> GraphStats:
        key = (hashlib.sha256(jwt.encode("utf-8")).hexdigest(), str(project_id))
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit is not None and (now - hit[0]) < self._ttl:
            return hit[1]
        stats = await self._inner.get_graph_stats(jwt=jwt, project_id=project_id)
        self._cache[key] = (now, stats)
        return stats

    async def build_context(
        self, *, user_id: UUID, project_id: UUID | None = None, message: str = ""
    ) -> BuiltContext:
        return await self._inner.build_context(
            user_id=user_id, project_id=project_id, message=message
        )
