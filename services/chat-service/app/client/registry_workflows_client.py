"""HTTP client for agent-registry-service's /internal/workflows endpoint (WS-2b).

Fetches the user's + book's + System curated WORKFLOWS so the chat-service
step-runner can list them (workflow_list) and load one's ordered steps
(workflow_load). Graceful degradation is the contract (mirrors
user_skills_client): EVERY failure path returns an EMPTY result and never raises
into the chat turn — workflows are an enrichment, so a registry outage leaves the
turn with no curated workflows (the agent still has raw tools + discovery).

Response shape from /internal/workflows:
  {
    "catalog_version": <int>,
    "workflows": [{slug, title, description, tier, surfaces, inputs, steps, notes_md}, ...]
  }
where each step is {id, tool, gate, when?, repeat?, inputs_map?}.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from app.config import settings
from app.middleware.trace_id import current_trace_id

logger = logging.getLogger(__name__)

__all__ = [
    "ModeBinding",
    "Workflows",
    "WorkflowsClient",
    "init_workflows_client",
    "close_workflows_client",
    "get_workflows_client",
]


@dataclass(frozen=True)
class ModeBinding:
    """WS-3 (C6) — the resolved mode → capability binding for this turn.

    ``inject_workflows`` are PINNED: their rail is rendered into the prompt and their
    step tools pre-activated, so the agent never has to *recognise* that a workflow
    applies (the S06 assent gap). Empty everywhere = no binding = pre-WS-3 behavior.
    """

    mode: str = ""
    inject_skills: list[str] = field(default_factory=list)
    inject_workflows: list[str] = field(default_factory=list)
    seed_tool_categories: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.inject_skills or self.inject_workflows or self.seed_tool_categories)


@dataclass(frozen=True)
class Workflows:
    """Resolved workflows for one turn. Empty = no curated workflows (fallback)."""

    workflows: list[dict] = field(default_factory=list)
    mode_binding: ModeBinding | None = None

    def by_slug(self, slug: str) -> dict | None:
        for wf in self.workflows:
            if wf.get("slug") == slug:
                return wf
        return None


def _str_list(v: object) -> list[str]:
    """Keep only non-blank strings — a malformed registry row can never inject a
    non-string into the prompt/seed path."""
    if not isinstance(v, list):
        return []
    return [s.strip() for s in v if isinstance(s, str) and s.strip()]


def _parse_mode_binding(data: dict) -> ModeBinding | None:
    raw = data.get("mode_binding")
    if not isinstance(raw, dict):
        return None
    mb = ModeBinding(
        mode=str(raw.get("mode") or ""),
        inject_skills=_str_list(raw.get("inject_skills")),
        inject_workflows=_str_list(raw.get("inject_workflows")),
        seed_tool_categories=_str_list(raw.get("seed_tool_categories")),
    )
    return None if mb.is_empty() else mb


_EMPTY = Workflows()


class WorkflowsClient:
    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_s: float = 2.0,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        kwargs: dict = {
            "timeout": httpx.Timeout(timeout_s),
            "headers": {"X-Internal-Token": internal_token},
        }
        if transport is not None:
            kwargs["transport"] = transport
        self._http = httpx.AsyncClient(**kwargs)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_workflows(
        self, user_id: str, *, book_id: str = "", surface: str = "", mode: str = "",
    ) -> Workflows:
        """GET /internal/workflows — returns Workflows on success, _EMPTY on ANY failure.

        ``mode`` (WS-3/C6) rides the SAME fetch: the registry resolves the mode→capability
        binding server-side and returns it alongside. One hop, one degrade path — a
        registry outage yields _EMPTY, i.e. no workflows AND no binding, which is exactly
        the pre-WS-3 behavior.
        """
        if not user_id:
            return _EMPTY
        params = {"user_id": user_id}
        if book_id:
            params["book_id"] = book_id
        if surface:
            params["surface"] = surface
        if mode:
            params["mode"] = mode
        tid = current_trace_id()
        headers = {"X-Trace-Id": tid} if tid else None
        try:
            resp = await self._http.get(f"{self._base_url}/internal/workflows", params=params, headers=headers)
        except Exception as exc:  # noqa: BLE001 — degrade, don't raise
            logger.warning("workflows unavailable (fallback to none): %s", type(exc).__name__)
            return _EMPTY
        if resp.status_code != 200:
            logger.warning("workflows %d (fallback to none)", resp.status_code)
            return _EMPTY
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("workflows decode failure: %s", exc)
            return _EMPTY
        if not isinstance(data, dict):
            return _EMPTY
        wfs = data.get("workflows")
        if not isinstance(wfs, list):
            wfs = []
        # keep only well-formed workflow dicts (a NON-EMPTY slug + a list of steps). An
        # empty-slug row would count toward has_workflows yet never list — drop it here.
        clean = [
            wf for wf in wfs
            if isinstance(wf, dict) and wf.get("slug") and isinstance(wf.get("slug"), str)
            and isinstance(wf.get("steps"), list)
        ]
        return Workflows(workflows=clean, mode_binding=_parse_mode_binding(data))


_client: WorkflowsClient | None = None


def init_workflows_client() -> WorkflowsClient:
    global _client
    if _client is not None:
        return _client
    _client = WorkflowsClient(
        base_url=settings.agent_registry_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.agent_registry_timeout_s,
    )
    return _client


async def close_workflows_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_workflows_client() -> WorkflowsClient:
    global _client
    if _client is None:
        return init_workflows_client()
    return _client
