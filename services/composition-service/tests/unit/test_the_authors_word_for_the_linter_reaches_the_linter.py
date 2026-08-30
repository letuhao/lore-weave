"""D-THE-AUTHORS-WORD-FOR-THE-LINTER-REACHES-NO-TOOL.

    THE INVARIANT. If the product calls a capability "the golden linter" in the tool's own
    description, the author's word for it must reach that tool.

`plan_validate`'s description has read "run the S1-S8 golden linter" since it shipped. R1
answerability reads `synonyms`, not the description, so measured against `answerable_tools`:

    "Run the golden linter on this plan."   ->  set()        <- reached NOTHING
    "run the linter"                        ->  set()
    "lint the plan"                         ->  set()
    "validate plan"                         ->  {plan_validate}
    "check the golden rules"                ->  {plan_validate}

THIS IS THE SURFACE HALF of D-THE-PROBLEMS-PANEL-IS-REPORTED-AS-THE-GOLDEN-LINTER, filed
separately because that row explicitly refuses it as its own remedy: "a surface fix would stop
this instance without touching the behaviour". Asked for the linter, the model reached for
composition_diagnostics — the problems panel — and reported its output as the linter's, on 5 of 5
runs with plan_validate advertised 0 of 5. On the same book, given the linter, it used the linter
and only the linter: ten calls across five sessions, the panel untouched. The model tells them
apart perfectly well when it can see both; it could not see one of them.

🔴 PRECISION IS THE RISK, NOT RECALL. A synonym that steals a neighbour's request is worse than a
missing one, and `composition_diagnostics` is the neighbour. Asserted below: with these synonyms
added, "show me the problems panel" still resolves to the panel alone.
"""
from __future__ import annotations

import pathlib
import re

SRC = (pathlib.Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py").read_text(
    encoding="utf-8")


def _plan_validate_block() -> str:
    i = SRC.index('name="plan_validate"')
    return SRC[i:SRC.index("async def plan_validate", i)]


class TestTheAuthorsWordIsDeclared:
    def test_linter_is_a_declared_synonym(self):
        block = _plan_validate_block()
        for word in ('"golden linter"', '"linter"', '"lint the plan"'):
            assert word in block, (
                f"plan_validate no longer declares {word} — the author's own name for this "
                "capability goes back to reaching no tool at all")

    def test_the_original_synonyms_are_KEPT(self):
        """Additive only. `validate plan` and `check the golden rules` already resolved here and
        a fix that traded one phrasing for another would move the gap, not close it."""
        block = _plan_validate_block()
        for word in ('"validate plan"', '"check spec"', '"golden rules"'):
            assert word in block, word

    def test_the_description_still_says_golden_linter(self):
        """The declaration and the prose have to agree. If the description stops calling it a
        linter, these synonyms become the thing that is wrong."""
        assert "golden linter" in _plan_validate_block()


class TestItDoesNotSTEALTheNeighboursRequest:
    """🔴 THE PRECISION HALF. composition_diagnostics is the tool the model wrongly reached for;
    a synonym that pulled ITS requests to plan_validate would swap one misattribution for the
    reverse one."""

    def test_the_panels_own_words_are_not_claimed_here(self):
        block = _plan_validate_block()
        for word in ("problems panel", "diagnostics", "problems"):
            assert f'"{word}"' not in block, (
                f"plan_validate now declares {word!r}, which belongs to composition_diagnostics")

    def test_the_panel_still_declares_its_own(self):
        i = SRC.index('name="composition_diagnostics"')
        block = SRC[i:SRC.index("async def composition_diagnostics", i)]
        assert re.search(r"problems|diagnostic", block), (
            "composition_diagnostics lost its own vocabulary — this fix must not have taken it")


class TestTheSynonymsAreNotVacuous:
    def test_they_are_multi_word_or_specific(self):
        """A one-word synonym that is common English would fire on ordinary prose. `linter` is a
        term of art and is safe; the other two are phrases. Asserted so a later edit cannot slip
        a generic word in beside them."""
        block = _plan_validate_block()
        for word in ('"check"', '"plan"', '"run"', '"validate"'):
            assert word not in block, (
                f"a bare {word} would fire on ordinary prose and force this tool onto turns that "
                "never asked for it")
