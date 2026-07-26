"""P4 REG-P4-01 — command expansion (pure). No DB/port → no xdist_group needed."""

from app.client.registry_commands_client import (
    RESERVED_COMMANDS,
    expand_command,
    looks_like_command,
)

CMDS = [
    {
        "name": "plan-scene",
        "template_md": "Plan a scene about {{topic}} in the current chapter.",
        "arg_schema": {"properties": {"topic": {"type": "string"}}},
    },
    {
        "name": "recap",
        "template_md": "Recap the last {{n}} chapters focusing on {{focus}}.",
        "arg_schema": {"properties": {"n": {}, "focus": {}}},
    },
    {"name": "note", "template_md": "NOTE: {{args}}", "arg_schema": {}},
]


def test_looks_like_command_gate():
    assert looks_like_command("/plan-scene the duel")
    assert looks_like_command("  /recap 3 combat")
    assert not looks_like_command("hello world")
    assert not looks_like_command("/think")  # reserved built-in
    assert not looks_like_command("/effort=high do it")  # reserved
    assert not looks_like_command("path/like/this")


def test_expand_named_arg_last_soaks_remainder():
    out, name = expand_command("/plan-scene the tavern brawl at dawn", CMDS)
    assert name == "plan-scene"
    assert out == "Plan a scene about the tavern brawl at dawn in the current chapter."


def test_expand_multiple_named_positional():
    out, name = expand_command("/recap 3 the romance subplot", CMDS)
    assert name == "recap"
    # n → "3", focus (last) → "the romance subplot"
    assert out == "Recap the last 3 chapters focusing on the romance subplot."


def test_expand_args_placeholder():
    out, name = expand_command("/note remember the moon is red", CMDS)
    assert name == "note"
    assert out == "NOTE: remember the moon is red"


def test_unknown_command_passes_through():
    out, name = expand_command("/does-not-exist foo", CMDS)
    assert name is None
    assert out == "/does-not-exist foo"


def test_reserved_never_expands():
    out, name = expand_command("/think hard", CMDS)
    assert name is None and out == "/think hard"


def test_missing_args_yield_empty_placeholders():
    out, name = expand_command("/plan-scene", CMDS)
    assert name == "plan-scene"
    assert out == "Plan a scene about  in the current chapter."


def test_reserved_set_matches_builtins():
    for r in ("think", "no_think", "effort", "compact", "clear", "model", "help"):
        assert r in RESERVED_COMMANDS
