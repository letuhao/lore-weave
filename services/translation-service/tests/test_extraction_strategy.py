"""Tests for the per-job extraction strategy (BOOK_TO_GAME/15).

The shapes ship behind a per-JOB parameter, not a deploy flag, so two of them can run on
one book at the same time — a global flag would have to be flipped between runs, and
`BTG-A41` is the measured case of that confound (the known-entity context makes extraction
path-dependent, so a later run inherits an earlier one's discoveries).

What must hold:
  * the set is CLOSED and an unknown value RAISES — a typo that quietly ran the baseline
    would make an A/B report "no difference" for a reason unrelated to the shapes;
  * `batched` is byte-identical to the shipped behaviour, so an existing job is unaffected;
  * a single-call shape puts EVERY kind in ONE batch and gets the raised output ceiling,
    because the cap it removes was protecting against truncation.
"""
import pytest

from app.workers.extraction_prompt import (
    DELTA_INSTRUCTION,
    MAX_KINDS_PER_BATCH,
    plan_kind_batches,
)
from app.workers.extraction_strategy import (
    BATCHED,
    EDC_CITED,
    SINGLE_CALL,
    SINGLE_CALL_DELTA,
    PLANNED,
    SINGLE_CALL_SHAPES,
    STRATEGIES,
    normalize,
    output_ceiling,
    plan_batches,
    shape_hash,
)

#: Eight kinds with realistic attribute counts — the same shape the POC ran against, so
#: `batched` really does split (a 2-kind fixture would batch into one and the test would
#: pass for both strategies, proving nothing).
KINDS = [
    {"code": "character", "attributes": [{"code": f"a{i}"} for i in range(13)]},
    {"code": "location", "attributes": [{"code": f"a{i}"} for i in range(7)]},
    {"code": "item", "attributes": [{"code": f"a{i}"} for i in range(6)]},
    {"code": "event", "attributes": [{"code": f"a{i}"} for i in range(8)]},
    {"code": "terminology", "attributes": [{"code": f"a{i}"} for i in range(4)]},
    {"code": "power_system", "attributes": [{"code": f"a{i}"} for i in range(7)]},
    {"code": "organization", "attributes": [{"code": f"a{i}"} for i in range(7)]},
    {"code": "species", "attributes": [{"code": f"a{i}"} for i in range(7)]},
]
PROFILE = {k["code"]: {a["code"]: "default" for a in k["attributes"]} for k in KINDS}


# ── the closed set ───────────────────────────────────────────────────────────

def test_the_advertised_set_is_exactly_what_the_worker_implements():
    assert STRATEGIES == {BATCHED, SINGLE_CALL, SINGLE_CALL_DELTA}


def test_a_PLANNED_strategy_is_refused_rather_than_run_as_the_default():
    """No-silent-no-op: the API advertises only what the engine wires.

    Found in the live smoke, not by reading. `edc_cited` was accepted while the worker had
    no two-stage path, so it fell through to the default batching — and the proof was that
    it and `batched` both cost ZERO tokens on the same chapter, having produced the same
    extraction-cache key because they were the same shape. An A/B on that would have
    compared the control against itself and reported no difference.
    """
    assert EDC_CITED in PLANNED and EDC_CITED not in STRATEGIES
    with pytest.raises(ValueError) as exc:
        normalize(EDC_CITED)
    assert "NOT YET WIRED" in str(exc.value)


def test_planned_and_implemented_never_overlap():
    assert not (PLANNED & STRATEGIES)


def test_absent_or_blank_means_the_shipped_shape():
    for v in (None, "", "   "):
        assert normalize(v) == BATCHED


def test_case_and_whitespace_are_tolerated():
    assert normalize("  Single_Call  ") == SINGLE_CALL


def test_unknown_strategy_RAISES_rather_than_defaulting():
    """The bite test for the whole design.

    A silent fallback would make `extraction_strategy="sinlge_call"` run the baseline and
    report it as the new shape — an A/B that compares the control against itself and
    concludes there is no difference. That is the silent-no-op failure one layer down.
    """
    with pytest.raises(ValueError) as exc:
        normalize("sinlge_call")
    assert "sinlge_call" in str(exc.value)
    for known in STRATEGIES:
        assert known in str(exc.value)  # the message names the legal set


def test_the_single_call_set_is_NON_EMPTY():
    """Every `parametrize(..., sorted(SINGLE_CALL_SHAPES))` below silently becomes ZERO
    test cases if that set empties — pytest skips rather than fails, so the suite would go
    green while the shapes reverted to batched. Found by bite-testing this file: emptying
    the set turned four assertions into two skips. NV-3, the scope-never-reaches-it shape.
    """
    assert SINGLE_CALL_SHAPES, "SINGLE_CALL_SHAPES is empty — the parametrized tests below cover nothing"
    assert len(SINGLE_CALL_SHAPES) == 2


# ── batching ─────────────────────────────────────────────────────────────────

def test_batched_is_byte_identical_to_the_shipped_planner():
    assert plan_batches(BATCHED, PROFILE, KINDS) == plan_kind_batches(PROFILE, KINDS)


