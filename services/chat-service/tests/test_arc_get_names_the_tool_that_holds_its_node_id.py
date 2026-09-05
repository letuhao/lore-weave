"""D-THE-ONLY-SUPPLIER-OF-node_id-IS-NEVER-ADVERTISED-WITH-arc_get.

    THE INVARIANT. A tool that refuses for a missing id must NAME the tool that holds it —
    because naming is also ARMING, and an unnameable supplier is an unreachable one.

MEASURED 2026-08-30 over every recorded call in the live chat store:

    composition_arc_get            93 calls   0 ok   0 carded
      every failure: "missing required argument(s): ['node_id']"

    the surface on those 93 turns, from the server's own advertised_tools:
      composition_package_tree     advertised 93 of 93     (623 of 673 ok overall)
      composition_list_outline     advertised  3 of 93
      composition_arc_list         advertised  0 of 93     (5 of 5 ok when called)

The always-present tool names arcs WITHOUT IDS — `composition_package_tree` returns
`"arcs": ["arc \\"The Shifting Tide\\" · outline", ...]`, plain strings — so a model reading it
learns an arc exists and cannot address it. Across 16 fresh runs the model said exactly that,
every time: *"I can see that Arc I — The Hollow Keep is part of your story outline, but I need
its specific ID."* No invented id, no false claim. Given that surface there was no better move.

🔴 AND THE DECLARATION IS A FACT, NOT A GUESS, which is what makes it safe to add:
  * `composition_arc_get(node_id)` declares "The arc/saga (structure_node) id. (a UUID)"
  * `composition_arc_list` "Returns a flat, deterministically-ordered node list" and a real
    payload reads `{"nodes": [{"id": "01a0214c-…", "kind": "arc", "title": "Arc I — …"}]}`
  * `composition_package_tree`'s OWN description already says "To read an arc's actual nodes use
    composition_list_outline / composition_arc_list"

The last point is the whole reason a description was not enough: the supplier was already named
in prose the model reads, and prose does not ARM. `_tools_named_in_refusal` -> `_arm_tools` does,
and it only sees `argument_emitters`.
"""
from __future__ import annotations

import json
import pathlib

from app.services.stream_service import _missing_args_message

ROOT = pathlib.Path(__file__).resolve().parents[3]
REGISTRY = json.loads(
    (ROOT / "contracts" / "agent-runtime-tool-contracts.json").read_text(encoding="utf-8"))
EMITTERS = REGISTRY["argument_emitters"]
CONTRACTS = REGISTRY["contracts"]


def test_the_emitter_is_declared():
    assert EMITTERS.get("composition_arc_get", {}).get("node_id") == "composition_arc_list", (
        "composition_arc_get.node_id no longer declares composition_arc_list — the refusal goes "
        "back to 'this tool does not declare which side supplies them' and the supplier becomes "
        "unnameable, therefore unarmable, on a tool measured at 0 of 93 ok")


def test_the_refusal_NAMES_it():
    """The point of the declaration. A refusal that names no tool leaves the model with the
    honest-failure branch, which is what all 93 recorded calls took."""
    msg = _missing_args_message(
        "composition_arc_get", ["node_id"], CONTRACTS.get("composition_arc_get"), {})
    assert "composition_arc_list" in msg, msg


def test_the_refusal_no_longer_says_NOBODY_declares_it():
    """The exact sentence the 93 failures received. It was true before this declaration and is
    false after it; if it comes back, the declaration has stopped being read."""
    msg = _missing_args_message(
        "composition_arc_get", ["node_id"], CONTRACTS.get("composition_arc_get"), {})
    assert "does not declare which side supplies" not in msg, msg


def test_a_tool_WITHOUT_a_declaration_is_unchanged():
    """🔴 ANTI-VACUITY. If the refusal named a supplier for everything, naming would carry no
    information and the arming it drives would fire on turns that have no supplier to reach."""
    msg = _missing_args_message("composition_arc_get", ["book_id"], None, {})
    assert "composition_arc_list" not in msg, msg


def test_the_emitter_is_a_TOOL_NAME_not_prose():
    """An armed value is looked up in the catalogue; prose there would arm nothing and the
    failure would be silent."""
    e = EMITTERS["composition_arc_get"]["node_id"]
    assert " " not in e and e.islower() and "_" in e, repr(e)
