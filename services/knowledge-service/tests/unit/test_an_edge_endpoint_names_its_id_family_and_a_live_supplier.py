"""D-ENTITY-ID-MEANS-TWO-DIFFERENT-IDS-IN-ADJACENT-TOOLS.

A GLOSSARY entity id and a graph `:Entity` NODE id are different objects with the same shape
and the same name. kg_propose_edge requires the NODE id — `existing_entity_node_ids` matches on
`Entity.id` and `KG_ENDPOINT_NOT_NODE` rejects anything else — while its arguments were
described as "The id of the relationship's source entity", which invites the other one.

Measured 2026-08-26, batch c-kgedge3: on 3 of 3 kg_propose_edge calls the model passed the
GLOSSARY entity ids, matched exactly against the run's own seed_ids
(glossary_propose_entities.results[N].entity_id). Well-formed UUIDs, real objects, wrong family.

And the recovery path was worse than useless:

🔴 THE REFUSAL NAMED A TOOL THE TURN CANNOT SEE. KG_ENDPOINT_NOT_NODE said "project the
glossary entities into the graph first (kg_project_entities_to_nodes)". That tool is
`visibility: legacy`, and since 2026-08-25 `drop_superseded_tools` drops EVERY legacy tool from
every turn catalogue unconditionally ("a legacy tool is a DEAD tool"). Measured over the same
batch, from chat_messages.withheld_tools: withheld on 5 of 5 runs, at stages `superseded` and
`domain_not_selected`. Naming a tool is also what ARMS it onto the turn, so an unreachable name
arms nothing — the platform's own remedy for this exact failure pointed at a dead tool.
"""
from __future__ import annotations

import inspect
import pathlib
import re

import pytest

from app.mcp import server as mcp_server
from app.tools import graph_schema_tools as gst

SERVER_SRC = pathlib.Path(inspect.getfile(mcp_server)).read_text(encoding="utf-8")
EDGE_SRC = inspect.getsource(gst._handle_kg_propose_edge)


def legacy_tool_names() -> set[str]:
    """Every tool this service registers with `visibility="legacy"`, read from the registration
    itself rather than a hand-kept list — a hand-kept list is how the next one gets missed."""
    return set(
        re.findall(
            r'visibility="legacy",\s*\n\s*tool_name="([a-z0-9_]+)"',
            SERVER_SRC,
        )
    )


def test_this_service_actually_has_legacy_tools():
    """Anti-vacuity: if the pattern stops matching, every check below passes for free."""
    names = legacy_tool_names()
    assert len(names) >= 3, f"only found {names} — the legacy-tool scan has stopped working"
    assert "kg_project_entities_to_nodes" in names


def code_without_comments(src: str) -> str:
    """Comments are for the next maintainer and never reach the model. The comment ABOVE this
    refusal has to name the dead tool to explain what was wrong, so a scan that cannot tell a
    comment from an instruction would forbid recording the defect it is guarding against."""
    return " ".join(line for line in src.splitlines() if not line.lstrip().startswith("#"))


def test_the_endpoint_refusal_does_not_name_a_dead_tool():
    """THE CLASS. A refusal is the runtime's own instruction to the model; naming a legacy tool
    tells it to call something that is dropped from the wire by construction."""
    live = code_without_comments(EDGE_SRC)
    for dead in legacy_tool_names():
        assert dead not in live, (
            f"the kg_propose_edge refusal names {dead}, which is visibility=legacy and is "
            f"therefore dropped from every turn catalogue — the instruction cannot be followed"
        )


def test_the_endpoint_refusal_names_a_LIVE_supplier():
    """PRECISION. Removing the dead name is only half — the caller still needs somewhere to go."""
    assert "KG_ENDPOINT_NOT_NODE" in EDGE_SRC
    assert "kg_add_nodes" in EDGE_SRC, "the refusal names no supplier at all"
    assert "from_glossary" in EDGE_SRC, (
        "the refusal must name the MODE that projects a glossary entity, not just the tool"
    )


def test_the_refusal_says_which_id_family_was_passed():
    """The whole confusion is two id families with one name. A refusal that says only 'not yet
    graph nodes' leaves a caller holding a real, valid, wrong-family id with nothing to act on."""
    assert "glossary entity id" in EDGE_SRC.lower()
    assert "node id" in EDGE_SRC.lower()


def test_the_endpoint_arguments_distinguish_the_two_id_families():
    """The mint-time description, so a caller need not reach the refusal at all."""
    src = SERVER_SRC[SERVER_SRC.index("async def kg_propose_edge"):]
    src = src[: src.index("-> dict:")]
    assert "NOT a glossary entity id" in src, "source_entity_id still invites the wrong family"
    assert "kg_add_nodes" in src, "the argument names no supplier for a node id"


def test_the_declared_emitter_is_a_live_tool():
    """argument_emitters now declares where an endpoint comes from — and the emitter-arm fix
    (2026-08-26) makes a declared emitter sayable in a refusal for a tool with no contract row,
    which kg_propose_edge is. A declaration naming a LEGACY tool would put a dead name into
    that sentence, which is the defect this file is about, arriving by another route."""
    import json

    root = pathlib.Path(__file__).resolve().parents[4]
    reg = json.loads(
        (root / "contracts" / "agent-runtime-tool-contracts.json").read_text(encoding="utf-8")
    )
    declared = reg["argument_emitters"].get("kg_propose_edge")
    assert declared, "kg_propose_edge declares no emitter for its endpoints"
    dead = legacy_tool_names()
    for arg, emitter in declared.items():
        assert emitter not in dead, f"{arg} declares {emitter}, which is a legacy (dropped) tool"
        assert emitter == "kg_add_nodes", f"{arg} -> {emitter}"


@pytest.mark.parametrize("arg", ["source_entity_id", "target_entity_id"])
def test_both_endpoints_are_covered(arg):
    """Both, not just the one that happened to be measured."""
    src = SERVER_SRC[SERVER_SRC.index("async def kg_propose_edge"):]
    src = src[: src.index("-> dict:")]
    at = src.index(arg)
    assert "NOT a glossary entity id" in src[at:at + 400] or "Same " in src[at:at + 400], (
        f"{arg} does not say which id family it needs"
    )