def test_the_fixture_actually_splits_under_batched():
    """Guards the tests below: if `batched` produced one batch on this fixture, the
    single-call assertions would hold for BOTH strategies and prove nothing."""
    assert len(plan_kind_batches(PROFILE, KINDS)) > 1
    assert all(len(b) <= MAX_KINDS_PER_BATCH for b in plan_kind_batches(PROFILE, KINDS))


@pytest.mark.parametrize("strategy", sorted(SINGLE_CALL_SHAPES))
def test_single_call_shapes_put_every_kind_in_one_batch(strategy):
    batches = plan_batches(strategy, PROFILE, KINDS)
    assert len(batches) == 1
    assert set(batches[0]) == set(PROFILE)


def test_a_kind_absent_from_metadata_is_dropped_not_invented():
    """The whitelist still applies — a profile entry with no metadata cannot reach the
    prompt, or the schema builder would be asked for a kind it cannot describe."""
    profile = {**PROFILE, "ghost_kind": {"a": "default"}}
    assert "ghost_kind" not in plan_batches(SINGLE_CALL, profile, KINDS)[0]


# ── output ceiling ───────────────────────────────────────────────────────────

def test_batched_keeps_the_per_batch_ceiling():
    assert output_ceiling(BATCHED, 8000, 24000) == 8000


@pytest.mark.parametrize("strategy", sorted(SINGLE_CALL_SHAPES))
def test_single_call_shapes_get_the_raised_ceiling(strategy):
    assert output_ceiling(strategy, 8000, 24000) == 24000


def test_the_two_ceilings_actually_differ():
    """Vacuity guard: if the caller ever passed the same value for both, every ceiling
    assertion above would pass while the shape truncated in production."""
    assert output_ceiling(SINGLE_CALL, 8000, 24000) != output_ceiling(BATCHED, 8000, 24000)


# ── the delta instruction ────────────────────────────────────────────────────

def test_delta_instruction_asks_for_omission_and_for_new_entities_in_full():
    """It must do BOTH. An instruction that only says "omit known entities" suppresses
    corrections as well as repeats, which is the way this arm could look brilliant and be
    wrong (BOOK_TO_GAME/14 §5 A4)."""
    assert "OMIT" in DELTA_INSTRUCTION
    assert "adds or corrects" in DELTA_INSTRUCTION
    assert "does NOT appear above, in full" in DELTA_INSTRUCTION


def test_only_the_delta_shape_is_named_delta():
    """Guards against a future shape being added to SINGLE_CALL_SHAPES and silently
    inheriting the delta instruction — they are separate decisions."""
    assert SINGLE_CALL_DELTA in SINGLE_CALL_SHAPES
    assert SINGLE_CALL in SINGLE_CALL_SHAPES
    assert SINGLE_CALL != SINGLE_CALL_DELTA


def test_edc_is_declared_but_not_a_single_call_shape():
    """`edc_cited` is two calls by construction, so when it IS wired it must not pick up
    the single-call batching or ceiling by accident."""
    assert EDC_CITED in PLANNED
    assert EDC_CITED not in SINGLE_CALL_SHAPES


# ── the cache key must separate the shapes ───────────────────────────────────

def _profile_hash(profile: dict, strategy: str) -> str:
    """The REAL computation the worker calls — not a copy.

    The first version of these tests mirrored the hash locally, and a bite-test showed the
    hole immediately: deleting the strategy from the worker left every assertion green,
    because they were testing the mirror. NV-1 — the subject has to be able to vary.
    """
    return shape_hash(profile, strategy)


def test_two_strategies_on_one_profile_get_DIFFERENT_cache_keys():
    """The bug this guards is silent and expensive.

    The raw-output cache is keyed on (chapter, content, batch_idx, profile_hash, effort).
    `batched` batch 0 is [character, location, item]; `single_call` batch 0 is ALL EIGHT
    kinds. With the strategy absent from the key those two collide, so running one shape
    over a chapter the other had already done returns a CACHE HIT — the three-kind parse
    served as the eight-kind one, five kinds silently gone, zero tokens reported. It also
    makes an A/B between two shapes on one chapter impossible, which is the whole point of
    the parameter.
    """
    assert _profile_hash(PROFILE, BATCHED) != _profile_hash(PROFILE, SINGLE_CALL)


def test_delta_is_a_different_cache_key_from_plain_single_call():
    """`single_call` and `single_call_delta` produce the SAME batches, so batch_idx alone
    cannot tell them apart — but they send different prompts and get different answers."""
    assert _profile_hash(PROFILE, SINGLE_CALL) != _profile_hash(PROFILE, SINGLE_CALL_DELTA)


def test_the_same_strategy_and_profile_still_hit_the_cache():
    """Vacuity guard: if every call produced a fresh key the cache would never hit and the
    two assertions above would pass for the wrong reason."""
    assert _profile_hash(PROFILE, BATCHED) == _profile_hash(PROFILE, BATCHED)


def test_a_changed_profile_still_changes_the_key():
    """The property the field originally existed for must survive the addition."""
    other = {**PROFILE, "character": {"name": "default"}}
    assert _profile_hash(other, BATCHED) != _profile_hash(PROFILE, BATCHED)
