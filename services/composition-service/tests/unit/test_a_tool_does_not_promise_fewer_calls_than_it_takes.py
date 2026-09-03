"""A tool's description must not promise fewer round-trips than its protocol takes.

    THE INVARIANT. `composition_build_cast_and_graph` is a six-op pipeline whose protocol is
    FIVE CALLS AND TWO HUMAN GATES. Its description says so, and never claims one call.

OWNER RULING 2026-08-31, DQ-T64 (a): "fix the description first. It claims one call for a
pipeline that needs at least two with a human approval between."

🔴 THE FALSEHOOD EXPLAINED EVERY NUMBER ON THE ROW. Driven directly, no model in the loop:

    op=start        -> plan_ready   "Show the user this worklist; call op=approve_plan"
    op=approve_plan -> building     op=status x7 -> proposed, glossary_entities: 2
    op=project_kg   -> edges_ready  op=approve_edges -> done, edges_applied 2

and across 93 recorded sessions op=approve_plan has been called ZERO times — every recorded
call is `start` (78) or a confirm card (18). A model told the work takes ONE call has no reason
to come back for the second, so it reports the worklist and the turn ends. That is the tool
doing exactly what it said, and the author getting no cast: 0 of 80 turns ever produced one.

WHAT THIS DOES NOT CLAIM. Fixing the sentence does not make the model traverse the protocol —
that is measured separately and is a different question. It removes the reason it had not to.
"""
from __future__ import annotations

import re

from app.mcp import server as mcp


def _description() -> str:
    """The tool's registered description, as the model receives it.

    🔴 COMMENT LINES ARE STRIPPED FIRST, AND THE FIRST VERSION DID NOT. It joined every quoted
    run in the block, so my own explanatory comment — which QUOTES the phrase it was deleting,
    `"in ONE call"` — was read as part of the description and the guard failed against a fix
    that was correct. A comment is invisible to the model; an extractor that cannot tell them
    apart measures the file, not the surface.
    """
    src = open(mcp.__file__, encoding="utf-8").read()
    i = src.index('name="composition_build_cast_and_graph"')
    j = src.index("meta=require_meta", i)
    block = src[i:j]
    body = block[block.index("description=("):]
    code = "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith("#"))
    # JOINED WITH "" — Python concatenates adjacent literals with NO separator, and
    # joining with a space split "CALL THE " + "NEXT OP" into a phrase that matched
    # nothing. The extractor must reproduce the string the model receives.
    return "".join(re.findall(r'"([^"]*)"', code))


class TestItDoesNotPromiseOneCall:
    def test_the_words_one_call_are_gone(self):
        d = _description().lower()
        assert "in one call" not in d, (
            "the description still promises a single call for a five-call, two-gate protocol")

    def test_it_says_start_writes_nothing(self):
        """The precise falsehood the model acted on: it believed `start` had done the work."""
        d = _description()
        assert "op='start' WRITES NOTHING" in d or "start' WRITES NOTHING" in d

    def test_it_names_the_two_gates(self):
        d = _description()
        assert "approve_plan" in d and "approve_edges" in d
        assert "MULTI-STEP" in d.upper()

    def test_it_tells_the_caller_to_follow_next(self):
        """Every op returns a `next` field naming the call that follows; the 0-of-93 says
        nothing was following it."""
        d = _description()
        assert "`next`" in d or "next` field" in d
        assert "CALL THE NEXT OP" in d.upper()

    def test_it_still_leads_with_the_callers_own_phrasing(self):
        """ANTI-REGRESSION. The 2026-08-25 rewrite exists because the tool was INDISTINCT —
        surfaced 5/5, called 0/5 — and it was fixed by leading with the words the caller uses.
        A correction that buries that under protocol prose would trade one defect for the one
        before it."""
        d = _description()
        assert d.index("KNOWLEDGE GRAPH") < d.index("MULTI-STEP")
        assert "build the knowledge graph" in d


class TestTheOpListStillMatchesTheProtocol:
    def test_every_op_the_protocol_uses_is_documented(self):
        d = _description()
        for op in ("start", "approve_plan", "status", "project_kg", "approve_edges", "cancel"):
            assert op in d, f"op {op} is not documented"

    def test_the_synonyms_were_not_touched(self):
        """DQ-T70's cost: a synonym change manufactures ties. This ruling was about the
        DESCRIPTION only, and the answerability layer was already measured to be doing
        everything it can for this prompt."""
        src = open(mcp.__file__, encoding="utf-8").read()
        i = src.index('name="composition_build_cast_and_graph"')
        raw = src[i:src.index("async def composition_build_cast_and_graph", i)]
        # Comments stripped for the same reason as in `_description`: the note RECORDING the
        # 2026-08-25 removal quotes the removed synonym, and reading it as a live declaration
        # made this guard fail against a tree that is correct.
        block = chr(10).join(
            ln for ln in raw.splitlines() if not ln.lstrip().startswith("#"))
        for syn in ("build my world", "set up the glossary", "create the cast",
                    "extract the cast from my story"):
            assert syn in block
        assert "build the knowledge graph\"" not in block, (
            "the synonym removed in 2026-08-25 for tying with kg_build is back")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
