"""C1 DPS-A — read-only clients for knowledge-service + provider-registry.

This module reaches three platform read surfaces. It writes NOTHING to any
store (Q2 LOCKED: enrichment write-back goes through glossary SSOT in C11/C13,
never from here):

  * graph-stats  — GET /v1/knowledge/projects/{project_id}/graph-stats (JWT,
    scoped to the (user, project) pair). EMPTY/zero stats is a VALID result
    (a project with no extraction history) — callers must not treat zeros as
    an error.
  * context      — POST /internal/context/build (internal token). The endpoint
    is POST-shaped per the platform contract but is a pure READ: it assembles
    a context string from already-stored data and persists nothing.
  * embed        — POST /internal/embed on provider-registry (internal token).
    Also a pure read of model output. The embedding model is identified by a
    provider-registry `model_ref` (a `user_model` UUID) supplied by the caller
    — NO model name is ever hardcoded here (Execution LOCKED). C10 owns the
    actual retrieval reuse; C1 only ships the typed client + reachability.

All requests carry typed timeouts and raise a typed `KnowledgeServiceError`
(never a bare httpx error) so the port layer can map failures to graceful
degradation (Q6). Request + response bodies are handled UTF-8/CJK-safe: httpx
encodes JSON as UTF-8 and we never force-ascii, so 封神演义 place names round-trip
without mojibake.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx
from loreweave_internal_client import InternalClientError

__all__ = [
    "GraphStats",
    "BuiltContext",
    "EmbedResult",
    "KnowledgeServiceError",
    "KnowledgeClient",
]


# P3 SDK-first: subclass the shared InternalClientError (`.retryable` derived from
# `.status_code`); name kept so `except KnowledgeServiceError` sites are unchanged.
class KnowledgeServiceError(InternalClientError):
    """Raised on any knowledge-service / provider-registry read failure.

    `retryable` flags transient conditions (timeout, 502/503/429) so the
    port/cache layer can decide whether to degrade to empties (Q6) or retry.
    """


@dataclass(frozen=True)
class GraphStats:
    """Typed shape of the graph-stats read. Counts default to 0 so an empty
    project (no Fengshen data seeded yet) is a first-class valid value."""

    project_id: UUID
    entity_count: int = 0
    fact_count: int = 0
    event_count: int = 0
    passage_count: int = 0
    last_extracted_at: Any = None

    @property
    def is_empty(self) -> bool:
        return (
            self.entity_count == 0
            and self.fact_count == 0
            and self.event_count == 0
            and self.passage_count == 0
        )


@dataclass(frozen=True)
class BuiltContext:
    mode: str = "empty"
    context: str = ""
    token_count: int = 0


@dataclass(frozen=True)
class EmbedResult:
    embeddings: list[list[float]] = field(default_factory=list)
    dimension: int = 0
    model: str = ""
    #: LE-059b — the provider's reported input-token usage (OpenAI/LM Studio
    #: `usage.prompt_tokens`), surfaced by provider-registry. 0 when the provider
    #: omits it (the caller then falls back to a char-estimate for metering).
    prompt_tokens: int = 0


def _bearer(jwt: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt}"}


class KnowledgeClient:
    """Typed async read client for knowledge-service + provider-registry.

    `internal_token` authenticates `/internal/*` calls (context, embed).
    User-scoped reads (graph-stats) require the caller's JWT passed through
    per call so cross-user scoping is enforced by the upstream service.
    """

    def __init__(
        self,
        *,
        knowledge_base_url: str,
        provider_registry_base_url: str,
        internal_token: str,
        timeout_s: float = 10.0,
        embed_timeout_s: float = 30.0,
    ) -> None:
        self._kg_base = knowledge_base_url.rstrip("/")
        self._pr_base = provider_registry_base_url.rstrip("/")
        self._internal_token = internal_token
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s, connect=5.0),
        )
        self._embed_timeout = httpx.Timeout(embed_timeout_s, connect=5.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── graph-stats (JWT, (user, project)-scoped) ───────────────────────────

    async def get_graph_stats(self, *, jwt: str, project_id: UUID) -> GraphStats:
        url = f"{self._kg_base}/v1/knowledge/projects/{project_id}/graph-stats"
        resp = await self._get(url, headers=_bearer(jwt))
        data = resp.json()
        return GraphStats(
            project_id=project_id,
            entity_count=int(data.get("entity_count", 0) or 0),
            fact_count=int(data.get("fact_count", 0) or 0),
            event_count=int(data.get("event_count", 0) or 0),
            passage_count=int(data.get("passage_count", 0) or 0),
            last_extracted_at=data.get("last_extracted_at"),
        )

    # ── context build (internal token, pure read) ───────────────────────────

    async def build_context(
        self,
        *,
        user_id: UUID,
        project_id: UUID | None = None,
        message: str = "",
    ) -> BuiltContext:
        url = f"{self._kg_base}/internal/context/build"
        body: dict[str, Any] = {"user_id": str(user_id), "message": message}
        if project_id is not None:
            body["project_id"] = str(project_id)
        resp = await self._request(
            "POST", url, headers={"X-Internal-Token": self._internal_token}, json=body
        )
        data = resp.json()
        return BuiltContext(
            mode=str(data.get("mode", "empty")),
            context=str(data.get("context", "")),
            token_count=int(data.get("token_count", 0) or 0),
        )

    # ── embed via provider-registry (model_ref, never hardcoded name) ────────

    async def embed(
        self,
        *,
        user_id: UUID,
        model_source: str,
        model_ref: str,
        texts: list[str],
    ) -> EmbedResult:
        """Resolve an embedding via provider-registry. `model_ref` identifies a
        registered user_model (UUID) — the embedding model name is NEVER baked
        into this code (Execution LOCKED)."""
        url = f"{self._pr_base}/internal/embed"
        body = {"model_source": model_source, "model_ref": model_ref, "texts": texts}
        params = {"user_id": str(user_id)}
        resp = await self._request(
            "POST",
            url,
            headers={"X-Internal-Token": self._internal_token},
            json=body,
            params=params,
            timeout=self._embed_timeout,
        )
        data = resp.json()
        return EmbedResult(
            embeddings=data.get("embeddings", []),
            dimension=int(data.get("dimension", 0) or 0),
            model=str(data.get("model", "")),
            prompt_tokens=int(data.get("prompt_tokens", 0) or 0),
        )

    # ── transport helpers (typed errors only) ───────────────────────────────

    async def _get(self, url: str, *, headers: dict[str, str]) -> httpx.Response:
        return await self._request("GET", url, headers=headers)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: Any = None,
        params: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> httpx.Response:
        # httpx's `json=` uses stdlib json.dumps(ensure_ascii=True), which
        # escapes CJK to \uXXXX. The bytes are still valid, but we serialize
        # ourselves with ensure_ascii=False so 封神演义 names travel as genuine
        # UTF-8 on the wire (M4: no ASCII-escape surprise for downstreams).
        content: bytes | None = None
        send_headers = dict(headers)
        if json is not None:
            content = _json.dumps(json, ensure_ascii=False).encode("utf-8")
            send_headers["Content-Type"] = "application/json; charset=utf-8"
        try:
            resp = await self._http.request(
                method, url, headers=send_headers, content=content, params=params, timeout=timeout
            )
        except httpx.TimeoutException as exc:
            raise KnowledgeServiceError(f"timeout calling {url}: {exc}", retryable=True)
        except httpx.HTTPError as exc:
            raise KnowledgeServiceError(f"connection error calling {url}: {exc}", retryable=True)

        if resp.status_code == 200:
            return resp

        detail = resp.text[:200]
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            pass
        raise KnowledgeServiceError(
            f"{method} {url} failed ({resp.status_code}): {detail}",
            status_code=resp.status_code,
        )
