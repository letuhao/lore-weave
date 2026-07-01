"""Agent surface SSE state machine (story 04 / #07b).

Emits only on phase transitions; payload is the frozen CUSTOM agentSurface contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PHASES = (
    "Idle",
    "Curated",
    "SkillInjected",
    "Discovering",
    "Activated",
    "ToolRunning",
)


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

    def idle(self) -> dict[str, Any] | None:
        return self._transition("Idle", running_tool=None)
