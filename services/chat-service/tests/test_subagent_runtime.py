"""P5 REG-P5-01 runtime — pure scoped-tool resolution + guards (M1).

The security crux is `resolve_scoped_tools`: a subagent may ONLY be advertised
tools its `tool_scope` globs match, and NEVER a meta tool (find_tools /
run_subagent → no recursion) or a frontend/UI tool (no browser in a headless
nested loop). These tests pin that whitelist behaviour + the depth guard + the
dynamic-enum tool builder + the result cap.
"""

from __future__ import annotations

from app.services.subagent_runtime import (
    MAX_SUBAGENT_DEPTH,
    RUN_SUBAGENT_NAME,
    SUBAGENT_RESULT_CHAR_CAP,
    build_run_subagent_tool,
    cap_result,
    resolve_scoped_tools,
)


def _tool(name: str) -> dict:
    return {"type": "function", "function": {"name": name, "description": name, "parameters": {}}}


CATALOG = [
    _tool("glossary_search"),
    _tool("glossary_book_patch"),
    _tool("kg_project_list"),
    _tool("kg_search"),
    _tool("book_write"),
    _tool("find_tools"),          # meta — must always be excluded
    _tool("run_subagent"),        # meta — must always be excluded
    _tool("propose_edit"),        # frontend — must always be excluded
    _tool("confirm_action"),      # frontend — must always be excluded
]


def _names(defs: list[dict]) -> set[str]:
    return {d["function"]["name"] for d in defs}


class TestResolveScopedTools:
    def test_glob_intersect_selects_only_matching(self):
        got = resolve_scoped_tools(CATALOG, ["glossary_*", "kg_*"])
        assert _names(got) == {
            "glossary_search", "glossary_book_patch", "kg_project_list", "kg_search",
        }

    def test_exact_name_glob(self):
        got = resolve_scoped_tools(CATALOG, ["glossary_search"])
        assert _names(got) == {"glossary_search"}

    def test_out_of_scope_tool_never_appears(self):
        got = resolve_scoped_tools(CATALOG, ["glossary_*", "kg_*"])
        assert "book_write" not in _names(got)

    def test_meta_tools_excluded_even_if_glob_matches(self):
        # A malicious/broad scope that would match the meta tools must NOT
        # re-admit them (recursion / self-call guard).
        got = resolve_scoped_tools(CATALOG, ["find_tools", "run_subagent", "*"])
        assert "find_tools" not in _names(got)
        assert "run_subagent" not in _names(got)

    def test_frontend_tools_excluded_even_if_glob_matches(self):
        # Headless nested loop: a UI tool would hang/no-op — always dropped.
        got = resolve_scoped_tools(CATALOG, ["*"])
        assert "propose_edit" not in _names(got)
        assert "confirm_action" not in _names(got)

    def test_wildcard_grants_all_non_meta_non_frontend(self):
        got = resolve_scoped_tools(CATALOG, ["*"])
        assert _names(got) == {
            "glossary_search", "glossary_book_patch", "kg_project_list",
            "kg_search", "book_write",
        }

    def test_empty_scope_is_text_only(self):
        # Zero tools is VALID — a persona rewrite/summarize subagent.
        assert resolve_scoped_tools(CATALOG, []) == []

    def test_no_match_globs_is_text_only(self):
        assert resolve_scoped_tools(CATALOG, ["translation_*", "nope_*"]) == []

    def test_non_string_globs_ignored(self):
        got = resolve_scoped_tools(CATALOG, ["glossary_*", None, 3, ""])  # type: ignore[list-item]
        assert _names(got) == {"glossary_search", "glossary_book_patch"}

    def test_tolerates_malformed_catalog_entries(self):
        catalog = [*CATALOG, {"no": "function"}, {"function": {}}, "junk"]  # type: ignore[list-item]
        got = resolve_scoped_tools(catalog, ["glossary_search"])
        assert _names(got) == {"glossary_search"}


class TestBuildRunSubagentTool:
    def test_returns_none_when_no_subagents(self):
        assert build_run_subagent_tool([]) is None

    def test_builds_closed_set_enum(self):
        td = build_run_subagent_tool(["lore-scout", "style-editor"])
        assert td is not None
        fn = td["function"]
        assert fn["name"] == RUN_SUBAGENT_NAME
        props = fn["parameters"]["properties"]
        # closed-set arg ⇒ enum (Frontend-Tool-Contract rule)
        assert props["subagent"]["enum"] == ["lore-scout", "style-editor"]
        assert props["task"]["type"] == "string"
        assert set(fn["parameters"]["required"]) == {"subagent", "task"}

    def test_dedupes_and_preserves_order(self):
        td = build_run_subagent_tool(["b", "a", "b"])
        assert td["function"]["parameters"]["properties"]["subagent"]["enum"] == ["b", "a"]


class TestCapResult:
    def test_under_cap_unchanged(self):
        text, truncated = cap_result("hello")
        assert text == "hello"
        assert truncated is False

    def test_over_cap_truncated_with_note(self):
        big = "x" * (SUBAGENT_RESULT_CHAR_CAP + 500)
        text, truncated = cap_result(big)
        assert truncated is True
        assert len(text) <= SUBAGENT_RESULT_CHAR_CAP + 100  # cap + the note
        assert "truncated" in text.lower()

    def test_custom_char_cap_overrides_default(self):
        # The caller (stream_service) scales this per the session model's real
        # context_length instead of always using the flat SUBAGENT_RESULT_CHAR_CAP.
        big = "x" * (SUBAGENT_RESULT_CHAR_CAP + 500)
        text, truncated = cap_result(big, char_cap=SUBAGENT_RESULT_CHAR_CAP + 500)
        assert truncated is False
        assert text == big


def test_depth_cap_is_one():
    # Depth is capped at 1 — a subagent can never spawn another subagent.
    assert MAX_SUBAGENT_DEPTH == 1
