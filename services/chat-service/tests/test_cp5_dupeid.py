"""TOOL-V2 LOOP #5 — one id in two different id fields.

🔴 **MEASURED ACROSS THE WHOLE CORPUS: 135 calls over 7 tools and 19 sessions send the same UUID into two
distinct `*_id` parameters, and NOT ONE OF THEM SUCCEEDED.**

    glossary_get_entity          book_id == entity_id            71 calls / 5 sessions
    book_chapter_save_draft      book_id == chapter_id           38 / 6
    book_chapter_delete          book_id == chapter_id           14 / 1
    composition_create_work      book_id == project_id            5 / 1
    glossary_list_chapter_links  book_id == entity_id             2 / 2
    glossary_propose_entity_edit book_id == entity_id             2 / 2
    kg_propose_edge              source_entity_id == target_...   1 / 1

Zero successes in 135 is the falsifier for the RULE, not just for the code: one legitimate call
of this shape would be a counter-example, and the corpus contains none.

**Two causes, one fatal shape.** In `book_chapter_delete` the shared value is a REAL BOOK ("The
Tidewright") — the model had the book id, lacked a chapter id, and filled the field it lacked
with the one it had. In `glossary_get_entity` the shared value is neither a book nor an entity —
an id invented whole. Both are well-formed UUIDs, so the schema passes, `looks_like_an_id` says
no resolution is needed, and `_inject_context_ids` deliberately honours a valid-but-different id
as a cross-book call. Nothing in the runtime could see it.

**And it died naming the wrong thing.** `book_chapter_delete` was answered *"book not
accessible"* for a book that was perfectly accessible. `glossary_get_entity` was answered
*"entity not accessible"*, which reads as a permission problem for a row that does not exist.
One session repeated its version 14 times; another repeated its version 71.
"""
from __future__ import annotations

import pathlib

from app.agentruntime.toolcontract import (
    duplicate_identifier, duplicate_identifier_message,
)

BOOK = "019f82b6-c31b-72e9-bf2a-3f37f4c8a847"      # "The Tidewright", a real book
OTHER = "019fea5a-4ef0-74ee-a5c3-4bb3b1eaf6bc"


class TestTheRecordedShapes:
    """Each case is an argument object taken from the corpus, not invented."""

    def test_THE_14_CALL_SESSION_book_chapter_delete(self):
        got = duplicate_identifier({"book_id": BOOK, "chapter_id": BOOK})
        assert got is not None
        a, b, v = got
        assert {a, b} == {"book_id", "chapter_id"}
        assert v == BOOK

    def test_THE_71_CALL_SESSION_glossary_get_entity(self):
        got = duplicate_identifier({"book_id": OTHER, "entity_id": OTHER})
        assert got is not None
        assert {got[0], got[1]} == {"book_id", "entity_id"}

    def test_A_SELF_LOOP_EDGE_IS_CAUGHT_TOO(self):
        """`kg_propose_edge` with source_entity_id == target_entity_id. The domain already
        refuses the sibling case (propose_merge: "at least one loser_id distinct from the
        winner"), so this is the same invariant one tool over."""
        got = duplicate_identifier({"project_id": "019f9d05-9e51-7779-9b03-c28cdc0cdea4",
                                    "source_entity_id": OTHER, "target_entity_id": OTHER})
        assert got is not None
        assert {got[0], got[1]} == {"source_entity_id", "target_entity_id"}


class TestWhatItMustNOTCatch:
    """The rule earns its keep by being narrow. Every case here would be a false refusal, and a
    false refusal on a WRITE is worse than the failure it replaces."""

    def test_DISTINCT_IDS_PASS(self):
        assert duplicate_identifier({"book_id": BOOK, "chapter_id": OTHER}) is None

    def test_ONE_ID_ALONE_PASSES(self):
        assert duplicate_identifier({"book_id": BOOK}) is None

    def test_A_NON_UUID_REPEAT_IS_NOT_THIS_DEFECT(self):
        """Two placeholders are iteration 3's defect, not this one, and they are already refused
        by their own checks. Claiming them here would inflate this rule's measured population
        with calls it did not fix."""
        assert duplicate_identifier(
            {"book_id": "placeholder_id", "entity_id": "placeholder_id"}) is None

    def test_A_PLURAL_LIST_IS_OUT_OF_SCOPE(self):
        """`_ids` is excluded deliberately: a batch member repeating a value is a different
        question, and iteration 1 already showed the singular/plural pair is where this family's
        confusion actually lives.

        🔴 The first version of this guard passed `entity_ids: [BOOK, BOOK]` — a LIST — and its
        falsifier could not red it, because a list value is stopped by the `type(val) is not str`
        check before the key filter ever matters. The guard was protected twice and therefore
        tested neither protection. A STRING-valued plural key is the case where the key filter is
        the only thing standing between this rule and a false refusal."""
        assert duplicate_identifier({"entity_ids": BOOK, "book_id": BOOK}) is None
        assert duplicate_identifier({"entity_ids": [BOOK, BOOK], "book_id": BOOK}) is None

    def test_A_NON_ID_FIELD_SHARING_THE_VALUE_IS_IGNORED(self):
        assert duplicate_identifier({"book_id": BOOK, "note": BOOK}) is None

    def test_THE_ARGUMENT_OBJECT_MAY_BE_ANYTHING(self):
        for junk in (None, [], "book_id", 7):
            assert duplicate_identifier(junk) is None  # type: ignore[arg-type]


