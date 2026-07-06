"""Web-search client for provider-registry (composition-service, D-W9-WEBSEARCH).

W9's import/deconstruct can OPTIONALLY anchor its arc segmentation on well-known
PUBLIC arc conventions for a reference work (the ``use_web`` flag). The outward
web-search HTTP call lives ONLY in provider-registry (provider-gateway invariant) —
exactly like ``embedding_client`` reaches ``/internal/embed``: composition hits
``POST /internal/web-search?user_id=`` with ``X-Internal-Token``; provider-registry
resolves the user's BYOK ``web_search`` model + key and runs the query. Composition
never holds a search key, never imports a search SDK, never hardcodes a model.

INV-6 (untrusted external text): every returned title/url/snippet is UNTRUSTED web
DATA. The client neutralizes it (collapse control chars, cap length, drop
non-http(s) URLs) so a search result can never smuggle instructions into the
deconstruct prompt or a non-http scheme to a downstream consumer.

Graceful degradation (mirrors the other composition clients): a missing
``web_search`` credential (404) returns ``not_configured`` and any transport / non-200
returns ``None`` for ``error`` — the deconstruct then proceeds WITHOUT web augment
(``websearch_status: 'not_configured' | 'unavailable'``) rather than failing the job.
A web outage must never 500 an import.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from uuid import UUID

import httpx
from loreweave_internal_client import build_internal_client

from app.config import settings
from app.logging_config import trace_id_var

__all__ = [
    "WebSearchClient",
    "WebSearchHit",
    "WebSearchResult",
    "init_web_search_client",
    "get_web_search_client",
    "close_web_search_client",
]

logger = logging.getLogger(__name__)

# INV-6 neutralization caps (mirror glossary_web_search's title/snippet/answer caps).
_TITLE_CAP = 200
_SNIPPET_CAP = 600
_ANSWER_CAP = 1200
_QUERY_CAP = 500
# Collapse any run of control/whitespace (incl. newlines that could fake a chat turn)
# into a single space — an untrusted snippet must read as ONE inert line of DATA.
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]+|\s+")
_HTTP_RE = re.compile(r"^https?://", re.IGNORECASE)


def _neutralize(text: str | None, cap: int) -> str:
    """Collapse control chars / whitespace and hard-cap — an untrusted web string
    becomes one inert single-line fragment of bounded length."""
    if not text:
        return ""
    return _CTRL_RE.sub(" ", str(text)).strip()[:cap]


def _safe_http_url(url: str | None) -> str:
    """Keep ONLY http(s) URLs (drop javascript:/data:/file: etc.); else ''."""
    u = (url or "").strip()
    return u[:500] if _HTTP_RE.match(u) else ""


@dataclass(frozen=True)
class WebSearchHit:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class WebSearchResult:
    """A completed search. ``error`` is set (and ``hits`` empty) for the degrade
    states — the caller branches on it for an honest ``websearch_status``.

    error values: ``None`` (ok) · ``'not_configured'`` (no BYOK web_search model) ·
    ``'unavailable'`` (transport/non-200/bad-JSON outage)."""

    answer: str = ""
    hits: list[WebSearchHit] = field(default_factory=list)
    error: str | None = None


class WebSearchClient:
    def __init__(
        self, base_url: str, internal_token: str, timeout_s: float = 20.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # Advanced web search fetches pages — a longer timeout than the 5s read
        # clients, still bounded (mirrors glossary's 20s). W3: shared factory bakes
        # X-Internal-Token + JSON + per-request X-Trace-Id.
        self._http = build_internal_client(
            base_url, internal_token=internal_token,
            timeout_s=timeout_s, connect_timeout_s=5.0,
            trace_id_provider=trace_id_var.get,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def search(
        self, *, user_id: UUID, query: str, max_results: int = 5,
    ) -> WebSearchResult:
        """Run ONE BYOK web search for ``user_id`` via provider-registry. Returns a
        neutralized ``WebSearchResult`` — NEVER raises; degrades to an ``error``
        state so a deconstruct keeps going without the augment."""
        q = (query or "").strip()[:_QUERY_CAP]
        if not q:
            return WebSearchResult(error="unavailable")
        n = max(1, min(int(max_results or 5), 10))
        url = f"{self._base_url}/internal/web-search"
        try:
            resp = await self._http.post(
                url, json={"query": q, "max_results": n},
                params={"user_id": str(user_id)},
            )
        except httpx.HTTPError as exc:
            logger.warning("web-search unreachable: %s", exc)
            return WebSearchResult(error="unavailable")

        # 404 = the user has no web_search credential — actionable, not an outage.
        if resp.status_code == 404:
            return WebSearchResult(error="not_configured")
        if resp.status_code != 200:
            logger.warning("web-search → %d", resp.status_code)
            return WebSearchResult(error="unavailable")
        try:
            data = resp.json()
        except (ValueError, AttributeError) as exc:
            logger.warning("web-search bad JSON: %s", exc)
            return WebSearchResult(error="unavailable")

        raw = data.get("results") if isinstance(data, dict) else None
        hits: list[WebSearchHit] = []
        for r in raw or []:
            if not isinstance(r, dict):
                continue
            safe_url = _safe_http_url(r.get("url"))
            if not safe_url:
                continue  # drop non-http(s) — no javascript:/data: to the prompt.
            hits.append(WebSearchHit(
                title=_neutralize(r.get("title"), _TITLE_CAP),
                url=safe_url,
                snippet=_neutralize(r.get("content"), _SNIPPET_CAP),
            ))
        return WebSearchResult(
            answer=_neutralize(data.get("answer") if isinstance(data, dict) else "", _ANSWER_CAP),
            hits=hits,
            error=None,
        )


# ── Module-level singleton (mirrors embedding_client) ────────────────────────────────
_client: WebSearchClient | None = None


def init_web_search_client() -> WebSearchClient:
    global _client
    if _client is None:
        _client = WebSearchClient(
            base_url=settings.llm_gateway_internal_url,
            internal_token=settings.internal_service_token,
        )
    return _client


def get_web_search_client() -> WebSearchClient:
    return _client or init_web_search_client()


async def close_web_search_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
