"""D-READ-TURN-REACHES-FOR-WRITES — a question must not spend a standing write grant.

MEASURED ACROSS TWO BATCHES, 2026-08-14, K=3 each:

  "Who is Mira Solene?"
      -> attempted Tier-A WRITES on 3 of 3 runs: glossary_entity_set_attributes x2,
         kg_project_create x1.
  "How far along is the translation for this book?"
      -> called translation_start_job AND translation_retranslate_dirty on 3 of 3, both
         returning ok=true / call_outcome=done (NOT gated proposals, which record ok=false),
         and the reply claimed to have started the translation and prepared "a re-translation
         for a changed segment" — over the ZERO translations the same turn had just measured.

Every one of those was gated into a confirm card ONLY because the harness clears standing
approvals before a batch. The dogfood account holds 46 standing decisions. This is the cycle-11
shape exactly: *the gate was satisfied by a decision made weeks earlier, for a call the author
never saw.*

R5 (`standing_grant_applies`) already implements the right rule and works when it fires. The hole
is its INPUT: `request_mood` is a literal matcher over phrasings, and `unknown` — its default —
lets the grant stand. Measured:

    "How far along is the translation for this book?"   -> inspect  -> grant set aside  ✓
    "Who is Mira Solene?"                               -> unknown  -> grant APPLIES    ✗
    "What canon rules have I declared for this book?"   -> unknown  -> grant APPLIES     ✗

THE INVARIANT: a guess that gates a safety default must fail SAFE. Widening the phrase list would
fix those two sentences and leave the class — the next unrecognised question is the next incident.
So the second signal is the platform's OWN declaration, the one R1 already trusts to decide the
surface: if every tool whose declared vocabulary matches the request is a READ, the request's own
words say it is a question, whatever the phrasing matcher made of it.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.request_mood import request_mood, standing_grant_applies  # noqa: E402
from app.services.tool_surface import answerable_tools  # noqa: E402

SRC = (pathlib.Path(__file__).resolve().parents[1]
       / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")


def _tool(name: str, tier: str, synonyms: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": name,
        "_meta": {"tier": tier, "synonyms": synonyms, "scope": "book"},
    }}


CATALOG = [
    _tool("memory_recall_entity", "R", ["who is", "tell me about the character"]),
    _tool("composition_list_canon_rules", "R", ["canon rules", "invariants"]),
    _tool("glossary_entity_set_attributes", "A", ["set attributes", "update entity details"]),
    _tool("book_chapter_create", "W", ["add a chapter", "create a chapter"]),
]


def _reads_only(text: str) -> bool:
    """The predicate the turn computes, rebuilt from the same public pieces."""
    from app.services.tool_discovery import tool_tier
    idx = {t["function"]["name"]: t for t in CATALOG}
    ans = answerable_tools(text, CATALOG)
    return bool(ans) and all(n in idx and tool_tier(idx[n]) == "R" for n in ans)


class TestTheMoodMatcherReallyMissesThese:
    """CONTROL. If `request_mood` started classifying these as `inspect`, the declaration arm
    would be untested — passing for a reason that has nothing to do with the fix."""

    def test_the_two_measured_questions_are_unknown_to_the_mood_matcher(self):
        assert request_mood("Who is Mira Solene?") == "unknown"
        assert request_mood("What canon rules have I declared for this book?") == "unknown"

    def test_and_unknown_lets_a_standing_write_grant_stand(self):
        assert standing_grant_applies("unknown", kind="mutation") is True, (
            "this is the fail-OPEN default the declaration arm exists to close"
        )

    def test_the_phrasing_it_does_catch_still_works(self):
        """VERBATIM, because the difference matters and this test caught me shortening it. The
        measured prompt carries a trailing clause, and WITHOUT it the same sentence falls to
        `unknown` too — which is itself the point: the matcher keys on phrasings, so a sentence
        that reads identically to a person can land on either side of the consent boundary."""
        measured = ("How far along is the translation for this book — what's the coverage so far?")
        assert request_mood(measured) == "inspect"
        assert standing_grant_applies("inspect", kind="mutation") is False
        assert request_mood("How far along is the translation for this book?") == "unknown", (
            "dropping the trailing clause moves it to unknown — a phrasing matcher cannot be "
            "the only signal, which is the argument for the declaration arm"
        )


class TestTheDeclarationArmCoversWhatThePhrasingMissed:
    def test_the_measured_questions_are_reads_only(self):
        """THE FALSIFIER. Both fell through the mood matcher; both are unambiguously questions
        by the declaration of the tools their own words reach."""
        assert _reads_only("Who is Mira Solene?") is True
        assert _reads_only("What canon rules have I declared for this book?") is True

    def test_a_matched_write_stands_the_whole_thing_down(self):
        """"Add a chapter called X" reaches a CREATE tool's declaration. That is a construct
        turn and its standing grant must be untouched — a guard that blocks writes on write
        requests is worse than the defect."""
        assert _reads_only("Add a chapter called The Ember Codex") is False

    def test_a_mixed_match_is_not_reads_only(self):
        """One write in the matched set is enough. The rule is ALL, not most — a turn whose
        words reach a write has asked for one."""
        assert _reads_only("update entity details and tell me about the character") is False

    def test_chitchat_matches_nothing_and_changes_nothing(self):
        """EMPTY must never mean 'reads only', or every unrecognised sentence would silently
        revoke consent the user did grant."""
        assert _reads_only("thanks, that is great") is False
        assert _reads_only("") is False


class TestItIsWiredWhereConsentIsDECIDED:
    """CALL-SITE GUARDS. The predicate is inert unless `_decision_check` consults it."""

    def test_the_turn_computes_the_predicate(self):
        assert "_turn_reads_only = bool(_turn_answerable) and all(" in SRC
        assert "answerable_tools(user_message_content" in SRC

    def test_the_consent_check_consults_it(self):
        i = SRC.index("async def _decision_check(")
        block = SRC[i:i + 2200]
        assert "_reads_only_block" in block
        assert "_turn_reads_only" in block

    def test_a_deny_is_never_set_aside(self):
        """THE SAFETY PROPERTY, unchanged: a standing refusal must hold in every mood. The
        early return must come BEFORE any set-aside logic."""
        i = SRC.index("async def _decision_check(")
        block = SRC[i:i + 2200]
        deny = block.index('if _decision != "allow":')
        aside = block.index("_reads_only_block")
        assert deny < aside, "the deny short-circuit must precede the set-aside"

    def test_it_only_touches_the_mutation_axis(self):
        """`spend` already fails closed. Widening a second consent axis on this evidence would
        assert more than was measured."""
        i = SRC.index("async def _decision_check(")
        block = SRC[i:i + 2200]
        assert 'kind == "mutation" and _turn_reads_only' in block

    def test_the_set_aside_is_logged_with_its_reason(self):
        """Two independent signals can now set a grant aside; a log that does not say WHICH is
        how the next debugging session loses a day."""
        i = SRC.index("async def _decision_check(")
        block = SRC[i:i + 2200]
        assert "answerable-are-all-reads=%s" in block
