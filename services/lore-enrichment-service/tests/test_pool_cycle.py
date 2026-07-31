"""The contract-generator cycle, tested with no network and no model.

Eight probe rounds measured what a MODEL does. These test what the LOOP does, and
the split matters: the loop's job is to own the edges — which slot is next, when to
heal, when to refuse to freeze — and none of that needs a model to exercise.

Every test here corresponds to something that broke during the first live run of
the cycle, or to a claim the design makes that ought to be falsifiable.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.pool import criteria
from app.pool.loop import EDGES, PoolRun, SlotState, State, run_cycle
from app.pool.registry import Operation, Visibility, load_registry

REGISTRY = pathlib.Path(__file__).resolve().parents[3] / "contracts" / "pool" / "registry.json"


@pytest.fixture(scope="module")
def reg():
    return load_registry(REGISTRY)


# ── the registry ────────────────────────────────────────────────────────────

def test_the_registry_is_the_one_the_engine_would_read(reg):
    assert REGISTRY.exists(), "the Python loop and the Rust engine read the same file"
    assert reg.slots, "no slots registered"
    assert reg.generated is False, (
        "registry.json is still hand-authored; when the Rust export lands this flips "
        "to true and a drift test replaces this assertion"
    )


def test_axis_is_computed_from_consumers_not_authored(reg):
    """`BLD-A2` — the abstraction axis comes from who consumes the members."""
    tag = reg["instrument_tag"]
    assert tag.consumed_by, "a slot with no consumer has no computable axis"
    assert "progression" in tag.axis and "df07" in tag.axis


def test_a_slot_with_no_consumer_admits_it_rather_than_inventing_an_axis(reg):
    from dataclasses import replace
    orphan = replace(reg["instrument_tag"], consumed_by=())
    assert orphan.axis == "", "an unconsumed slot must NOT synthesise an axis"


def test_unregistered_reference_targets_are_visible_before_any_model_runs(reg):
    """`EPL-A8` — cross-module demand is a property of the registry, not of a run."""
    dangling = reg.dangling_targets()
    assert "progression_kind" in dangling, "PROG_001 has not registered its slot"
    assert dangling["progression_kind"] == ["item_archetype.gates_on"]


# ── the state machine (ASK-A6: the planner owns the edges) ──────────────────

def test_an_illegal_transition_raises_rather_than_warns():
    st = SlotState("item_archetype")
    st.move(State.PROBED)
    st.move(State.PROPOSED)
    st.move(State.SETTLED)
    with pytest.raises(ValueError, match="illegal transition"):
        st.move(State.PROBED)          # the edge the model invented in round 2


def test_starved_cannot_go_back_to_probed():
    """The exact edge the model invented when it would not terminate (`ASK-A6`)."""
    assert State.PROBED not in EDGES[State.STARVED]
    assert EDGES[State.STARVED] == frozenset({State.PROPOSED, State.DECLINED})


def test_declined_is_terminal():
    assert EDGES[State.DECLINED] == frozenset()


# ── the criteria (BLD-A1: the operation yields the check) ───────────────────

def test_a_one_to_one_map_is_not_an_abstraction(reg):
    """P17 passed a fidelity gate at 1.0 doing exactly this."""
    members = [{"code": f"tag_{i}", "name": {"en": f"t{i}"}, "covers": [f"obj{i}"],
                "provenance": "PROPOSED"} for i in range(11)]
    v = criteria.evaluate(reg["instrument_tag"], members, [], evidence_n=11)
    assert not v.passed and v.hard_broken
    assert any(f.criterion == "is_an_abstraction" for f in v.findings)


def test_an_abstraction_that_generalises_passes(reg):
    members = [
        {"code": "blade", "name": {"en": "blade"}, "covers": ["sword", "dagger"],
         "provenance": "PROPOSED"},
        {"code": "haft", "name": {"en": "haft"}, "covers": ["spear"], "provenance": "PROPOSED"},
    ]
    v = criteria.evaluate(reg["instrument_tag"], members, [], evidence_n=11)
    assert v.passed, v


def test_covers_is_accepted_in_either_position(reg):
    """The first live run put `covers` in `body`, because the slot declares no body
    fields and the envelope left it nowhere legal. A correct answer must not fail
    on placement."""
    in_body = [{"code": "blade", "name": {"en": "b"}, "provenance": "PROPOSED",
                "body": {"covers": ["sword", "dagger"]}}]
    v = criteria.evaluate(reg["instrument_tag"], in_body, [], evidence_n=11)
    assert v.passed, v


def test_a_banned_word_inside_evidence_does_not_fail_the_member(reg):
    """Round 8's checker matched "long" inside an evidence quote and reported a
    false failure. The scan looks at the code and display names, never the blob."""
    members = [
        {"code": "blade", "name": {"en": "blade"},
         "covers": ["a red silk sash, seven chi long", "an iron whip"],
         "provenance": "PROPOSED"},
        {"code": "haft", "name": {"en": "haft"}, "covers": ["a spear"],
         "provenance": "PROPOSED"},
    ]
    v = criteria.evaluate(reg["instrument_tag"], members, [], evidence_n=11)
    assert v.passed, v


def test_a_value_outside_an_engine_fixed_enum_is_a_hard_failure(reg):
    members = [{"code": "sword", "name": {"en": "sword"}, "provenance": "CITED",
                "evidence": {"kind": "span"},
                "body": {"class": "Superweapon", "instrument_tags": ["blade"]}}]
    v = criteria.evaluate(reg["item_archetype"], members, [], evidence_n=11,
                          registry_enums=reg.engine_enums)
    assert v.hard_broken
    assert any(f.criterion == "engine_enum_legal" for f in v.findings)


def test_provenance_without_resolvable_evidence_is_a_hard_failure(reg):
    """`MEM-A5` — the model invented genre-pack ids for the labels nothing verified."""
    members = [{"code": "blade", "name": {"en": "b"}, "covers": ["a", "b"],
                "provenance": "CANON"}]          # CANON with no evidence at all
    v = criteria.evaluate(reg["instrument_tag"], members, [], evidence_n=11)
    assert v.hard_broken
    assert any(f.criterion == "evidence_resolves" for f in v.findings)


def test_a_refusal_disguised_as_a_member_is_a_hard_failure(reg):
    """`BLD-A3` — P20 emitted a category literally named "non-implement"."""
    members = [
        {"code": "blade", "name": {"en": "b"}, "covers": ["x", "y"], "provenance": "PROPOSED"},
        {"code": "not_an_implement", "name": {"en": "n"}, "covers": ["mount"],
         "provenance": "PROPOSED"},
    ]
    v = criteria.evaluate(reg["instrument_tag"], members, [], evidence_n=11)
    assert v.hard_broken
    assert any(f.criterion == "no_refusal_as_member" for f in v.findings)


# ── the loop ────────────────────────────────────────────────────────────────

def _fake_model(scripts: dict[str, list[str]]):
    """A scripted completer. Keyed by the slot id that appears in the prompt."""
    calls: dict[str, int] = {}

    def complete(prompt: str) -> str:
        slot = next(s for s in ("instrument_tag", "item_archetype") if f"SLOT: {s}" in prompt)
        i = calls.get(slot, 0)
        calls[slot] = i + 1
        seq = scripts[slot]
        return seq[min(i, len(seq) - 1)]

    return complete


_GOOD_TAGS = json.dumps({"members": [
    {"code": "blade", "name": {"en": "blade"}, "covers": ["swords", "shears"],
     "provenance": "PROPOSED", "evidence": None},
    {"code": "haft", "name": {"en": "haft"}, "covers": ["spear"],
     "provenance": "PROPOSED", "evidence": None},
], "refused": [{"what": "a mount", "why": "a beast", "owner": "bestiary"}]})

_GOOD_ARCH = json.dumps({"members": [
    {"code": "sword", "name": {"en": "sword"}, "provenance": "CITED",
     "evidence": {"kind": "span", "chunk": "ch65"},
     "body": {"class": "Weapon", "instrument_tags": ["blade"]}},
    {"code": "banner", "name": {"en": "banner"}, "provenance": "CITED",
     "evidence": {"kind": "span", "chunk": "ch65"},
     "body": {"class": "Tool", "instrument_tags": ["haft"]}},
], "refused": []})

_BAD_TAGS = json.dumps({"members": [
    {"code": "t1", "name": {"en": "t1"}, "covers": [], "provenance": "PROPOSED"},
], "refused": []})


def test_the_cycle_fills_two_slots_with_two_kinds_and_no_per_slot_code(reg):
    """The reuse claim (`BLD-A5`), stated so it can fail: two slots, two kinds,
    zero code that names a slot."""
    run = run_cycle(reg, "EVIDENCE", _fake_model({
        "instrument_tag": [_GOOD_TAGS], "item_archetype": [_GOOD_ARCH]}), evidence_n=11)
    assert run.slots["instrument_tag"].state is State.SETTLED
    assert run.slots["item_archetype"].state is State.SETTLED
    assert run.frozen and len(run.digest) == 64


def test_a_hard_failed_slot_does_NOT_settle(reg):
    """The bug the first live run exposed: the gate fired and `approve()` was called
    anyway, so a slot whose criteria had broken settled regardless. A check nothing
    consumes is decoration (`ASK-A5`), and it happened inside the loop that
    documents it."""
    run = run_cycle(reg, "EVIDENCE", _fake_model({
        "instrument_tag": [_BAD_TAGS], "item_archetype": [_GOOD_ARCH]}),
        evidence_n=11, heal_rounds=0)
    st = run.slots["instrument_tag"]
    assert st.state is State.PROPOSED, "a hard-failed slot must not reach SETTLED"
    assert not run.frozen, "an unsettled slot must block the freeze"


def test_the_heal_round_is_used_and_then_stops(reg):
    run = run_cycle(reg, "EVIDENCE", _fake_model({
        "instrument_tag": [_BAD_TAGS, _GOOD_TAGS], "item_archetype": [_GOOD_ARCH]}),
        evidence_n=11, heal_rounds=1)
    assert run.slots["instrument_tag"].attempts == 2
    assert run.slots["instrument_tag"].state is State.SETTLED


def test_the_human_gate_can_decline_and_that_blocks_the_freeze(reg):
    run = run_cycle(reg, "EVIDENCE", _fake_model({
        "instrument_tag": [_GOOD_TAGS], "item_archetype": [_GOOD_ARCH]}),
        evidence_n=11, approve=lambda slot, members: slot.id != "item_archetype")
    assert run.slots["item_archetype"].state is State.PROPOSED
    assert not run.frozen


def test_cross_module_demands_survive_the_freeze_and_are_reported(reg):
    """`PPB-A5` — the planner finishes before the world does. Item's own slots close;
    the demands on unregistered modules stay visible and are NOT silently dropped."""
    run = run_cycle(reg, "EVIDENCE", _fake_model({
        "instrument_tag": [_GOOD_TAGS], "item_archetype": [_GOOD_ARCH]}), evidence_n=11)
    targets = {r.target for r in run.cross_module_demands()}
    assert {"progression_kind", "equip_slot"} <= targets
    assert run.frozen, (
        "an unregistered TARGET is another module's obligation, not this module's — "
        "PPB-A5 says the planner is done when internally closed. A pool-wide freeze "
        "across many modules is a different gate and is not built."
    )


def test_the_freeze_digest_is_of_content_not_of_order(reg):
    a = run_cycle(reg, "E", _fake_model({"instrument_tag": [_GOOD_TAGS],
                                         "item_archetype": [_GOOD_ARCH]}), evidence_n=11)
    b = run_cycle(reg, "E", _fake_model({"instrument_tag": [_GOOD_TAGS],
                                         "item_archetype": [_GOOD_ARCH]}), evidence_n=11)
    assert a.digest == b.digest


def test_an_unbuilt_planner_kind_refuses_by_name(reg):
    """`MOD-A1` — adding a KIND is an architecture decision, not a per-slot fix."""
    from dataclasses import replace

    from app.pool.kinds import planner_for
    ladder = replace(reg["instrument_tag"], operation=Operation.PARTITION)
    with pytest.raises(NotImplementedError, match="architecture decision"):
        planner_for(ladder)