class TestTheRefusalSaysWhatIsActuallyWrong:

    def test_IT_NAMES_BOTH_PARAMETERS_AND_THE_VALUE(self):
        msg = duplicate_identifier_message("book_id", "chapter_id", BOOK)
        assert "book_id" in msg and "chapter_id" in msg and BOOK in msg

    def test_IT_SAYS_THE_CALL_CANNOT_SUCCEED_AS_SENT(self):
        """The measured failure was a 14x and a 71x repeat. A message that leaves retrying open
        is what those loops were made of."""
        msg = duplicate_identifier_message("book_id", "entity_id", OTHER)
        assert "cannot succeed" in msg

    def test_IT_DOES_NOT_CLAIM_A_PERMISSION_PROBLEM(self):
        """The whole point: the old answers were "book not accessible" and "entity not
        accessible" — both false, and both sent the model looking at the wrong thing."""
        msg = duplicate_identifier_message("book_id", "chapter_id", BOOK).lower()
        assert "not accessible" not in msg


class TestItIsWiredOnBOTHDISPATCHPATHS:
    """🔴 DQ-5 is the standing lesson and it is why this class exists. The frontend branch
    refuses or suspends ~150 lines before the backend's pre-dispatch checks, which is how CP-5.3's
    resolver became unreachable for frontend tools and how the context-id injector missed them
    before that. `glossary_propose_entity_edit` is IN the measured population, so a one-sided gate
    would leave it out by construction."""

    def _src(self) -> str:
        return (pathlib.Path(__file__).resolve().parents[1] / "app" / "services"
                / "stream_service.py").read_text(encoding="utf-8")

    def test_THE_BACKEND_DISPATCH_CHECKS_IT(self):
        assert "_dupe = _dup_check(args_obj)" in self._src()

    def test_THE_FRONTEND_BRANCH_CHECKS_IT_TOO(self):
        # V6 (2026-09-03) — THE TWO PATHS BECAME ONE, so "wired on BOTH" is no longer the
        # invariant. The v1 intercept (which carried `_fe_dupe = _fe_dup_check(_fe_args)`) is
        # deleted; the three tools it guarded dispatch through the backend path now, where the
        # SAME check runs — `_dupe = _dup_check(args_obj)`.
        #
        # The defect this guards has not changed: a duplicated identifier reaching a tool is a
        # silent wrong-target write. What changed is that there is one place left to check it,
        # which is the point of the migration rather than a gap in it.
        assert "_dupe = _dup_check(args_obj)" in self._src(), (
            "the duplicate-identifier check is gone from the surviving dispatch path")

    def test_IT_RUNS_BEFORE_THE_RESOLVER_SPENDS_A_DISPATCH(self):
        """A resolver read on a call that cannot succeed either way is the cost §3a is careful
        about."""
        s = self._src()
        assert s.index("TOOL-V2 LOOP #5 · ONE ID IN TWO DIFFERENT ID FIELDS") < s.index(
            "CP-5.3 · IDENTIFIER RESOLUTION")

    def test_THE_DUPLICATE_REFUSAL_IS_TYPED_REFUSED_NOT_FAILED(self):
        """🔴 **RENAMED FROM `test_THE_REFUSAL_IS_TYPED_REFUSED_NOT_FAILED`, AND THE RENAME IS
        THE FINDING.** `_guards()` builds `{test name: suite}` across every registered suite, so
        two guards sharing a bare name SILENTLY COLLAPSE — one shadows the other and its falsifier
        is then measured against a test in a different file. CP-6.1 already owns that name, so
        this guard reported *"GREEN — the guard requires nothing"* while its falsifier was
        actually running CP-6.1's identically-named test, which the edit does not touch.

        Two more collisions exist and predate this iteration (D-5 in the runbook)."""
        assert 'instrument.stamp_refused({' in self._src()
        assert '}, "duplicate_identifier")}' in self._src()
