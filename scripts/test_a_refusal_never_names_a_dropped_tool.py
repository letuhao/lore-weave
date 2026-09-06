"""D-A-REFUSAL-NAMES-A-LEGACY-TOOL-THE-CATALOGUE-ALWAYS-DROPS.

On 2026-08-25 `drop_superseded_tools` was widened to remove EVERY `visibility: legacy` tool
from every turn catalogue, unconditionally — "a legacy tool is a DEAD tool". The older,
narrower rule only dropped one when its named replacement happened to be on the same wire.

That widening turned a whole class of refusal into an instruction that cannot be followed. A
refusal is the runtime's own words telling the model what to call next, and naming a tool is
ALSO what ARMS it onto the turn (`_tools_named_in_refusal` -> `_arm_tools`). So a refusal
naming a legacy tool fails twice: the instruction is impossible, and the arming mechanism is
spent on a tool that will be dropped again.

MEASURED 2026-08-26 on the instance that surfaced it — kg_propose_edge's KG_ENDPOINT_NOT_NODE
said "project the glossary entities into the graph first (kg_project_entities_to_nodes)", and
over batch c-kgedge3 that tool was withheld on 5 of 5 runs (chat_messages.withheld_tools,
stages `superseded` and `domain_not_selected`).

The census then found four such sites, and TWO OF THEM WERE WRITTEN EARLIER THE SAME DAY BY
THE LOOP ITSELF — the motif archive/restore remedy named composition_motif_archive and
composition_motif_restore, both legacy. A defect introduced while fixing a different one, in
the same session, is exactly what a build-failing gate is for: nobody re-reads a tool list.
"""
from __future__ import annotations

import ast
import collections
import pathlib
import re

import pytest

SERVICES = pathlib.Path(__file__).resolve().parents[1] / "services"

#: Constructors whose message argument is handed to the caller — the model, or a human reading
#: the card. A docstring or a comment naming a dead tool is documentation and stays legal.
REFUSAL_CONSTRUCTORS = {"ToolExecutionError", "ValueError", "HTTPException", "RuntimeError"}


def _is_source(p: pathlib.Path) -> bool:
    s = p.as_posix()
    return "/tests/" not in s and not p.name.startswith("test_")


def legacy_tools_by_service() -> dict[str, set[str]]:
    """Every tool registered `visibility="legacy"`, read from the REGISTRATION.

    Deliberately not a hand-kept list: 68 tools carry the marker today across two services and
    a list in this file would be stale the first time someone retires a tool.
    """
    out: dict[str, set[str]] = collections.defaultdict(set)
    for p in SERVICES.rglob("*.py"):
        if not _is_source(p):
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        if 'visibility="legacy"' not in src:
            continue
        service = p.relative_to(SERVICES).parts[0]
        # Registration blocks: a block declaring legacy contributes its own name=.
        for block in re.split(r"@mcp_server\.tool\(|registerTool\(", src):
            if 'visibility="legacy"' in block:
                m = re.search(r'name="([a-z0-9_]+)"', block)
                if m:
                    out[service].add(m.group(1))
    return dict(out)


def refusals_naming(dead: set[str]) -> list[tuple[str, int, str, str]]:
    """(file, line, dead_tool, message) for every refusal message naming a dead tool."""
    found = []
    for p in SERVICES.rglob("*.py"):
        if not _is_source(p):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if fn not in REFUSAL_CONSTRUCTORS:
                continue
            msg = "".join(
                n.value for n in ast.walk(node)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            )
            for name in dead:
                if name in msg:
                    found.append(
                        (p.relative_to(SERVICES).as_posix(), node.lineno, name,
                         " ".join(msg.split())[:160])
                    )
    return found


LEGACY = legacy_tools_by_service()
ALL_DEAD = set().union(*LEGACY.values()) if LEGACY else set()


def test_the_legacy_scan_still_finds_tools():
    """ANTI-VACUITY. If the registration pattern changes, the gate below passes for free and
    the class comes straight back. 68 tools carried the marker when this was written."""
    assert len(ALL_DEAD) >= 40, f"only found {len(ALL_DEAD)} legacy tools — the scan has broken"
    assert "composition-service" in LEGACY and "knowledge-service" in LEGACY


def test_the_refusal_scan_can_see_refusals_at_all():
    """ANTI-VACUITY, the other half: prove the AST walk finds refusal messages, so 'no hits'
    means 'none name a dead tool' and not 'the walk found nothing'."""
    live_names = {"kg_list_templates", "kg_add_nodes", "composition_motif_edit"}
    assert refusals_naming(live_names), (
        "the refusal scan found no message naming even a LIVE tool — it is not working"
    )


def test_no_refusal_names_a_tool_the_catalogue_drops():
    """THE GATE. A legacy tool is dropped from every turn, so a refusal naming one issues an
    instruction the model cannot follow."""
    hits = refusals_naming(ALL_DEAD)
    assert not hits, "refusal(s) name a legacy tool the turn catalogue always drops:\n" + "\n".join(
        f"  {f}:{ln}  [{name}]\n      {msg}" for f, ln, name, msg in sorted(hits)
    )


@pytest.mark.parametrize("dead,live", [
    ("kg_project_entities_to_nodes", "kg_add_nodes"),
    ("composition_motif_archive", "composition_motif_edit"),
    ("kg_adopt_template", "kg_ontology_propose"),
])
def test_the_replacement_named_instead_is_itself_live(dead, live):
    """Swapping one dead name for another would pass the gate and fix nothing."""
    assert dead in ALL_DEAD, f"{dead} is no longer registered legacy — this case is stale"
    assert live not in ALL_DEAD, f"{live} is ALSO legacy; the refusal still names a dead tool"
