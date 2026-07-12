"""Agent surface SSE state machine (story 04 / #07b).

Emits only on phase transitions; payload is the frozen CUSTOM agentSurface contract.

W6 (tool/skill loading visibility) — the payload additionally carries the
ADVERTISED surface of the last provider pass (``advertised``: core / frontend /
activated name lists), a per-MCP-server grouping (``servers``: server_key →
{tools: N}) and the W1-measured schema token split (``schema_tokens``:
{frontend, mcp}). Strictly ADDITIVE: the original eight fields keep their
values, order and semantics — an older consumer keeps working unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from app.db.conversation_search import CONVERSATION_SEARCH_NAME
from app.db.session_search import CHAT_SEARCH_SESSIONS_NAME
from app.services.frontend_tools import FRONTEND_TOOL_NAMES
from app.services.tool_discovery import FIND_TOOLS_NAME


PHASES = (
    "Idle",
    "Curated",
    "SkillInjected",
    "Discovering",
    "Activated",
    "ToolRunning",
)


# ── W6: tool-name prefix → owning MCP server key ─────────────────────────────
# Mirrors the ai-gateway federation registry (services/ai-gateway/src/config/
# config.ts DEFAULT_PREFIX_MAP + EXTRA_PREFIX_MAP): knowledge serves BOTH
# `memory_*` and `kg_*`; composition serves `composition_*` AND the PlanForge
# `plan_*` tools; every other domain owns its own prefix. Adding a federated
# provider → add its prefix row here (unknown prefixes group under "other").
_SERVER_KEY_BY_PREFIX: dict[str, str] = {
    "memory": "knowledge",
    "kg": "knowledge",
    "knowledge": "knowledge",
    "glossary": "glossary",
    "book": "book",
    "composition": "composition",
    "plan": "composition",
    "translation": "translation",
    "jobs": "jobs",
}

# Frontend (browser-executed) tools group under "ui"; the consumer-local
# find_tools meta-tool (never federated) under "chat".
SERVER_KEY_UI = "ui"
SERVER_KEY_CHAT = "chat"
SERVER_KEY_OTHER = "other"


def server_key_for_tool(name: str) -> str:
    """The MCP-server grouping key for a tool name.

    Precedence matters: frontend tools are checked BEFORE the prefix map —
    ``glossary_confirm_action`` / ``glossary_propose_entity_edit`` are
    browser-executed frontend tools despite their ``glossary_`` prefix."""
    if not name:
        return SERVER_KEY_OTHER
    # Consumer-local, chat-native (never federated): the find_tools meta-tool, the
    # conversation_search recovery tool, and chat_search_sessions recall group under "chat".
    if name in (FIND_TOOLS_NAME, CONVERSATION_SEARCH_NAME, CHAT_SEARCH_SESSIONS_NAME):
        return SERVER_KEY_CHAT
    if name in FRONTEND_TOOL_NAMES:
        return SERVER_KEY_UI
    prefix = name.split("_", 1)[0] if "_" in name else ""
    return _SERVER_KEY_BY_PREFIX.get(prefix, SERVER_KEY_OTHER)


def servers_for_names(names: Iterable[str]) -> dict[str, dict[str, int]]:
    """Group tool names by owning server: ``{server_key: {"tools": N}}``."""
    out: dict[str, dict[str, int]] = {}
    for name in names:
        key = server_key_for_tool(name)
        slot = out.setdefault(key, {"tools": 0})
        slot["tools"] += 1
    return out


def _empty_advertised() -> dict[str, list[str]]:
    return {"core": [], "frontend": [], "activated": []}


def _empty_schema_tokens() -> dict[str, int]:
    return {"frontend": 0, "mcp": 0}


@dataclass
class AgentSurfaceTracker:
    """Tracks inspector phase + counters for one chat turn."""

    phase: str = "Idle"
    pinned_count: int = 0
    hot_seed_count: int = 0
    activated_count: int = 0
    injected_skills: list[str] = field(default_factory=list)
    running_tool: str | None = None
    last_find_tools_query: str | None = None
    find_tools_call_count: int = 0
    # W6 — the advertised surface of the last provider pass (ADDITIVE fields).
    advertised: dict[str, list[str]] = field(default_factory=_empty_advertised)
    servers: dict[str, dict[str, int]] = field(default_factory=dict)
    schema_tokens: dict[str, int] = field(default_factory=_empty_schema_tokens)

    def payload(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "pinned_count": self.pinned_count,
            "hot_seed_count": self.hot_seed_count,
            "activated_count": self.activated_count,
            "injected_skills": list(self.injected_skills),
            "running_tool": self.running_tool,
            "last_find_tools_query": self.last_find_tools_query,
            "find_tools_call_count": self.find_tools_call_count,
            # W6 additive — advertised surface + per-server grouping + W1 token split.
            "advertised": {k: list(v) for k, v in self.advertised.items()},
            "servers": {k: dict(v) for k, v in self.servers.items()},
            "schema_tokens": dict(self.schema_tokens),
        }

    def _transition(self, phase: str, **updates: Any) -> dict[str, Any] | None:
        if phase == self.phase and not updates:
            return None
        self.phase = phase
        for k, v in updates.items():
            setattr(self, k, v)
        return self.payload()

    def curated(
        self,
        *,
        pinned_count: int,
        hot_seed_count: int,
        activated_count: int,
    ) -> dict[str, Any] | None:
        return self._transition(
            "Curated",
            pinned_count=pinned_count,
            hot_seed_count=hot_seed_count,
            activated_count=activated_count,
            running_tool=None,
        )

    def skill_injected(self, skills: list[str]) -> dict[str, Any] | None:
        return self._transition("SkillInjected", injected_skills=skills, running_tool=None)

    def discovering(self, query: str) -> dict[str, Any] | None:
        self.find_tools_call_count += 1
        return self._transition(
            "Discovering",
            last_find_tools_query=query,
            running_tool=None,
        )

    def activated(self, activated_count: int) -> dict[str, Any] | None:
        return self._transition(
            "Activated",
            activated_count=activated_count,
            running_tool=None,
        )

    def tool_running(self, tool_name: str) -> dict[str, Any] | None:
        return self._transition("ToolRunning", running_tool=tool_name)

    def advertised_pass(
        self,
        *,
        core: Iterable[str],
        frontend: Iterable[str],
        activated: Iterable[str],
        schema_tokens: dict[str, int] | None = None,
    ) -> dict[str, Any] | None:
        """W6 — record the surface ADVERTISED to the provider on this pass.

        Not a phase transition: the phase is untouched. Returns the payload
        only when something actually changed (first pass, or a later pass
        after discovery grew the active set) so the SSE stream stays quiet
        on repeat passes. ``schema_tokens`` is the W1 measurement — taken
        once per turn — passed only on the pass that measured it (None keeps
        the stored split)."""
        new_advertised = {
            "core": sorted(core),
            "frontend": sorted(frontend),
            "activated": sorted(activated),
        }
        all_names = (
            new_advertised["core"]
            + new_advertised["frontend"]
            + new_advertised["activated"]
        )
        new_servers = servers_for_names(all_names)
        changed = False
        if new_advertised != self.advertised:
            self.advertised = new_advertised
            changed = True
        if new_servers != self.servers:
            self.servers = new_servers
            changed = True
        if schema_tokens is not None:
            new_split = {
                "frontend": int(schema_tokens.get("frontend", 0)),
                "mcp": int(schema_tokens.get("mcp", 0)),
            }
            if new_split != self.schema_tokens:
                self.schema_tokens = new_split
                changed = True
        return self.payload() if changed else None

    def idle(self) -> dict[str, Any] | None:
        return self._transition("Idle", running_tool=None)
