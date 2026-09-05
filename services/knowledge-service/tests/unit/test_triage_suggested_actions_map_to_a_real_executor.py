"""TOOLV2 LOOP #259 — suggested_actions names actions from three tools and says which for none.

kg_triage_resolve is correct on every path measured:

    unknown signature                -> "no pending triage items for this signature"
    action outside the enum          -> names the five valid values AND the value sent
    map on a proposed_edge           -> "action 'map' is not valid for item_type 'proposed_edge'"
    dismiss                          -> {"status": "resolved", "affected": 1}, verified in the DB

The per-item_type gate is the interesting part: the enum offers five actions and the gate narrows
them by item type, which is right. The listing is where the agent is meant to learn the narrowing
— `suggested_actions` — and a census of it against the LIVE tool schemas found:

    12 actions advertised | 10 with an MCP executor | 2 with none

The two are `promote_to_glossary_kind` and `demote_to_attribute`, and they are NOT a defect. They
are deliberately human-initiated cross-service glossary writes: the REST resolve route moves the
items to `pending_glossary` and returns `needs_glossary{book_id, kinds}` so the FE deep-links the
user into glossary, and this router never calls glossary itself. Checking that before filing is
what turned an apparent orphan into a design.

What IS wrong is the description. It said "Schema-changing actions (add to vocab/schema, widen,
promote to glossary) are NOT available here — those need explicit human confirmation via the
review surface", which conflates two different situations. Schema-changing actions ARE available
to an agent, on kg_triage_schema_write, a confirm-gated W-tier tool it does not name. Only the two
glossary handoffs are genuinely human-only. So an agent was told to stop where it could have
proceeded, and given no route where a route exists — #252's shape, in a second tool.

This guard does not hardcode the mapping. It rebuilds it from the tool definitions, so adding a
sixth action anywhere, or moving one between tools, is checked rather than assumed.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"

# Actions with no MCP executor BY DESIGN — cross-service glossary handoffs the user initiates.
HUMAN_ONLY = {"promote_to_glossary_kind", "demote_to_attribute"}


def _advertised() -> set[str]:
    src = (APP / "db" / "repositories" / "triage.py").read_text(encoding="utf-8")
    start = src.index("SUGGESTED_ACTIONS:")
    blk = src[start: src.index("\n\n", start)]
    keys = set(re.findall(r'^\s*"([a-z_]+)": \[', blk, re.M))
    return set(re.findall(r'"([a-z_]+)"', blk)) - keys


def _executors() -> dict[str, str]:
    """action -> the tool whose Literal/enum accepts it, read from the arg models."""
    src = (APP / "tools" / "graph_schema_tools.py").read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for cls, tool in (("KgTriageResolveArgs", "kg_triage_resolve"),
                      ("KgTriageSchemaWriteArgs", "kg_triage_schema_write")):
        start = src.index(f"class {cls}(")
        body = src[start: src.index("\nclass ", start + 10)]
        m = re.search(r"action:\s*Literal\[([^\]]+)\]", body)
        assert m, f"{cls} no longer declares its action Literal"
        for a in re.findall(r'"([a-z_]+)"', m.group(1)):
            out[a] = tool
    out["place_edge"] = "kg_triage_place_edge"
    return out


def test_every_advertised_action_has_an_executor_or_is_known_human_only():
    """A silently orphaned action is one the agent will try and fail on with no explanation.
    Adding one to SUGGESTED_ACTIONS without a tool — or without listing it as human-only — fails
    here rather than in production."""
    orphans = _advertised() - set(_executors()) - HUMAN_ONLY
    assert orphans == set(), (
        f"these suggested_actions have no MCP executor and are not recorded as human-only: "
        f"{sorted(orphans)}"
    )


def test_the_human_only_pair_really_has_no_executor():
    """The other direction: if one of these ever gains a tool, the description below stops being
    true and must be re-decided instead of quietly under-selling what the agent can do."""
    assert HUMAN_ONLY & set(_executors()) == set()


def test_the_description_names_the_tool_that_takes_the_schema_actions():
    for rel in ("mcp/server.py", "tools/graph_schema_tools.py"):
        body = APP.joinpath(rel).read_text(encoding="utf-8").replace("\r\n", "\n")
        flat = re.sub(r'"\s*\n\s*"', "", body)
        start = flat.index("Resolve a triage signature group with a low-impact")
        desc = flat[start: start + 900]
        assert "kg_triage_schema_write" in desc, (
            f"{rel}: the description sends the agent away from schema actions without naming "
            "the tool that performs them"
        )
        assert "are NOT available here" not in desc, (
            f"{rel}: they ARE available, on another tool — the old wording stops the agent short"
        )


def test_the_description_separates_human_only_from_another_tool():
    """The original sentence lumped the glossary handoffs in with the schema actions. They are
    different: one needs a different tool, the other needs a person."""
    for rel in ("mcp/server.py", "tools/graph_schema_tools.py"):
        body = APP.joinpath(rel).read_text(encoding="utf-8").replace("\r\n", "\n")
        flat = re.sub(r'"\s*\n\s*"', "", body)
        start = flat.index("Resolve a triage signature group with a low-impact")
        desc = flat[start: start + 900]
        for token in HUMAN_ONLY:
            assert token in desc, f"{rel}: name {token} explicitly, not 'promote to glossary'"
        assert "human-only" in desc


def test_the_description_warns_that_the_listing_spans_tools():
    """suggested_actions is a flat list drawn from three tools; an agent that assumes one tool
    owns all of them will call this one with an action it cannot take."""
    for rel in ("mcp/server.py", "tools/graph_schema_tools.py"):
        body = APP.joinpath(rel).read_text(encoding="utf-8").replace("\r\n", "\n")
        flat = re.sub(r'"\s*\n\s*"', "", body)
        assert "names actions from all three triage tools" in flat, rel
