"""Teeth for `scripts/deprecated-tool-scan.py`.

The scan sat unwired long enough that its per-line reading was never stress-tested against
real code, and it reported 43 findings of which 34 were its own blind spots. Every test here
pins one of those, so the fix cannot silently regress:

  * a wrapped `_dispatch(` / `_undo(` call — the tool name lands on the CONTINUATION line, and
    the exemption that exists precisely for dispatch keys and undo hints could not see it
  * a `NOTE: superseded by X` sitting one line BELOW the reference it excuses
  * a tool naming ITSELF ("Reverse: book_chapter_set_part with the prior part_id")

and, most importantly, that the scan still goes RED on the thing it exists to catch: an
ADVERTISED tool's description steering the model at a retired one.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "dts", Path(__file__).resolve().parent / "deprecated-tool-scan.py"
)
dts = importlib.util.module_from_spec(_SPEC)
sys.modules["dts"] = dts
_SPEC.loader.exec_module(dts)


LEGACY = {"kg_world_query": "kg_graph_query", "kg_view_upsert": None}
ADVERTISED = {"kg_graph_query", "kg_view_edit", "lore_search"}


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str) -> list[dict]:
    """Scan one synthetic Python tool-description file."""
    f = tmp_path / "server.py"
    f.write_text(source, encoding="utf-8")
    monkeypatch.setattr(dts, "ROOT", tmp_path)
    monkeypatch.setattr(dts, "instruction_files", lambda: [("tool-desc", f, "py")])
    return dts.scan(dict(LEGACY), set(ADVERTISED))


# ── the regression that produced 19 of the 43 false findings ──────────────────────────────

def test_wrapped_dispatch_call_is_not_prose(tmp_path, monkeypatch):
    """`_dispatch(\\n ctx, "kg_world_query",` — the name is a dispatch key, not an instruction.

    The single-line form was already exempt; this is the wrapped form that was not."""
    found = _run(tmp_path, monkeypatch, '''"""mod."""
@mcp_server.tool(
    name="kg_graph_query",
    description="Read the knowledge graph.",
)
async def kg_graph_query(ctx):
    return await _dispatch(
        ctx, "kg_world_query",
        {"limit": 10},
    )
''')
    assert found == [], f"wrapped dispatch key read as prose: {found}"


def test_wrapped_undo_hint_is_not_prose(tmp_path, monkeypatch):
    """An undo hint must name the tool whose SIGNATURE matches — retired tools stay callable
    exactly so undo keeps working. Repointing it at the replacement breaks the undo."""
    found = _run(tmp_path, monkeypatch, '''"""mod."""
@mcp_server.tool(
    name="kg_graph_query",
    description="Read the knowledge graph.",
)
async def kg_graph_query(ctx):
    out["_meta"] = {"undo_hint": _undo(
        "kg_view_upsert", project_id=args.project_id,
    )}
''')
    assert found == [], f"wrapped undo hint read as prose: {found}"


def test_paren_inside_a_description_does_not_move_the_depth_counter(tmp_path, monkeypatch):
    """A description like "(a whole world)" must not be counted as an open paren — otherwise
    the continuation tracker never closes and swallows the rest of the file."""
    assert dts._paren_delta('    "some text (with parens) here",') == 0
    assert dts._paren_delta('    return await _dispatch(') == 1
    assert dts._paren_delta('    )') == -1


def test_the_tracker_closes_and_does_not_swallow_the_rest_of_the_file(tmp_path, monkeypatch):
    """The exemption must end with the call. A real reference AFTER a dispatch block still reds."""
    found = _run(tmp_path, monkeypatch, '''"""mod."""
@mcp_server.tool(
    name="kg_graph_query",
    description="Read the graph.",
)
async def kg_graph_query(ctx):
    return await _dispatch(
        ctx, "kg_world_query",
        {"limit": 10},
    )


@mcp_server.tool(
    name="lore_search",
    description="Search lore. To read a whole world use kg_world_query instead.",
)
async def lore_search(ctx):
    return None
''')
    assert [f["tool"] for f in found] == ["kg_world_query"], found
    assert found[0]["in_default_hotset"] is True


# ── the thing the scan exists to catch — this must stay RED ───────────────────────────────

def test_advertised_tool_pointing_at_a_retired_one_is_blocking(tmp_path, monkeypatch):
    found = _run(tmp_path, monkeypatch, '''"""mod."""
@mcp_server.tool(
    name="lore_search",
    description="Search lore. For a whole world call kg_world_query first.",
)
async def lore_search(ctx):
    return None
''')
    assert len(found) == 1, found
    assert found[0]["tool"] == "kg_world_query"
    assert found[0]["in_default_hotset"] is True, "an advertised owner must block"
    assert found[0]["replacement"] == "kg_graph_query"


def test_reaches_model_is_true_even_for_a_retired_owner(tmp_path, monkeypatch):
    """`toolLoadResult` applies NO legacy filter — it resolves any tool by name and returns its
    description. A retired owner's text still reaches the model; only the HOT-SET differs."""
    found = _run(tmp_path, monkeypatch, '''"""mod."""
@mcp_server.tool(
    name="kg_view_upsert",
    description="Upsert a view. To read a whole world use kg_world_query.",
)
async def kg_view_upsert(ctx):
    return None
''')
    assert len(found) == 1, found
    assert found[0]["reaches_model"] is True
    assert found[0]["in_default_hotset"] is False, "a retired owner is not in the hot set"


