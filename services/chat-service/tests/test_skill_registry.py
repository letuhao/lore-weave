"""Tests for skill_registry (story 04)."""
from __future__ import annotations

from app.services.skill_registry import resolve_skills_to_inject, catalog_items, skill_prompts


class TestResolveSkillsToInject:
    def test_empty_skills_universal_chat_surface(self):
        codes = resolve_skills_to_inject(
            enabled_skills=[],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=False,
            book_scoped=False,
            admin=False,
        )
        assert codes == ["universal", "knowledge"]

    def test_empty_skills_book_surface(self):
        codes = resolve_skills_to_inject(
            enabled_skills=[],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=False,
            book_scoped=True,
            admin=False,
        )
        assert codes == ["glossary", "knowledge"]

    def test_curated_glossary_only(self):
        codes = resolve_skills_to_inject(
            enabled_skills=["glossary"],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=False,
            book_scoped=True,
            admin=False,
        )
        assert codes == ["glossary"]

    def test_disable_tools_returns_empty(self):
        assert resolve_skills_to_inject(
            enabled_skills=["glossary"],
            stream_format="agui",
            disable_tools=True,
            tool_calling_enabled=True,
            editor=True,
            book_scoped=True,
            admin=False,
        ) == []


class TestSkillCatalog:
    def test_catalog_has_system_skills(self):
        ids = {row["id"] for row in catalog_items()}
        assert "glossary" in ids
        assert "universal" in ids
        assert "admin" not in ids


class TestPlanForgeSkill:
    def test_plan_forge_in_catalog(self):
        ids = {row["id"] for row in catalog_items()}
        assert "plan_forge" in ids

    def test_plan_forge_resolves_when_pinned_on_book_surface(self):
        codes = resolve_skills_to_inject(
            enabled_skills=["plan_forge"],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=False,
            book_scoped=True,
            admin=False,
        )
        assert codes == ["plan_forge"]

    def test_plan_forge_hidden_on_plain_chat_surface(self):
        # book/editor only — a non-book chat pin must not inject it.
        codes = resolve_skills_to_inject(
            enabled_skills=["plan_forge"],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=False,
            book_scoped=False,
            admin=False,
        )
        assert codes == []

    def test_plan_forge_prompt_loads(self):
        prompts = skill_prompts(["plan_forge"])
        assert "plan_forge" in prompts
        assert "plan_propose_spec" in prompts["plan_forge"]
