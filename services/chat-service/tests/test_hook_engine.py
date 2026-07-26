"""P4 REG-P4-03 — declarative hook engine (pure). No DB/port."""

from app.services.hook_engine import (
    collect_annotations,
    collect_injections,
    decide_pre_tool_call,
    tool_matches,
)


def _hook(event, action, match=None, priority=0):
    return {"on_event": event, "action": action, "match": match or {}, "priority": priority}


def test_tool_matches_glob_and_no_filter():
    assert tool_matches(None, "glossary_delete_entity")
    assert tool_matches({}, "anything")
    assert tool_matches({"tool_pattern": "glossary_delete_*"}, "glossary_delete_entity")
    assert not tool_matches({"tool_pattern": "glossary_delete_*"}, "glossary_search")
    assert tool_matches({"tool": "book_write"}, "book_write")  # alias


def test_deny_blocks_matched_tool():
    hooks = [_hook("pre_tool_call", {"kind": "deny", "message": "no deletes"}, {"tool_pattern": "*_delete_*"})]
    action, msg = decide_pre_tool_call(hooks, "glossary_delete_entity")
    assert action == "deny" and msg == "no deletes"
    # a non-matching tool is allowed
    assert decide_pre_tool_call(hooks, "glossary_search") == ("allow", "")


def test_deny_wins_over_require_approval():
    hooks = [
        _hook("pre_tool_call", {"kind": "require_approval"}, {"tool_pattern": "book_*"}),
        _hook("pre_tool_call", {"kind": "deny", "message": "blocked"}, {"tool_pattern": "book_write"}),
    ]
    assert decide_pre_tool_call(hooks, "book_write")[0] == "deny"
    assert decide_pre_tool_call(hooks, "book_read")[0] == "require_approval"


def test_wrong_event_ignored():
    hooks = [_hook("post_tool_call", {"kind": "deny"}, {"tool_pattern": "*"})]
    assert decide_pre_tool_call(hooks, "anything") == ("allow", "")


def test_collect_pre_turn_injections_in_order():
    hooks = [
        _hook("pre_turn", {"kind": "inject_text", "text": "Keep a wry tone."}, priority=10),
        _hook("pre_turn", {"kind": "inject_text", "text": "Stay in the 1890s."}, priority=5),
        _hook("post_turn", {"kind": "inject_text", "text": "ignored here"}),
    ]
    assert collect_injections(hooks, "pre_turn") == ["Keep a wry tone.", "Stay in the 1890s."]


def test_collect_annotations_matched():
    hooks = [_hook("post_tool_call", {"kind": "annotate", "text": "logged"}, {"tool_pattern": "book_*"})]
    assert collect_annotations(hooks, "book_write") == ["logged"]
    assert collect_annotations(hooks, "glossary_search") == []
