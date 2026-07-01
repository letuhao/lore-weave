"""Tests for tool_surface (story 04)."""
from __future__ import annotations

from app.services.tool_surface import (
    assemble_initial_active_names,
    effective_enabled_tools,
    is_curated,
    merge_activated_tools,
)


def _tool(name: str) -> dict:
    return {"type": "function", "function": {"name": name, "description": name}}


class TestToolSurface:
    def test_is_curated(self):
        assert not is_curated([])
        assert is_curated(["book_get_chapter"])

    def test_assemble_auto_mode_uses_hot_seed(self):
        hot = {"glossary_search", "glossary_list"}
        out = assemble_initial_active_names(
            curated=False,
            enabled_tools=[],
            activated_tools=[],
            hot_seed_names=hot,
        )
        assert out == hot

    def test_assemble_curated_uses_pins_and_activated(self):
        out = assemble_initial_active_names(
            curated=True,
            enabled_tools=["book_get_chapter"],
            activated_tools=["translation_start"],
            hot_seed_names={"glossary_search"},
        )
        assert out == {"book_get_chapter", "translation_start"}

    def test_glossary_skill_unions_hot_glossary_tools(self):
        catalog = [_tool("glossary_search"), _tool("book_get_chapter")]
        pins = effective_enabled_tools(
            ["book_get_chapter"],
            glossary_skill=True,
            catalog=catalog,
            hot_domains={"glossary"},
        )
        assert "glossary_search" in pins
        assert "book_get_chapter" in pins

    def test_merge_activated_tools_caps(self):
        from app.services.tool_surface import ACTIVATED_TOOLS_CAP
        base = [f"t{i}" for i in range(ACTIVATED_TOOLS_CAP)]
        merged = merge_activated_tools(base, {"new_tool"})
        assert len(merged) == ACTIVATED_TOOLS_CAP
        assert merged[-1] == "new_tool"

    def test_discovery_seed_curated_ignores_hot_tail(self):
        from app.services.tool_surface import (
            SessionToolPins,
            discovery_seed_for_surface,
        )
        catalog = [
            _tool("book_get_chapter"),
            _tool("glossary_search"),
            _tool("translation_start_job"),
        ]
        pins = SessionToolPins(
            effective_enabled=["book_get_chapter"],
            effective_skills=[],
            curated_mode=True,
            activation_state={"activated_tools": [], "dirty": False},
        )
        seed = discovery_seed_for_surface(
            catalog, pins=pins, editor=False, book_scoped=False,
        )
        assert seed == {"book_get_chapter"}
