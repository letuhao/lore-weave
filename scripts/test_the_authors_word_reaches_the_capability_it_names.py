"""Two capabilities the author names differently must reach different tools.

DQ-T77, owner 2026-08-31: "(a) ACCEPT THE BEHAVIOUR, FIX THE SURFACE -- and this is deliberately
the OPPOSITE of what the row argues. The row's own natural experiment is why: the model
distinguishes the two tools perfectly when it holds both, so the misattribution is not a habit
but what it does when the capability the author named is ABSENT."

    THE INVARIANT. The author's own word for a capability reaches the tool that owns it, and
    reaches no other.

🔴 WHY A REPLY-SIDE DETECTOR IS NOT THE ANSWER, measured twice before this shipped:
  * A TOOL-IDENTIFIER matcher scores ZERO on the founding instance. The reply misattributes to
    "the linter" -- the PRODUCT's word -- and never says `plan_validate`.
  * A DECLARED-SYNONYM matcher flags 607 of 1,463 runs (41.5%). Its top phrases are replies that
    legitimately DISCUSS a capability: 'read the book' 187, 'story bible' 181.
  Identifiers never fire; product words fire on everything. Both were built, measured, reverted.

THE FOUNDING INSTANCE. Asked to run the golden linter, the model called composition_diagnostics
-- the problems panel -- and reported its output as the linter's: "The plan doesn't quite pass the
linter yet. There are 3 warnings currently flagged". plan_validate was advertised 0 of 5 and
called 0 of 5. On the same book plan_validate returned passed=TRUE while the diagnostics-based
reply said the plan does not pass: OPPOSITE verdicts, and the author was told the stricter one ran.
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

#: The author's words for each capability, and the ONE tool each must reach.
OWNED_VOCABULARY = {
    "plan_validate": [
        "Run the golden linter on my plan for this book and tell me which rules pass.",
        "Run the golden linter.",
        "Is my plan passing the linter?",
        "lint the plan",
    ],
    "composition_diagnostics": [
        "Show me the problems panel.",
    ],
}


@pytest.fixture(scope="module")
def defs():
    raw = json.loads(CACHE.read_text(encoding="utf-8"))
    d = [{"type": "function", "function": {
        "name": n, "description": t.get("description") or "",
        "parameters": t.get("inputSchema") or {}, "_meta": t.get("meta") or {}}}
        for n, t in raw.items()]
    # Adapter controls, raising rather than warning: "nothing matched" is what a broken
    # conversion says, and it is also this file's failure mode.
    if "glossary_propose_translation" not in answerable_tools(
            "Give me vietnamese names for these characters", d):
        pytest.fail("ADAPTER BROKEN — the positive control did not match")
    if answerable_tools("hello, how are you today", d):
        pytest.fail("ADAPTER BROKEN — chitchat matched something")
    return d


@pytest.mark.parametrize(
    ("tool", "phrasing"),
    [(t, p) for t, ps in OWNED_VOCABULARY.items() for p in ps],
)
def test_the_authors_word_reaches_its_own_tool(defs, tool, phrasing):
    got = answerable_tools(phrasing, defs)
    assert tool in got, (
        f"{phrasing!r} does not reach {tool} — it answers {sorted(got) or 'NOTHING'}. When the "
        "capability the author named is absent, the model answers from a DIFFERENT tool and "
        "attributes the verdict to the one it did not run.")


@pytest.mark.parametrize(
    ("tool", "phrasing"),
    [(t, p) for t, ps in OWNED_VOCABULARY.items() for p in ps],
)
def test_it_reaches_NO_OTHER_capability(defs, tool, phrasing):
    """🔴 THE SEPARATION IS THE POINT, not merely the reach. The two checks are not
    interchangeable — plan_validate returns `passed` over the HARD S1-S8 rules, while
    composition_diagnostics ranks contradictions and staleness — and on the same book they
    returned OPPOSITE verdicts. A phrasing that reaches both hands the model the same choice it
    got wrong."""
    others = set(OWNED_VOCABULARY) - {tool}
    got = set(answerable_tools(phrasing, defs))
    assert not (got & others), (
        f"{phrasing!r} reaches {sorted(got & others)} as well as {tool}. These capabilities give "
        "opposite verdicts on the same book, so a tie here is the defect's own condition.")


def test_the_vocabulary_is_declared_not_merely_matched(defs):
    """A phrase that resolves only because of a description keyword is a coincidence a reword
    breaks. The author's word must be in the tool's own declared synonyms."""
    raw = json.loads(CACHE.read_text(encoding="utf-8"))
    syns = [s.lower() for s in ((raw["plan_validate"].get("meta") or {}).get("synonyms") or [])]
    assert any("linter" in s for s in syns), (
        f"plan_validate does not DECLARE the author's word: {syns}. It reached the tool by some "
        "other route, which a rewording removes.")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
