"""`PGN-A9` — the hash is a promise about the evidence, and the promise is total.

No DB, no port, no network — deliberately no ``xdist_group`` mark.

Every test here is written to be able to fail. The one that carries the most
weight is :func:`test_the_hash_covers_every_field_of_the_evidence`, which is the
`NV-3` guard: a hand-listed set of hashed fields is *default-uncovered*, so a
field added tomorrow would sit outside the promise while the hash kept verifying.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.gamegen.answer_hash import (
    HASHED_FIELDS,
    NOT_STATED_REASONS,
    UNHASHED_FIELDS,
    AnswerEvidence,
    AnswerShapeError,
    Citation,
    answer_hash,
    assert_fields_are_partitioned,
    says_json,
)

SEAL = "0191f2a0-0000-7000-8000-000000000001"
CHUNK_A = "0191f2a0-0000-7000-8000-00000000000a"
CHUNK_B = "0191f2a0-0000-7000-8000-00000000000b"


def cited(**kw) -> AnswerEvidence:
    base = dict(
        question_id="q_tier_count",
        target_ref="kind:internal_energy",
        value="stage",
        says=(Citation(CHUNK_A, 10, 16, "內功分為九層"),),
        proposed_text=None,
        not_stated=False,
        not_stated_reason=None,
        verified_against_seal_id=SEAL,
    )
    base.update(kw)
    return AnswerEvidence(**base)


def silent(**kw) -> AnswerEvidence:
    base = dict(
        question_id="q_cap_rule",
        target_ref="kind:comprehension",
        value=None,
        says=(),
        proposed_text=None,
        not_stated=True,
        not_stated_reason="absent_from_corpus",
        verified_against_seal_id=None,
    )
    base.update(kw)
    return AnswerEvidence(**base)


# ── the NV-3 guard ──────────────────────────────────────────────────────────


def test_the_hash_covers_every_field_of_the_evidence() -> None:
    """**The one that matters.** A hash over a hand-listed subset of a row is
    default-uncovered: add a field, forget this list, and the hash keeps
    verifying while the row means something new — which is precisely the
    retroactive rewrite `PGN-A9` exists to stop."""
    assert_fields_are_partitioned()
    assert not (HASHED_FIELDS & UNHASHED_FIELDS)


def test_the_partition_refuses_an_unclassified_field(monkeypatch) -> None:
    """The guard above passes today. This proves it CAN fail — a partition that
    only ever sees a correct input is a claim, not a check."""
    import app.gamegen.answer_hash as mod

    monkeypatch.setattr(mod, "HASHED_FIELDS", mod.HASHED_FIELDS - {"not_stated"})
    with pytest.raises(AssertionError) as e:
        mod.assert_fields_are_partitioned()
    assert "not_stated" in str(e.value)
    assert "outside the hash's promise" in str(e.value)


def test_the_partition_refuses_a_stale_entry(monkeypatch) -> None:
    import app.gamegen.answer_hash as mod

    monkeypatch.setattr(mod, "UNHASHED_FIELDS", frozenset({"a_field_that_was_removed"}))
    with pytest.raises(AssertionError) as e:
        mod.assert_fields_are_partitioned()
    assert "no longer exist" in str(e.value)


# ── what the hash separates ─────────────────────────────────────────────────


def test_a_citation_and_an_invention_of_the_same_text_hash_differently() -> None:
    """`PGN-A3`'s whole point, at the hash layer. If these collided, an
    UPDATE-free attack would still exist: swap the columns, keep the hash."""
    quote = "內功分為九層"
    extracted = cited(says=(Citation(CHUNK_A, 10, 16, quote),))
    invented = cited(says=(), proposed_text=quote, verified_against_seal_id=None)
    assert answer_hash(extracted) != answer_hash(invented)


def test_reordering_citations_changes_the_hash() -> None:
    """Order is part of the claim for an ordered list — *tier 1 is X, tier 2 is
    Y* reordered is a different assertion. Sorting the spans before hashing would
    have made those two answers indistinguishable."""
    a = Citation(CHUNK_A, 0, 2, "一層")
    b = Citation(CHUNK_A, 20, 22, "二層")
    assert answer_hash(cited(says=(a, b))) != answer_hash(cited(says=(b, a)))


def test_an_absent_field_and_an_empty_one_hash_differently() -> None:
    """The presence tag. Collapsing ``None`` to ``""`` would make *"the model
    proposed nothing"* and *"the model proposed the empty string"* the same
    answer."""
    absent = cited(proposed_text=None)
    empty = cited(proposed_text="")
    assert answer_hash(absent) != answer_hash(empty)


def test_field_contents_cannot_slide_across_the_boundary() -> None:
    """Length-prefixing, not separator-joining. With a ``|`` join these two would
    collide, and a claim about one kind could be re-read as a claim about
    another."""
    a = cited(question_id="q_a", target_ref="kind:b")
    b = cited(question_id="q_a|kind:b", target_ref="")
    assert answer_hash(a) != answer_hash(b)


def test_the_seal_is_part_of_the_promise() -> None:
    """An answer verified against a DIFFERENT corpus seal is a different answer.
    Otherwise a citation checked against one snapshot could be re-attributed to
    another with the hash still matching."""
    other = "0191f2a0-0000-7000-8000-0000000000ff"
    assert answer_hash(cited()) != answer_hash(cited(verified_against_seal_id=other))


def test_the_hash_is_stable_and_64_hex() -> None:
    h = answer_hash(cited())
    assert h == answer_hash(cited())
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


# ── the shape rules, each with its own failure ──────────────────────────────


def test_a_citation_with_no_seal_is_refused() -> None:
    """`PGN-A14` — a citation nobody could have checked."""
    with pytest.raises(AnswerShapeError) as e:
        answer_hash(cited(verified_against_seal_id=None))
    assert "PGN-A14" in str(e.value)


def test_a_zero_width_span_is_refused() -> None:
    """It verifies against the empty string, i.e. against anything."""
    with pytest.raises(AnswerShapeError) as e:
        answer_hash(cited(says=(Citation(CHUNK_A, 10, 10, ""),)))
    assert "empty or backwards" in str(e.value)


def test_overlapping_spans_on_one_chunk_are_refused() -> None:
    """The shape that kills citing one span 24 times for 24 tier names: one piece
    of evidence dressed as N."""
    with pytest.raises(AnswerShapeError) as e:
        answer_hash(
            cited(says=(Citation(CHUNK_A, 0, 30, "一" * 30), Citation(CHUNK_A, 20, 50, "二" * 30)))
        )
    assert "OVERLAP" in str(e.value)


def test_the_same_span_on_a_different_chunk_is_fine() -> None:
    """Disjointness is per chunk. Two books can say the same thing at the same
    offset, and refusing that would be a false positive with no story."""
    answer_hash(cited(says=(Citation(CHUNK_A, 0, 30, "一" * 30), Citation(CHUNK_B, 0, 30, "一" * 30))))


def test_a_not_stated_answer_carrying_citations_is_refused() -> None:
    with pytest.raises(AnswerShapeError) as e:
        answer_hash(silent(says=(Citation(CHUNK_A, 0, 5, "xxxxx"),), verified_against_seal_id=SEAL))
    assert "PGN-A4" in str(e.value)


def test_a_not_stated_answer_hiding_a_proposal_is_refused() -> None:
    """The interesting one: `not_stated` is the ~2-second click and a citation is
    ~60–90 s, so a proposal filed under a silence is the cheap path that also
    launders an invention."""
    with pytest.raises(AnswerShapeError) as e:
        answer_hash(silent(proposed_text="nine tiers, probably"))
    assert "hides an invention behind a silence" in str(e.value)


@pytest.mark.parametrize("reason", sorted(NOT_STATED_REASONS))
def test_every_closed_set_reason_is_accepted(reason: str) -> None:
    answer_hash(silent(not_stated_reason=reason))


def test_a_free_text_not_stated_reason_is_refused() -> None:
    with pytest.raises(AnswerShapeError) as e:
        answer_hash(silent(not_stated_reason="couldn't find it"))
    assert "not one of" in str(e.value)


def test_a_not_stated_answer_with_no_reason_is_refused() -> None:
    with pytest.raises(AnswerShapeError):
        answer_hash(silent(not_stated_reason=None))


def test_an_answer_that_states_nothing_is_refused() -> None:
    """No citation, no proposal, not marked silent. S3's consumption ledger would
    faithfully record it as consumed."""
    with pytest.raises(AnswerShapeError) as e:
        answer_hash(cited(says=(), verified_against_seal_id=None))
    assert "states nothing" in str(e.value)


def test_a_reason_without_not_stated_is_refused() -> None:
    with pytest.raises(AnswerShapeError):
        answer_hash(cited(not_stated_reason="absent_from_corpus"))


# ── the JSONB form travels with the hash ────────────────────────────────────


def test_says_json_matches_what_the_db_check_expects() -> None:
    """``gamegen_says_wellformed`` requires ``chunk_id`` + a two-element numeric
    ``span`` + a non-empty ``quote``. This is the Python side of that shape, kept
    in the same module as the hash so the two cannot drift apart."""
    rendered = says_json((Citation(CHUNK_A, 10, 16, "內功分為九層"),))
    assert rendered == [{"chunk_id": CHUNK_A, "span": [10, 16], "quote": "內功分為九層"}]


def test_the_hash_ignores_nothing_it_claims_to_cover() -> None:
    """Every hashed field, changed one at a time, moves the digest. Written as a
    sweep rather than one assertion per field so a field added to
    ``HASHED_FIELDS`` is covered the moment it is listed — an enumerated test list
    would be default-uncovered in exactly the way the partition guard is not."""
    base = cited(
        says=(Citation(CHUNK_A, 10, 16, "內功分為九層"),),
        proposed_text="a proposal",
    )
    h0 = answer_hash(base)
    mutations = {
        "question_id": {"question_id": "q_other"},
        "value": {"value": "attribute"},
        "target_ref": {"target_ref": "kind:swordsmanship"},
        "says": {"says": (Citation(CHUNK_A, 10, 16, "內功分為八層"),)},
        "proposed_text": {"proposed_text": "a different proposal"},
        "verified_against_seal_id": {
            "verified_against_seal_id": "0191f2a0-0000-7000-8000-00000000beef"
        },
        # not_stated cannot vary alone (it drags the whole shape with it), so it
        # is exercised as the legal silent answer against the cited one.
        "not_stated": None,
        "not_stated_reason": None,
    }
    assert set(mutations) == HASHED_FIELDS, (
        "a field was added to HASHED_FIELDS with no mutation here, so nothing proves "
        "the hash actually reads it"
    )
    for field, kw in mutations.items():
        if kw is None:
            continue
        assert answer_hash(replace(base, **kw)) != h0, f"changing {field} did not move the hash"

    # the two shape-locked fields, exercised as whole answers
    assert answer_hash(silent()) != answer_hash(silent(not_stated_reason="contradicted"))
