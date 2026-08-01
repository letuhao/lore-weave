"""`PGN-A2` closed end to end — the brief's coverage is ASSERTED, not assumed.

The v1 defect this replaces: a ``schema_fingerprint`` comparison is green for a
brief with **zero questions**, because deleting a question row moves neither
operand. Every test here is about the half that can actually fail.

No DB, no port, no network — deliberately no ``xdist_group`` mark.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.gamegen.brief import (
    SCHEMA_CONTRACT,
    Brief,
    BriefCoverageError,
    Question,
    assert_covers,
    load_brief,
    load_contract,
    required_paths,
)


@pytest.fixture(scope="module")
def contract() -> dict:
    return load_contract()


# ── the contract is the engine's, not ours ──────────────────────────────────


def test_the_contract_is_generated_and_present(contract: dict) -> None:
    """If this file is hand-edited it stops being the engine's schema and
    becomes a second implementation of it — which is the whole thing
    ``CPL-A2`` forbids. Rust's ``the_committed_contract_matches_the_code`` is
    what keeps it honest; this only asserts we are reading that artifact."""
    assert "_generated_by" in contract
    assert "cargo test" in contract["_generated_by"]
    assert len(contract["fingerprint"]) == 64
    assert len(required_paths(contract)) == 11


# ── the shipped brief ───────────────────────────────────────────────────────


def test_the_progression_brief_covers_its_schema(contract: dict) -> None:
    """The headline. ``load_brief`` asserts at LOAD, so this passing means the
    shipped question set is total against the engine's required positions."""
    brief = load_brief("progression_system", contract=contract)
    assert brief.coverage == required_paths(contract)


def test_every_closed_set_question_carries_its_options(contract: dict) -> None:
    """``PGN-A13`` — a closed-set arg gets an enum, never a free string. The
    options let the S2 gate render choices instead of a text box, which is what
    stops an answer of ``"stage-ish"`` reaching the fold."""
    brief = load_brief("progression_system", contract=contract)
    for q in brief.questions:
        if "closed set" in q.answer_shape:
            assert q.options, f"{q.id} is a closed set with no options"
            assert len(q.options) >= 2, f"{q.id} has a closed set of one"


def test_the_breakthrough_question_invites_what_the_schema_cannot_hold(
    contract: dict,
) -> None:
    """**Deliberate, and the fixture depends on it.**

    ``at_max_plus`` needs a place/item module that does not exist (`PGN-A20`),
    so the question still asks for a stated requirement. Asking is what lets the
    pipeline **refuse by name** rather than silently emit ``at_max`` — 陳玄一's
    cold pool is exactly this case.
    """
    brief = load_brief("progression_system", contract=contract)
    q = next(q for q in brief.questions if q.path == "kind.tier[].breakthrough")
    assert "REQUIREMENT" in q.ask
    assert "cannot yet express" in q.ask


def test_the_tier_name_question_asks_for_a_PATTERN(contract: dict) -> None:
    """``PGN-A11`` — the approval unit is the assertion class. Asking for 15
    names is 15 decisions; asking for the pattern once is one, and the fold
    expands it deterministically."""
    brief = load_brief("progression_system", contract=contract)
    q = next(q for q in brief.questions if q.path == "kind.tier[].name")
    assert "PATTERN" in q.ask


# ── the checks that can fail ────────────────────────────────────────────────


def _brief(paths: list[str], fingerprint: str) -> Brief:
    return Brief(
        element_kind="test",
        schema_fingerprint=fingerprint,
        questions=tuple(
            Question(id=f"q{i}", path=p, ask="?", answer_shape="prose")
            for i, p in enumerate(paths)
        ),
    )


def test_a_missing_question_is_refused(contract: dict) -> None:
    """The v1 case: a brief that never asks about a required position. v1's
    fingerprint could not see this — deleting a row moved neither operand."""
    want = sorted(required_paths(contract))
    with pytest.raises(BriefCoverageError) as e:
        assert_covers(_brief(want[1:], contract["fingerprint"]), contract)
    assert want[0] in str(e.value)
    assert "default nobody chose" in str(e.value)


def test_an_EMPTY_brief_is_refused(contract: dict) -> None:
    """The extreme of the same case, spelled out because it is the one v1 was
    provably green for."""
    with pytest.raises(BriefCoverageError):
        assert_covers(_brief([], contract["fingerprint"]), contract)


def test_a_question_for_a_position_the_engine_does_not_want_is_refused(
    contract: dict,
) -> None:
    """Set equality runs BOTH ways. A reviewer facing ~29 decisions must not
    spend one on a position the engine will never read."""
    paths = sorted(required_paths(contract)) + ["kind.invented_by_a_helpful_author"]
    with pytest.raises(BriefCoverageError) as e:
        assert_covers(_brief(paths, contract["fingerprint"]), contract)
    assert "does not list as required" in str(e.value)


def test_two_questions_for_one_position_are_refused(contract: dict) -> None:
    """Two chances to answer one position differently, and nothing downstream
    can say which answer won."""
    paths = sorted(required_paths(contract))
    with pytest.raises(BriefCoverageError) as e:
        assert_covers(_brief(paths + [paths[0]], contract["fingerprint"]), contract)
    assert "more than once" in str(e.value)


def test_a_moved_schema_fingerprint_is_refused(contract: dict) -> None:
    """A brief authored against an older schema. The positions may still line
    up by name while a position was RECLASSIFIED underneath them — which is how
    a question disappears without the list getting shorter, and why the
    fingerprint covers `askable` and not just membership."""
    stale = _brief(sorted(required_paths(contract)), "0" * 64)
    with pytest.raises(BriefCoverageError) as e:
        assert_covers(stale, contract)
    assert "schema MOVED" in str(e.value)
    assert "reclassified" in str(e.value)


def test_a_missing_contract_says_how_to_regenerate_it(tmp_path) -> None:
    """And says not to re-derive it here, because that is the mirror-nothing-
    forces-to-agree defect one tier up."""
    with pytest.raises(BriefCoverageError) as e:
        load_contract(tmp_path / "nope.json")
    assert "REGEN_PROGRESSION_SCHEMA" in str(e.value)
    assert "never re-derive" in str(e.value)


# ── the shipped artifact stays in sync with the engine ──────────────────────


def test_the_shipped_brief_records_the_CURRENT_fingerprint(contract: dict) -> None:
    """A brief whose fingerprint is stale would be refused at load — this makes
    the failure a clear one line rather than a coverage message, so a schema
    change reads as *"the schema moved"* rather than *"someone deleted a
    question"*."""
    raw = json.loads(
        (SCHEMA_CONTRACT.parent.parent
         / "services/lore-enrichment-service/app/gamegen/briefs/progression_system.json"
         ).read_text(encoding="utf-8")
    )
    assert raw["schema_fingerprint"] == contract["fingerprint"], (
        "the shipped brief was authored against an older schema. Re-read "
        "contracts/progression-schema.json, update the questions, then update this "
        "fingerprint - in that order, because updating it first makes the check vacuous."
    )