# ── the two narrower blind spots ──────────────────────────────────────────────────────────

def test_a_tool_naming_itself_is_not_a_dangling_pointer(tmp_path, monkeypatch):
    found = _run(tmp_path, monkeypatch, '''"""mod."""
@mcp_server.tool(
    name="kg_world_query",
    description="Read a world. Reverse: kg_world_query with the prior world_id.",
)
async def kg_world_query(ctx):
    return None
''')
    assert found == [], f"self-reference reported as dangling: {found}"


def test_superseded_note_below_the_reference_still_exempts(tmp_path, monkeypatch):
    """The note that excuses the reference sits one line LOWER — the exemption is scoped to the
    description, not the line, or it never fires for the layout it was written for."""
    found = _run(tmp_path, monkeypatch, '''"""mod."""
@mcp_server.tool(
    name="kg_view_upsert",
    description=(
        "Upsert a view. Pass the base_version you read from kg_world_query so a "
        "concurrent edit is detected. "
        "NOTE: superseded by kg_graph_query — kept for existing callers only."
    ),
)
async def kg_view_upsert(ctx):
    return None
''')
    assert found == [], f"description-scoped superseded note did not exempt: {found}"


# ── the ratchet ───────────────────────────────────────────────────────────────────────────

def _fake_findings(n_debt: int, n_blocking: int = 0) -> list[dict]:
    row = {"kind": "tool-desc", "file": "services/x/app/mcp/server.py", "line": 1,
           "tool": "kg_world_query", "problem": "retired", "replacement": None,
           "owner": "o", "reaches_model": True}
    return ([{**row, "in_default_hotset": True}] * n_blocking
            + [{**row, "in_default_hotset": False}] * n_debt)


@pytest.mark.parametrize(
    "n_debt,n_blocking,expected",
    [
        (dts.DEAD_TO_DEAD_BASELINE, 0, 0),      # at baseline, nothing live → green
        (dts.DEAD_TO_DEAD_BASELINE + 1, 0, 1),  # a NEW retired→retired reference → red
        (dts.DEAD_TO_DEAD_BASELINE - 1, 0, 1),  # progress must be recorded, not pocketed → red
        (dts.DEAD_TO_DEAD_BASELINE, 1, 1),      # an advertised owner → always red
    ],
)
def test_ratchet_reds_in_both_directions(monkeypatch, n_debt, n_blocking, expected):
    monkeypatch.setattr(dts, "build_catalog", lambda: (dict(LEGACY), set(ADVERTISED)))
    monkeypatch.setattr(dts, "scan", lambda *a: _fake_findings(n_debt, n_blocking))
    monkeypatch.setattr(sys, "argv", ["deprecated-tool-scan.py"])
    assert dts.main() == expected


def test_the_exemption_does_not_leak_into_the_next_tool(tmp_path, monkeypatch):
    """One tool declaring itself superseded must not excuse the NEXT tool's stale pointer."""
    found = _run(tmp_path, monkeypatch, '''"""mod."""
@mcp_server.tool(
    name="kg_view_edit",
    description="Edit a view. NOTE: superseded by nothing; this is the live one.",
)
async def kg_view_edit(ctx):
    return None


@mcp_server.tool(
    name="lore_search",
    description="Search lore. For a world use kg_world_query.",
)
async def lore_search(ctx):
    return None
''')
    assert [f["tool"] for f in found] == ["kg_world_query"], found
