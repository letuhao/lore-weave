"""WS-4C Half A — client for glossary's canon-capture route.

`POST /internal/books/{book_id}/capture-canon` — the ONLY write chat-service makes into the
glossary. Spec: docs/specs/2026-07-10-ws4c-half-a-canon-auto-capture.md

Graceful degradation is the contract (mirrors known_entities_client): EVERY failure returns
``None`` and never raises into the caller. Capture runs after the turn has finished
streaming; a glossary outage must cost the user nothing but a missed capture, which the next
cadence tick retries.

`owner_user_id` is sent so glossary can grant-check (Edit) the write. Holding the internal
token does NOT authorize a write into an arbitrary book — that check is glossary's, and this
client's job is simply to name the user honestly.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.middleware.trace_id import current_trace_id

logger = logging.getLogger(__name__)

__all__ = [
    "CanonCaptureClient",
    "init_canon_capture_client",
    "close_canon_capture_client",
    "get_canon_capture_client",
]


def _error_code(resp: httpx.Response) -> str | None:
    """glossary's error envelope is ``{"code": ..., "message": ...}``. Return the code, or
    None when the body is missing/undecodable — a diagnostic read must never raise into a
    caller whose whole contract is "never raise"."""
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return None
    return body.get("code") if isinstance(body, dict) else None


class CanonCaptureClient:
    """Thin async wrapper. One instance per process. No cache — every capture is a distinct
    turn, and the result is a write receipt, not a lookup."""

    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_s: float = 90.0,
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

    async def capture(
        self,
        *,
        book_id: str,
        owner_user_id: str,
        source_text: str,
        model_ref: str | None = None,
    ) -> dict[str, Any] | None:
        """Capture the exchange's new entities into the book's review inbox.

        Returns the response dict, or ``None`` on ANY failure (never raises).
        """
        if not book_id or not owner_user_id or not source_text.strip():
            return None
        url = f"{self._base_url}/internal/books/{book_id}/capture-canon"
        payload: dict[str, Any] = {"owner_user_id": owner_user_id, "source_text": source_text}
        if model_ref:
            payload["model_ref"] = model_ref
        tid = current_trace_id()
        headers = {"X-Trace-Id": tid} if tid else None
        try:
            resp = await self._http.post(url, json=payload, headers=headers)
        except Exception as exc:  # noqa: BLE001 — degrade, never raise into the turn
            logger.warning("canon capture unavailable for book %s: %s", book_id, type(exc).__name__)
            return None
        if resp.status_code == 409:
            # 409 is NOT one condition. glossary returns it for GLOSS_NO_KINDS (the book has
            # no ontology, so capture can never succeed until the user sets one up) AND for
            # GLOSS_BOOK_INVALID_LIFECYCLE (the book is trashed / purge-pending — the grant
            # guard). Branch on the CODE: attributing a trashed book to "no entity kinds"
            # sends the reader to fix the wrong thing.
            code = _error_code(resp)
            if code == "GLOSS_BOOK_INVALID_LIFECYCLE":
                logger.info("canon capture skipped for book %s: book is not in an editable state", book_id)
            elif code == "GLOSS_NO_KINDS":
                logger.info("canon capture skipped for book %s: book has no entity kinds yet", book_id)
            else:
                logger.warning("canon capture conflict for book %s: %s", book_id, code or "unknown")
            return None
        if resp.status_code == 403:
            # The session's user has no Edit grant on the book its project points at. Not a
            # bug in capture — a data/config issue worth surfacing once per turn, loudly
            # enough to notice, quietly enough not to page.
            logger.warning("canon capture denied for book %s (no edit grant)", book_id)
            return None
        if resp.status_code != 200:
            logger.warning("canon capture %d for book %s", resp.status_code, book_id)
            return None
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("canon capture decode failure for book %s: %s", book_id, exc)
            return None
        if not isinstance(data, dict):
            logger.warning("canon capture unexpected shape for book %s", book_id)
            return None
        return data


# ── module-level singleton managed by lifespan ─────────────────────────────

_client: CanonCaptureClient | None = None


def init_canon_capture_client() -> CanonCaptureClient:
    """Instantiate the shared client from settings. Idempotent."""
    global _client
    if _client is not None:
        return _client
    _client = CanonCaptureClient(
        base_url=settings.glossary_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.canon_capture_timeout_s,
    )
    return _client


async def close_canon_capture_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_canon_capture_client() -> CanonCaptureClient:
    """Lazy accessor — initialises on first use if lifespan didn't."""
    global _client
    if _client is None:
        return init_canon_capture_client()
    return _client
