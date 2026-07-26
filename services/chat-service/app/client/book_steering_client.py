"""HTTP client for book-service's /internal/books/{book_id}/steering endpoint.

RAID C1 (DR-C1) — per-book steering. Graceful degradation is the contract,
mirroring app/client/knowledge_client.py: EVERY failure path (timeout,
transport error, non-200, decode error, unexpected shape) returns ``[]`` and
never raises into the chat turn — steering is an enrichment, so a book-service
outage must leave the turn unaffected.

Same module-level-singleton lifecycle as knowledge_client
(init/close/get_book_steering_client), with an injectable httpx transport for
tests (no monkey-patching httpx.AsyncClient).
"""

import logging

import httpx

from app.config import settings
from app.middleware.trace_id import current_trace_id

logger = logging.getLogger(__name__)

__all__ = [
    "BookSteeringClient",
    "init_book_steering_client",
    "close_book_steering_client",
    "get_book_steering_client",
]

# The fields the selector/renderer needs. Extra keys from a newer book-service
# are tolerated (passed through); entries that aren't dicts are dropped.
_REQUIRED_KEYS = ("name", "body")


class BookSteeringClient:
    """Thin async wrapper around httpx.AsyncClient.

    One instance per chat-service process, shared across requests.
    Close via ``await client.aclose()`` on shutdown.
    """

    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_s: float = 2.0,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        client_kwargs: dict = {
            "timeout": httpx.Timeout(timeout_s),
            "headers": {"X-Internal-Token": internal_token},
        }
        if transport is not None:
            client_kwargs["transport"] = transport
        self._http = httpx.AsyncClient(**client_kwargs)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_steering(self, book_id: str) -> list[dict]:
        """GET /internal/books/{book_id}/steering — the ENABLED entries.

        Returns ``[{id, name, body, inclusion_mode, match_pattern}, ...]`` on
        success, ``[]`` on ANY failure (never raises — the turn proceeds
        steering-free). At most one warning per failed call.
        """
        if not book_id:
            return []
        url = f"{self._base_url}/internal/books/{book_id}/steering"
        tid = current_trace_id()
        headers = {"X-Trace-Id": tid} if tid else None
        try:
            resp = await self._http.get(url, headers=headers)
        except Exception as exc:  # noqa: BLE001 — degrade, don't raise
            logger.warning("get_steering unavailable for book %s: %s", book_id, type(exc).__name__)
            return []
        if resp.status_code != 200:
            logger.warning("get_steering %d for book %s", resp.status_code, book_id)
            return []
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_steering decode failure for book %s: %s", book_id, exc)
            return []
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            logger.warning("get_steering unexpected shape for book %s", book_id)
            return []
        out: list[dict] = []
        for it in items:
            if isinstance(it, dict) and all(isinstance(it.get(k), str) for k in _REQUIRED_KEYS):
                out.append(it)
        return out


# ── module-level singleton managed by lifespan ─────────────────────────────

_client: BookSteeringClient | None = None


def init_book_steering_client() -> BookSteeringClient:
    """Instantiate the shared client from settings. Idempotent — a second call
    without a prior close returns the existing instance (no pool leak)."""
    global _client
    if _client is not None:
        return _client
    _client = BookSteeringClient(
        base_url=settings.book_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.book_steering_timeout_s,
    )
    return _client


async def close_book_steering_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_book_steering_client() -> BookSteeringClient:
    """Lazy accessor — initialises on first use if lifespan didn't."""
    global _client
    if _client is None:
        return init_book_steering_client()
    return _client
