"""K20 — a closed set this service enforces must be DECLARED in the schema.

Sibling of book-service's TestEveryEnumeratedClosedSetHasAnEnum, same rule, Python spelling.

The defect found here on 2026-07-23: three args were runtime-checked closed sets advertised
as bare strings —

    composition_arc_template_list.scope    "mine | system | all"      (rejects anything else)
    composition_arc_template_list.status   "draft | active | archived"
    composition_motif_link_list.direction  "'out', 'in', or 'both'"

— plus `composition_canon_rule_create.scope`, which the DATABASE constrains with
CHECK (scope IN ('world','entity','reveal_gate')) while the arg carried no enum AND no
description at all. In every case the handler (or Postgres) rejected a near-miss the model
was never told about: a hard error it had no way to avoid. `Literal[...]` fixes it, because
FastMCP emits a real `enum` from a Literal and the enum is the only form a validator reads.
"""
from __future__ import annotations

import pytest

from loreweave_mcp.closed_set_gate import (
    count_enumerating_descriptions,
    enumerated_values_in_description,
    find_undeclared_closed_sets,
)


@pytest.mark.asyncio
async def test_every_enumerated_closed_set_is_declared():
    from app.mcp.server import mcp_server

    tools = await mcp_server.list_tools()
    assert tools, "tools/list returned nothing — the catalog failed to register"

    bad = find_undeclared_closed_sets(tools)
    assert not bad, "\n".join(
        f"{t}.{a} enumerates {v} in its DESCRIPTION but advertises no `enum` — the model is "
        f"validated against a set the schema never declares, so a near-miss value is either "
        f"silently accepted or hard-rejected with no way to have known. Type it as "
        f"Literal{v!r}."
        for t, a, v in bad
    )

    # Guard the guard: if nothing in the catalog enumerates a set any more, the detector has
    # gone blind and this test would pass vacuously forever.
    assert count_enumerating_descriptions(tools) > 0, (
        "the detector matched NO enumerated description anywhere in the catalog — it has "
        "almost certainly gone blind; this test would now pass vacuously"
    )


@pytest.mark.asyncio
async def test_the_four_repaired_args_actually_carry_their_enums():
    """Pin the specific repairs, so a refactor back to `str` reds here with a name — the
    gate above would too, but this says WHICH tool and WHAT set."""
    from app.mcp.server import mcp_server

    tools = {t.name: t for t in await mcp_server.list_tools()}
    expected = {
        ("composition_arc_template_list", "scope"): {"mine", "system", "all"},
        ("composition_arc_template_list", "status"): {"draft", "active", "archived"},
        ("composition_motif_link_list", "direction"): {"out", "in", "both"},
        # Must match the DB's CHECK constraint exactly, or a value the schema allows would
        # still 23514 at the insert.
        ("composition_canon_rule_create", "scope"): {"world", "entity", "reveal_gate"},
    }
    for (tool_name, arg), want in expected.items():
        tool = tools.get(tool_name)
        assert tool is not None, f"{tool_name} is no longer advertised"
        prop = (tool.inputSchema.get("properties") or {}).get(arg)
        assert prop is not None, f"{tool_name}.{arg} is gone"
        got = set(prop.get("enum") or [])
        for branch in (prop.get("anyOf") or []):
            got |= set(branch.get("enum") or [])
        assert got == want, f"{tool_name}.{arg} enum = {sorted(got)}, want {sorted(want)}"


class TestDetector:
    """The detector is load-bearing; pin its edges directly."""

    @pytest.mark.parametrize("desc,want", [
        ("mine | system | all", 3),
        ("the structure operation: create_part | rename_part | reorder_parts", 3),
        ("what to list: books | chapters | revisions (default books)", 3),
        ("when the rule fires: always|scene_match|manual|auto (default always)", 4),
        ("a free-text note", 0),
        ("pick the part | then tell me which chapter to move", 0),  # prose: tokens have spaces
        ("", 0),
        (None, 0),
    ])
    def test_edges(self, desc, want):
        got = enumerated_values_in_description(desc)
        assert len(got or []) == want, f"{desc!r} -> {got}"
