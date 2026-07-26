"""Unit tests for the planner-executor POC pure core (D-WEAK-MODEL-PLANNER)."""

from app.services.tool_plan import (
    build_plan_prompt,
    parse_plan,
    plan_directive,
    restrict_tools_to_plan,
)

KNOWN = {"book_list", "book_get", "book_update_details", "book_chapter_create", "confirm_action"}


def _fn(name: str) -> dict:
    return {"type": "function", "function": {"name": name}}


def test_parse_plan_extracts_ordered_names():
    assert parse_plan('["book_list", "book_update_details"]', KNOWN) == [
        "book_list", "book_update_details",
    ]


def test_parse_plan_tolerates_json_fence_and_prose():
    raw = 'Here is the plan:\n```json\n["book_list", "book_update_details"]\n```\nDone.'
    assert parse_plan(raw, KNOWN) == ["book_list", "book_update_details"]


def test_parse_plan_drops_hallucinated_names():
    # a name not in the known catalog must NEVER be executed
    assert parse_plan('["book_list", "book_teleport", "book_update_details"]', KNOWN) == [
        "book_list", "book_update_details",
    ]


def test_parse_plan_dedupes_preserving_order():
    assert parse_plan('["book_list","book_list","book_update_details"]', KNOWN) == [
        "book_list", "book_update_details",
    ]


def test_parse_plan_empty_for_conversational():
    assert parse_plan("[]", KNOWN) == []
    assert parse_plan("no tool needed", KNOWN) == []
    assert parse_plan("", KNOWN) == []


def test_restrict_offers_only_planned_plus_core():
    advertised = [
        _fn("book_list"), _fn("book_get"), _fn("book_update_details"),
        _fn("book_chapter_create"), _fn("confirm_action"), _fn("kg_build_graph"),
    ]
    plan = ["book_list", "book_update_details"]
    out = [td["function"]["name"] for td in restrict_tools_to_plan(advertised, plan)]
    # the WRONG sibling (book_chapter_create) that stole the live pick is NOT offered
    assert "book_chapter_create" not in out
    assert "book_get" not in out          # not in the plan
    assert "kg_build_graph" not in out    # unrelated
    # planned tools present, in plan order, then the kept core (confirm_action)
    assert out[:2] == ["book_list", "book_update_details"]
    assert "confirm_action" in out        # always-keep core (Tier-W confirm)


def test_restrict_skips_planned_tool_not_yet_loaded():
    # a plan tool whose schema isn't in the advertised set is skipped (caller loads it)
    advertised = [_fn("book_list"), _fn("confirm_action")]
    out = [td["function"]["name"] for td in restrict_tools_to_plan(advertised, ["book_list", "book_update_details"])]
    assert out == ["book_list", "confirm_action"]  # update_details not present -> skipped


def test_prompt_and_directive_render():
    p = build_plan_prompt("book_list: list books\nbook_update_details: edit details", "update the description")
    assert "PLANNER" in p and "JSON array" in p and "update the description" in p
    d = plan_directive(["book_list", "book_update_details"], "update the description")
    assert "1. book_list" in d and "2. book_update_details" in d and "one step at a time" in d.lower()
