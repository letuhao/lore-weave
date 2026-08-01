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
    CACHE_ALWAYS_REFRESH,
    CACHE_POLICIES,
    CACHE_PREFER_CACHE,
    CACHE_REFRESH_IF_STALE,
    ONE_RESPONSE_SHAPES,
    PLANNED,
    SINGLE_CALL_SHAPES,
    TWO_STAGE_SHAPES,
    STRATEGIES,
    normalize,
    normalize_cache_policy,
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
    assert STRATEGIES == {BATCHED, SINGLE_CALL, SINGLE_CALL_DELTA, EDC_CITED}


def test_the_PLANNED_mechanism_still_refuses_even_though_the_set_is_empty():
    """PLANNED is empty now that edc_cited is wired, but the GATE must survive — it is what
    stops the next declared-but-unwired name from silently running as the default. Proven
    by feeding the check a name that is in neither set."""
    with pytest.raises(ValueError) as exc:
        normalize("some_future_shape")
    assert "unknown extraction_strategy" in str(exc.value)


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
    assert len(SINGLE_CALL_SHAPES) == 3  # single_call, single_call_delta, edc_cited


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


def test_edc_is_wired_and_gets_the_one_response_treatment():
    """`edc_cited` is TWO calls, but its second one carries every kind — so it needs the
    same one-batch plan and raised ceiling as the single-call shapes, and additionally the
    sweep pre-pass."""
    assert EDC_CITED in STRATEGIES and EDC_CITED not in PLANNED
    assert EDC_CITED in ONE_RESPONSE_SHAPES
    assert EDC_CITED in TWO_STAGE_SHAPES
    assert len(plan_batches(EDC_CITED, PROFILE, KINDS)) == 1
    assert output_ceiling(EDC_CITED, 8000, 24000) == 24000


def test_only_edc_is_two_stage():
    """The sweep costs an extra call per window; no other shape may pick it up silently."""
    assert TWO_STAGE_SHAPES == {EDC_CITED}
    for s in (BATCHED, SINGLE_CALL, SINGLE_CALL_DELTA):
        assert s not in TWO_STAGE_SHAPES


def test_nothing_is_advertised_that_the_engine_does_not_implement():
    """The no-silent-no-op rule, now that PLANNED is empty: every advertised strategy must
    be one the worker actually branches on. This is the assertion that reds if someone adds
    a name to STRATEGIES before wiring it."""
    assert not (PLANNED & STRATEGIES)
    for s in STRATEGIES:
        assert s in ONE_RESPONSE_SHAPES or s == BATCHED, (
            f"{s} is advertised but matches no implemented shape")


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


def test_changing_a_kind_DESCRIPTION_changes_the_cache_key():
    """Descriptions are rendered into the prompt, so editing one changes the answer.

    Keyed only on the profile, the cache served the pre-edit parse — and worse, made the
    edit unmeasurable: you cannot re-run a chapter to see whether a better definition
    helped if the answer comes from before you wrote it. Found while trying to test exactly
    that, on the same day the identical gap was fixed for `strategy`.
    """
    bare = [{"code": "power_system", "description": None, "attributes": []}]
    defined = [{"code": "power_system",
                "description": "A named TECHNIQUE... NOT the object used to perform it.",
                "attributes": []}]
    assert shape_hash(PROFILE, BATCHED, bare) != shape_hash(PROFILE, BATCHED, defined)


def test_changing_an_ATTRIBUTE_description_changes_the_cache_key():
    a = [{"code": "item", "description": "d", "attributes": [{"code": "type", "description": None}]}]
    b = [{"code": "item", "description": "d",
          "attributes": [{"code": "type", "description": "weapon, treasure, talisman"}]}]
    assert shape_hash(PROFILE, BATCHED, a) != shape_hash(PROFILE, BATCHED, b)


def test_identical_definitions_still_hit_the_cache():
    """Vacuity guard — otherwise every run would miss and the two tests above would pass
    for the wrong reason."""
    m = [{"code": "item", "description": "d", "attributes": [{"code": "type", "description": "x"}]}]
    assert shape_hash(PROFILE, BATCHED, m) == shape_hash(PROFILE, BATCHED, list(m))


# ── cache policy ─────────────────────────────────────────────────────────────

def test_the_default_policy_is_the_CORRECT_one_not_the_cheap_one():
    """This is the whole design decision.

    The cache could serve an entire job at zero tokens and nothing said so. Two dimensions
    of its key were found missing in one day — the strategy, then the kind/attribute
    descriptions — and each made a re-extraction after an edit silently return the parse
    from before that edit. The answer cannot be "remember every dimension", so the DEFAULT
    refreshes when anything looks stale and reuse is an explicit choice.
    """
    assert normalize_cache_policy(None) == CACHE_REFRESH_IF_STALE
    assert normalize_cache_policy("") == CACHE_REFRESH_IF_STALE


def test_all_three_policies_exist_and_are_distinct():
    assert CACHE_POLICIES == {CACHE_REFRESH_IF_STALE, CACHE_PREFER_CACHE, CACHE_ALWAYS_REFRESH}
    assert len(CACHE_POLICIES) == 3


def test_an_unknown_policy_RAISES_rather_than_defaulting():
    """A typo must not quietly become a policy the caller did not choose — in either
    direction. Falling back to `prefer_cache` would serve stale silently; falling back to
    `always_refresh` would burn tokens the caller did not agree to spend."""
    with pytest.raises(ValueError) as exc:
        normalize_cache_policy("use_cache_pls")
    assert "use_cache_pls" in str(exc.value)
    for p in CACHE_POLICIES:
        assert p in str(exc.value)


def test_policy_names_are_not_interchangeable_with_strategy_names():
    """They travel together on one request; a value valid for one must not pass for the
    other, or a caller could set a cache policy and get a prompt shape."""
    for p in CACHE_POLICIES:
        with pytest.raises(ValueError):
            normalize(p)
    for s in STRATEGIES:
        with pytest.raises(ValueError):
            normalize_cache_policy(s)
