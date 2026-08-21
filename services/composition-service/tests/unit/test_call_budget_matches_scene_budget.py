"""The generalised call-budget seam must never undercut the measured original.

`scene_output_budget` is the implementation the SDK's `call_budget(PROSE, ...)`
generalises; its docstring records the Mị Đế measurements that produced it (targets of
900/850/800/750/800 words coming back as 445/414/532/618/736 because the wire allowed
1024 tokens). The seam may be MORE generous — its per-kind floor makes it so for small
targets — but a migration that shrank any call site's budget would introduce truncation
and make every later regression ambiguous.

Lives here, not in the SDK suite: the assertion spans a service function and an SDK
function, and only this side can import both.
"""
from __future__ import annotations

import pytest
from loreweave_llm.budget import OutputKind, call_budget
from loreweave_llm.reasoning import ReasoningDirective

from app.engine.cowrite import scene_output_budget


def _directive(effort: str | None) -> ReasoningDirective:
    return ReasoningDirective(effort=effort, passthrough=False, source="test")


@pytest.mark.parametrize("words", [200, 500, 900, 1500, 3000])
@pytest.mark.parametrize("lang", ["vi", "en", "zh", "ja"])
@pytest.mark.parametrize("effort", [None, "low", "medium", "high"])
def test_prose_never_undercuts_the_implementation_it_generalises(words, lang, effort):
    """`scene_output_budget` is the measured original (its docstring records the Mị Đế
    numbers that produced it). The generalisation may be more generous — the floor makes
    it so for small targets — but never less."""
    reasoning = _directive(effort)
    generalised = call_budget(
        OutputKind.PROSE, target=words, language=lang, reasoning=reasoning,
    ).max_output_tokens
    original = scene_output_budget(words, lang, reasoning=reasoning)
    assert generalised >= original, (
        f"{words}w/{lang}/effort={effort}: seam {generalised} < original {original}"
    )
