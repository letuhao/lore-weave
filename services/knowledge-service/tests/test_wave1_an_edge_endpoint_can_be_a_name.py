"""DQ-T76 (f) WAVE 1 — an edge endpoint can be given by NAME.

Owner ruling 2026-09-01 approved (f) "remove ids from the model surface, name in / handle
through", requiring a written migration first. Wave 1 is scoped by
docs/specs/2026-09-02-remove-ids-from-the-model-surface.md to `source_entity_id` (the single
argument on the platform with a genuinely unreachable supplier — advertised on 4 of the 46 calls
that passed it, 9%) and the arguments with ZERO observed suppliers. Both of kg_propose_edge's
endpoints are in that set.

🔴 THE FAILURE IS MEASURED — AND THIS DOCSTRING FIRST NAMED THE WRONG ONE. It cited "batch
c-kgedge3, 2026-08-26: on 3 of 3 edge calls the model passed the GLOSSARY entity ids", taken from
the tool's own source comment. That is UNVERIFIABLE: no c-kgedge3 file exists and there is no
2026-08-26 batch directory, and KG_ENDPOINT_NOT_NODE appears in ZERO recorded results.

WHAT IS RE-CHECKABLE, over all 53 distinct kg_propose_edge calls in the corpus:

    passed at least one endpoint id     17   (32%)
    passed NEITHER                      36   (68%)   <- the dominant failure
    wrong-family (KG_ENDPOINT_NOT_NODE)  0

So the model does not pass the WRONG id — it passes NO id, because it has no reachable way to get
one. That is exactly the ground the owner's (f) ruling rests on, and a NAME is something the model
demonstrably has: the request that triggers this tool is "record that Aldric and Mira know each
other". Wave 1 is aimed at the 68%, not at the unverifiable 3-of-3.

The rules asserted here are the plan's, and each answers a failure it names:
  ID WINS when both arrive — an id is unambiguous, a name is not.
  SAY WHICH WON — "an accept-both tool that silently prefers one is how a migration becomes a
    defect".
  AMBIGUITY REFUSES WITH THE CANDIDATES and never picks.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.tools.graph_schema_tools import KgProposeEdgeArgs  # noqa: E402

def _live(src: str, needle: str) -> bool:
    """Is `needle` on a line that ACTUALLY RUNS — not commented, not disabled?

    🔴 A PLAIN `needle in src` IS DEFEATED BY THE COMMENT MARKER USED TO DISPROVE IT. Two
    assertions in this file went GREEN against injected defects because the injection kept the
    substring: `# INJECTED-DRIFT "resolved_by": resolved_by,` still contains
    `"resolved_by": resolved_by`, and `if False and len(matches) > 1:` still contains
    `len(matches) > 1`. That is the third time this month a source-substring guard has matched
    non-behavioural text, so it is fixed once, here, rather than per assertion.

    Requires: the line is not a comment, and does not contain a disabling `if False`.
    """
    for ln in src.splitlines():
        st = ln.strip()
        if needle in st and not st.startswith("#") and "if False" not in st:
            return True
    return False


NODE_ID = "01a04107-5b4a-789c-8b22-30f17c8abb00"


def _args(**kw):
    base = {"project_id": "01a04107-5b4a-789c-8b22-30f17c8abb99", "edge_type": "knows"}
    base.update(kw)
    return KgProposeEdgeArgs(**base)


def test_a_NAME_alone_is_accepted():
    """THE POINT OF WAVE 1: the ordinary way to say it now validates."""
    a = _args(source_name="Aldric Vane", target_name="Mira Solene")
    assert a.source_name == "Aldric Vane"
    assert a.source_entity_id is None


def test_an_ID_alone_is_STILL_accepted():
    """Backward compatibility is the plan's rule: accept BOTH forms. Every existing caller —
    including the frontend, which passes ids throughout all three waves — must keep working."""
    a = _args(source_entity_id=NODE_ID, target_entity_id=NODE_ID)
    assert a.source_entity_id == NODE_ID
    assert a.source_name is None


def test_BOTH_together_is_accepted_and_the_handler_prefers_the_id():
    """The model layer must not reject a caller who supplies both; the HANDLER decides, and the
    handler prefers the id. Asserted here at the schema, and at the handler by the source check
    below."""
    a = _args(source_entity_id=NODE_ID, source_name="Aldric Vane", target_name="Mira")
    assert a.source_entity_id == NODE_ID and a.source_name == "Aldric Vane"


def test_NEITHER_is_REFUSED_at_mint():
    """🔴 THE REGRESSION MAKING THE IDS OPTIONAL WOULD OTHERWISE INTRODUCE. Before Wave 1 both
    ids were required, so a call omitting them could not validate. Optional-without-this would
    park an edge with NO endpoints instead of refusing — strictly worse than the id-only tool
    it replaced."""
    with pytest.raises(Exception) as e:
        _args(target_name="Mira Solene")
    assert "source endpoint is missing" in str(e.value)
    with pytest.raises(Exception) as e:
        _args(source_name="Aldric Vane")
    assert "target endpoint is missing" in str(e.value)
    with pytest.raises(Exception):
        _args()


def test_the_refusal_NAMES_BOTH_WAYS_IN():
    """A refusal that names only the id would teach the caller the thing Wave 1 is removing."""
    with pytest.raises(Exception) as e:
        _args(target_name="Mira")
    msg = str(e.value)
    assert "source_entity_id" in msg and "source_name" in msg
    assert "kg_add_nodes" in msg, "the refusal does not say where a node id comes from"


class TestTheHandlerRulesAreInTheCode:
    """The handler needs Neo4j and a ToolContext, so these assert the SHIPPED rules at their
    source. They are deliberately about the three behaviours the plan calls out, not about
    wording — and each names what its absence would cost."""

    @staticmethod
    def _src() -> str:
        return (pathlib.Path(__file__).resolve().parents[1]
                / "app" / "tools" / "graph_schema_tools.py").read_text(encoding="utf-8")

    def test_the_ID_WINS_when_both_arrive(self):
        src = self._src()
        i = src.index("DQ-T76 (f) WAVE 1 — NAME IN")
        block = src[i:i + 2600]
        assert 'if given_id:' in block and 'resolved_by[side] = "id"' in block, (
            "the handler no longer short-circuits on a supplied id — preferring the NAME would "
            "make a precise caller LESS precise")
        # 🔴 ANCHOR ON THE CALL, NOT THE NAME. The first version of this compared against
        # "find_entities_by_name" and matched the IMPORT line, which necessarily precedes the
        # loop — so it failed against correct code. A source check that matches non-behavioural
        # text (an import, a comment, a docstring) is the trap this file has now hit once and
        # the wider loop three times this month.
        assert block.index("if given_id:") < block.index("await find_entities_by_name("), (
            "the name lookup runs BEFORE the id check, so a supplied id no longer wins")

    def test_AMBIGUITY_refuses_WITH_the_candidates(self):
        block = self._src()
        assert _live(block, "KG_ENDPOINT_NAME_AMBIGUOUS"), (
            "an ambiguous name does not refuse on a line that runs")
        i = block.index("KG_ENDPOINT_NAME_AMBIGUOUS")
        window = block[max(0, i - 900):i + 300]
        assert _live(window, "len(matches) > 1"), (
            "ambiguity is not detected on a line that runs")
        assert "candidates" in window, (
            "the refusal does not carry the candidates, so the caller cannot resolve it without "
            "guessing — and guessing writes a relationship between the wrong characters into a "
            "human's review inbox")

    def test_a_MISSING_name_refuses_distinctly(self):
        src = self._src()
        assert _live(src, "KG_ENDPOINT_NAME_NOT_FOUND"), (
            "a name that matches nothing is not distinguished from one that matches many — two "
            "different problems with two different fixes")

    def test_the_RESULT_SAYS_WHICH_FORM_WON(self):
        src = self._src()
        assert _live(src, '"resolved_by": resolved_by'), (
            "the result does not report which form resolved each endpoint. The plan's own "
            "warning: 'an accept-both tool that silently prefers one is how a migration becomes "
            "a defect.'")

    def test_the_resolution_reads_but_never_writes(self):
        """INV-K1: kg_propose_edge never writes Neo4j — the proposal is parked for human review.
        The resolver must stay a READ, or Wave 1 would break the invariant the tool exists for."""
        src = self._src()
        i = src.index("DQ-T76 (f) WAVE 1 — NAME IN")
        block = src[i:i + 2600]
        assert "find_entities_by_name" in block
        for writer in ("MERGE", "CREATE ", "run_write", "park("):
            assert writer not in block, f"the name resolution performs a write ({writer})"
