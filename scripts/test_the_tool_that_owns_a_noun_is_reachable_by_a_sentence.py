"""A tool that OWNS a noun must be reachable by a SENTENCE using it, not only by a command.

THE INVARIANT. A tool's declared vocabulary has to cover how the request is actually phrased. A
vocabulary made entirely of imperative list-shapes answers "list arcs" and nothing else, so an
author who merely NAMES the thing mid-sentence reaches nothing at all.

🔴 MEASURED 2026-09-01 against the real `answerable_tools` over the live 316-tool catalogue.
`composition_arc_list` declared six phrasings, every one list-shaped:

    "What arcs does this book have?"                                    -> EMPTY
    "Show me the opening arc"                                           -> EMPTY
    "Which arc does chapter 3 belong to?"                               -> EMPTY
    "Attach Emberfall Seam to the opening arc as this book's motif."    -> only motif_search

The last is D-THE-MODEL-CLAIMS-A-BINDING-IT-NEVER-MADE's own wording, and it is why DQ-T58's
shipped refusal ("that is an arc, this tool binds CHAPTERS") never fired in five live runs: to be
told that, the model must first HOLD an arc id, and nothing put the arc lister on the wire.

WHY A DECLARATION AND NOT AN EMITTER — read out of the mechanism, not guessed. R1's
supplier-arming seeds from `_answerable` only, so a tool riding the DOMAIN HOT SET never arms its
declared suppliers; and `composition_motif_bind_edit.node_id` is a CHAPTER node, so naming the
arc lister as its emitter would be a false registry entry.

THE COST WAS PRICED FIRST, over 2,033 distinct real prompts from the chat store
(`scripts/toolloop/arc_synonym_probe.py`): 108 newly match, 105 of those tie with a tool already
answerable, and ZERO tools are DISPLACED. Displacement is the figure that matters — ANSWERABLE_MAX
truncates at 8, so a synonym can EVICT a tool the turn needed — and the probe's first version did
not measure it.

WHAT THIS DOES NOT COVER: it says nothing about whether the model then CHOOSES the tool, and a
match is not a promise the tool was advertised (see the sibling gate's list of the other paths).
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "chat-service"))

CACHE = ROOT / "contracts" / "tool-catalog-cache.json"

try:
    from app.services.tool_surface import answerable_tools
except Exception as e:  # chat-service not importable here
    pytest.skip(f"chat-service not importable: {e}", allow_module_level=True)

#: tool -> requests an author actually writes about the thing it owns. NOT list-shaped,
#: deliberately: a list-shaped probe would pass against the very vocabulary this file rejects.
OWNED_NOUNS = {
    "composition_arc_list": [
        "What arcs does this book have?",
        "Show me the opening arc",
        "Which arc does chapter 3 belong to?",
        "Attach Emberfall Seam to the opening arc as this book's motif.",
    ],
}

#: Wording that appears in a MEASURED prompt and nowhere else. Declaring one of these would make
#: the tests above pass while helping no author — DQ-T58 refused an earlier attempt for exactly
#: this, and the refusal is the reason this list exists.
OVERFIT = ("opening arc", "emberfall", "arc i", "chapter 3")


def _defs():
    raw = json.loads(CACHE.read_text(encoding="utf-8"))
    return [{"type": "function", "function": {
        "name": n, "description": t.get("description") or "",
        "parameters": t.get("inputSchema") or {}, "_meta": t.get("meta") or {}}}
        for n, t in raw.items()]


@pytest.fixture(scope="module")
def defs():
    d = _defs()
    # The adapter controls, RAISING rather than warning: "nothing matched" is exactly what a
    # broken conversion says, and it is also this file's failure mode.
    if "glossary_propose_translation" not in answerable_tools(
            "Give me vietnamese names for these characters", d):
        pytest.fail("ADAPTER BROKEN — the positive control did not match")
    if answerable_tools("hello, how are you today", d):
        pytest.fail("ADAPTER BROKEN — chitchat matched something")
    return d


def _synonyms(defs_, tool):
    for td in defs_:
        if td["function"]["name"] == tool:
            return [s.lower() for s in (td["function"]["_meta"].get("synonyms") or [])]
    raise AssertionError(f"{tool} is not in the catalogue cache — renamed, or the cache is stale")


@pytest.mark.parametrize(
    ("tool", "request_text"),
    [(t, p) for t, ps in OWNED_NOUNS.items() for p in ps],
)
def test_a_sentence_about_the_thing_reaches_the_tool_that_owns_it(defs, tool, request_text):
    got = answerable_tools(request_text, defs)
    assert tool in got, (
        f"{request_text!r} does not reach {tool} — it answers {sorted(got) or 'NOTHING'}. The "
        "tool that owns the noun must be reachable by a sentence about it, or the request goes "
        "nowhere and no refusal downstream can ever fire.")


@pytest.mark.parametrize("tool", sorted(OWNED_NOUNS))
def test_the_declaration_is_not_shaped_like_the_measured_prompt(defs, tool):
    syns = _synonyms(defs, tool)
    bad = [s for s in syns if any(o in s for o in OVERFIT)]
    assert not bad, (
        f"{tool} declares {bad}, which is the measured prompt's own wording rather than a "
        "phrasing authors share. It would satisfy the test above and help nobody.")


@pytest.mark.parametrize("tool", sorted(OWNED_NOUNS))
def test_the_vocabulary_is_not_entirely_command_shaped(defs, tool):
    """The rule, not the instance: at least one phrasing must be the bare noun, or the tool is
    reachable only by an author who already knows to ask for a list."""
    syns = _synonyms(defs, tool)
    bare = [s for s in syns if " " not in s.strip()]
    assert bare, (
        f"{tool}'s synonyms are all multi-word: {syns}. A sentence that merely USES the noun "
        "cannot match any of them, which is the defect this file was written for.")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
