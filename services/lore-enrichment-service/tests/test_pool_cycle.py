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
from app.pool import loop as loop_module
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
        "D-POOL-REGISTRY-NOT-GENERATED: registry.json is still hand-authored; when "
        "the Rust `declare_pool_slot!` export lands this flips to true and a DRIFT "
        "test — Rust declaration vs this file — replaces this assertion"
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
    assert dangling["equip_slot"] == ["item_archetype.equip_slot"]
    assert "progression_kind" not in dangling, (
        "PROG_001 has registered progression_kind, so its demand row is GONE. This is "
        "the half of EPL-A8 that is easy to leave untested: a demand channel that only "
        "ever accumulates is a list, not a register."
    )


def test_a_confirm_slot_must_declare_the_default_it_confirms(tmp_path):
    """A CONFIRM planner starts from an answer; with none it silently degrades into a
    free-form enumeration while still being called CONFIRM."""
    raw = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for s in raw["slots"]:
        s.pop("default", None)
    bad = tmp_path / "registry.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="no `default`"):
        load_registry(bad)


def test_registry_identifiers_are_refused_if_they_would_become_asp_variables(tmp_path):
    raw = json.loads(REGISTRY.read_text(encoding="utf-8"))
    raw["slots"][0]["id"] = "InstrumentTag"
    bad = tmp_path / "registry.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="not a registry identifier"):
        load_registry(bad)


# ── model text must never become solver source ──────────────────────────────

def test_a_model_code_can_never_become_asp_program_text(reg):
    """A live run crashed the solver on a code the model chose. `24_pearls` is a
    syntax error; `Blade` is the dangerous one — it PARSES, as a variable, so the
    register would answer a different question with nothing to show for it."""
    from app.pool.register import abduce
    hostile = {"instrument_tag": [
        {"code": "24_pearls"}, {"code": "Blade"}, {"code": "has space"},
        {"code": 'quote"inside'}, {"code": "back\\slash"}, {"code": "靈寶"},
        {"code": "ok_one", "body": {}},
    ]}
    rows = abduce(reg, hostile)                       # must not raise
    targets = {r.target for r in rows}
    assert "instrument_tag" not in targets, "a slot with members is not 'needs_members'"
    assert "progression_kind" in targets


def test_a_code_that_is_not_a_contract_identifier_is_a_hard_failure(reg):
    """The second, independent layer: the register cannot crash on these any more,
    and they still must never SETTLE."""
    for bad in ("24_pearls", "Blade", "_leading", "has space"):
        members = [{"code": bad, "name": {"en": "x"}, "covers": ["a", "b"],
                    "provenance": "PROPOSED"},
                   {"code": "fine", "name": {"en": "y"}, "covers": ["c"],
                    "provenance": "PROPOSED"}]
        v = criteria.evaluate(reg["instrument_tag"], members, [], evidence_n=11)
        assert v.hard_broken, bad
        assert any(f.criterion == "codes_ascii" for f in v.findings), bad


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


def test_reopened_is_declared_and_currently_unreachable_and_says_so():
    """A state nothing can enter is a claim, not a state — and `SETTLED -> REOPENED`
    is the only outgoing edge SETTLED has, so a test that merely asserts the edge
    exists proves nothing about the machine.

    The trigger it is FOR is real and was measured: `item_archetype` requires a list
    of `instrument_tag` codes, the model omitted the field on every archetype no
    settled tag covered, and healing cannot fix that — the fix is upstream, in a slot
    that has already settled. Reopening on downstream under-coverage is a feature
    with its own termination question, and it is not built.

    This test RE-REDS the day it is built, which is the point: whoever wires the
    edge has to come here and state the bound they chose."""
    import re
    src = pathlib.Path(loop_module.__file__).read_text(encoding="utf-8")
    entries = re.findall(r"move\(State\.REOPENED\)", src)
    assert not entries, (
        "D-POOL-REOPEN-UNREACHABLE: something now moves a slot into REOPENED. Delete "
        "this test and replace it with one that asserts the reopen BOUND — an "
        "unbounded reopen turns the cycle into a loop a model can keep alive forever."
    )
    assert EDGES[State.SETTLED] == frozenset({State.REOPENED})
    assert State.REOPENED in EDGES[State.SETTLED]


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


def test_covers_has_exactly_one_legal_position(reg):
    """This test asserted the OPPOSITE for one cycle, and the reversal is the point.

    The tolerance was written when the envelope named `covers` nowhere, so a model
    that put it in `body` had produced a correct answer in an invented place — and
    failing that would have been failing placement, not content. Fixing the envelope
    removed the ambiguity; keeping the tolerance afterwards would have left two rules
    disagreeing about one field, with `no_undeclared_body_fields` rejecting exactly
    what this branch accepted."""
    in_body = [{"code": "blade", "name": {"en": "b"}, "provenance": "PROPOSED",
                "body": {"covers": ["sword", "dagger"]}}]
    v = criteria.evaluate(reg["instrument_tag"], in_body, [], evidence_n=11)
    assert v.hard_broken
    assert {f.criterion for f in v.findings} >= {"no_undeclared_body_fields",
                                                 "every_category_covers"}

    top_level = [{"code": "blade", "name": {"en": "b"}, "provenance": "PROPOSED",
                  "covers": ["sword", "dagger"]},
                 {"code": "haft", "name": {"en": "h"}, "provenance": "PROPOSED",
                  "covers": ["spear"]}]
    assert criteria.evaluate(reg["instrument_tag"], top_level, [], evidence_n=11).passed


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


def test_a_body_field_the_slot_does_not_declare_is_a_hard_failure(reg):
    """A live run put `aspect` on a slot whose `member` is empty. Nothing reads it,
    and it still changes the frozen digest."""
    members = [{"code": "blade", "name": {"en": "b"}, "covers": ["x", "y"],
                "provenance": "PROPOSED", "body": {"aspect": "form"}}]
    v = criteria.evaluate(reg["instrument_tag"], members, [], evidence_n=11)
    assert v.hard_broken
    assert any(f.criterion == "no_undeclared_body_fields" for f in v.findings)


def test_an_owner_that_names_nothing_is_not_an_owner(reg):
    """`BLD-A3` — the check was a truthiness test, and the model produced the STRING
    "null", which is truthy. A refusal routed to "null" was dropped, not routed."""
    members = [{"code": "blade", "name": {"en": "b"}, "covers": ["x", "y"],
                "provenance": "PROPOSED"}]
    for owner in ("null", "none", "N/A", " Unknown ", ""):
        v = criteria.evaluate(reg["instrument_tag"], members,
                              [{"what": "a mount", "why": "a beast", "owner": owner}],
                              evidence_n=11)
        assert v.hard_broken, owner
        assert any(f.criterion == "refusals_name_an_owner" for f in v.findings), owner
    ok = criteria.evaluate(reg["instrument_tag"], members,
                           [{"what": "a mount", "why": "a beast", "owner": "bestiary"}],
                           evidence_n=11)
    assert ok.passed, ok


# ── the loop ────────────────────────────────────────────────────────────────

def _fake_model(scripts: dict[str, list[str]], reg=None):
    """A scripted completer, keyed by the slot id the prompt names.

    It reads the slot id out of the prompt rather than being told which slot is
    next, because WHICH SLOT COMES NEXT is the loop's decision and the thing under
    test. A script missing an entry raises, so adding a slot to the registry and
    forgetting it here is loud.
    """
    calls: dict[str, int] = {}

    def complete(prompt: str) -> str:
        line = next(ln for ln in prompt.splitlines() if ln.startswith("SLOT: "))
        slot = line.split()[1]
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
     "body": {"class": "Weapon", "instrument_tags": ["blade"],
              "gates_on": ["cultivation_realm"]}},
    {"code": "banner", "name": {"en": "banner"}, "provenance": "CITED",
     "evidence": {"kind": "span", "chunk": "ch65"},
     "body": {"class": "Tool", "instrument_tags": ["haft"]}},
], "refused": []})

_BAD_TAGS = json.dumps({"members": [
    {"code": "t1", "name": {"en": "t1"}, "covers": [], "provenance": "PROPOSED"},
], "refused": []})

#: CONFIRM — two of the three declared defaults kept, the third dropped with a reason.
_GOOD_KINDS = json.dumps({"members": [
    {"code": "cultivation_realm", "name": {"en": "cultivation realm"},
     "provenance": "DECLARED", "evidence": None},
    {"code": "skill_mastery", "name": {"en": "skill mastery"},
     "provenance": "DECLARED", "evidence": None},
], "refused": [{"what": "standing", "why": "this reality has no social ladder",
                "owner": "progression"}]})

#: PARTITION — two groups, each with two or more bands, none of them numbered.
_GOOD_STAGES = json.dumps({"members": [
    {"code": "qi_gathering", "name": {"en": "qi gathering"}, "provenance": "CITED",
     "evidence": {"kind": "span", "chunk": "ch12"}, "body": {"kind": "cultivation_realm"}},
    {"code": "foundation", "name": {"en": "foundation building"}, "provenance": "CITED",
     "evidence": {"kind": "span", "chunk": "ch12"}, "body": {"kind": "cultivation_realm"}},
    {"code": "golden_core", "name": {"en": "golden core"}, "provenance": "CITED",
     "evidence": {"kind": "span", "chunk": "ch47"}, "body": {"kind": "cultivation_realm"}},
    {"code": "immortal", "name": {"en": "immortal"}, "provenance": "CITED",
     "evidence": {"kind": "span", "chunk": "ch65"}, "body": {"kind": "cultivation_realm"}},
    {"code": "apprentice", "name": {"en": "apprentice"}, "provenance": "PROPOSED",
     "evidence": None, "body": {"kind": "skill_mastery"}},
    {"code": "adept", "name": {"en": "adept"}, "provenance": "PROPOSED",
     "evidence": None, "body": {"kind": "skill_mastery"}},
], "refused": []})

_ALL_GOOD = {"progression_kind": [_GOOD_KINDS], "instrument_tag": [_GOOD_TAGS],
             "item_archetype": [_GOOD_ARCH], "progression_stage": [_GOOD_STAGES]}


def test_the_cycle_fills_four_slots_with_four_kinds_and_no_per_slot_code(reg):
    """The reuse claim (`BLD-A5`), stated so it can fail: every registered slot, every
    operation, two owning modules, and zero code anywhere that names a slot."""
    run = run_cycle(reg, "EVIDENCE", _fake_model(_ALL_GOOD), evidence_n=11)
    assert {s.state for s in run.slots.values()} == {State.SETTLED}
    assert {reg[sid].operation for sid in run.slots} == set(Operation), (
        "this test is only a four-kind test while the registry exercises all four "
        "operations; if a future registry drops one, say so here rather than let the "
        "name of the test carry a claim the fixture no longer supports"
    )
    assert {reg[sid].owner for sid in run.slots} == {"item", "progression"}
    assert run.frozen and len(run.digest) == 64


def test_every_operation_has_a_planner_kind(reg):
    """`MOD-A1` — the table is keyed by operation, so this is total or it is not."""
    from app.pool.kinds import PLANNERS
    assert set(PLANNERS) == set(Operation)


def test_an_unbuilt_planner_kind_still_refuses_by_name(reg, monkeypatch):
    """All four kinds are built now, so the refusal path has no natural subject left.
    It is still the mechanism that makes a FIFTH operation an architecture decision
    rather than a crash, so it keeps a test — with the subject constructed."""
    from app.pool import kinds
    monkeypatch.setitem(kinds.PLANNERS, Operation.PARTITION, None)
    monkeypatch.delitem(kinds.PLANNERS, Operation.PARTITION)
    with pytest.raises(NotImplementedError, match="architecture decision"):
        kinds.planner_for(reg["progression_stage"])


def test_the_register_ranks_by_blocking_power_not_by_registry_order(reg):
    """`PPL-A6.1`. progression_kind is referenced by two different slots, so it opens
    first — and that happens to be dependency-correct here. The ranking is by blocking
    power, NOT a topological sort; this asserts the property that exists."""
    from app.pool.register import abduce
    rows = [r for r in abduce(reg, {}) if r.target in reg.slots]
    assert rows[0].target == "progression_kind"
    assert rows[0].blocks == 2


def test_a_hard_failed_slot_does_NOT_settle(reg):
    """The bug the first live run exposed: the gate fired and `approve()` was called
    anyway, so a slot whose criteria had broken settled regardless. A check nothing
    consumes is decoration (`ASK-A5`), and it happened inside the loop that
    documents it."""
    run = run_cycle(reg, "EVIDENCE", _fake_model({**_ALL_GOOD,
                                                  "instrument_tag": [_BAD_TAGS]}),
                    evidence_n=11, heal_rounds=0)
    st = run.slots["instrument_tag"]
    assert st.state is State.PROPOSED, "a hard-failed slot must not reach SETTLED"
    assert not run.frozen, "an unsettled slot must block the freeze"


def test_rejected_members_are_not_readable_as_if_they_were_approved(reg):
    """The second live run's find: a hard-failed slot still had `members`, and the
    pool exposed them. The register then stopped calling the slot open, the next
    planner was offered its codes, and the reference check accepted a pointer into
    it — all while the slot's own verdict said FAIL."""
    run = run_cycle(reg, "EVIDENCE", _fake_model({**_ALL_GOOD,
                                                  "instrument_tag": [_BAD_TAGS]}),
                    evidence_n=11, heal_rounds=0)
    assert run.slots["instrument_tag"].members, "the rejected material is still kept"
    assert "instrument_tag" not in run.pool, "…and is not readable as approved"
    assert any(r.target == "instrument_tag" and r.reason == "needs_members"
               for r in run.register), "the register must still call the slot open"


def test_the_not_frozen_message_names_what_is_unsettled(reg):
    """A refusal that reports `0 open rows` is a refusal whose reason cannot be
    read. That message is what hid the bug above for a whole run."""
    run = run_cycle(reg, "EVIDENCE", _fake_model(_ALL_GOOD), evidence_n=11,
                    approve=lambda slot, members: slot.id != "item_archetype")
    line = next(x for x in run.log if x.startswith("NOT FROZEN"))
    assert "item_archetype" in line


def test_the_heal_round_is_used_and_then_stops(reg):
    run = run_cycle(reg, "EVIDENCE", _fake_model({**_ALL_GOOD,
                                                  "instrument_tag": [_BAD_TAGS, _GOOD_TAGS]}),
                    evidence_n=11, heal_rounds=1)
    assert run.slots["instrument_tag"].attempts == 2
    assert run.slots["instrument_tag"].state is State.SETTLED


def test_the_heal_prompt_carries_the_answer_it_is_asking_to_repair(reg):
    """A live run watched a slot fail the same two criteria three times, each time
    with a different wrong answer, because the heal prompt said "keep the rest"
    without showing what the rest was."""
    seen: list[str] = []
    inner = _fake_model({**_ALL_GOOD, "instrument_tag": [_BAD_TAGS, _GOOD_TAGS]})

    def spy(prompt: str) -> str:
        seen.append(prompt)
        return inner(prompt)

    run_cycle(reg, "EVIDENCE", spy, evidence_n=11, heal_rounds=1)
    heal = next(p for p in seen if "PREVIOUS ANSWER" in p)
    assert '"code": "t1"' in heal or '"code":"t1"' in heal, (
        "the heal prompt must contain the rejected answer verbatim"
    )
    assert "every_category_covers" in heal, "…and the findings that rejected it"


def test_the_abstract_envelope_names_where_covers_goes(reg):
    """Two live runs failed on PLACEMENT with a sound answer underneath, because
    `covers` is required by the operation and declared by no slot body."""
    from app.pool.kinds import planner_for
    p = planner_for(reg["instrument_tag"]).ask(reg["instrument_tag"], reg, "E", {})
    assert '"covers"' in p.split("Emit ONE JSON object")[1], (
        "covers must appear in the OUTPUT SHAPE, not only in the prose above it"
    )
    q = planner_for(reg["item_archetype"]).ask(reg["item_archetype"], reg, "E", {})
    assert '"covers"' not in q, "…and only for the operation that requires it"


def test_the_human_gate_can_decline_and_that_blocks_the_freeze(reg):
    run = run_cycle(reg, "EVIDENCE", _fake_model(_ALL_GOOD), evidence_n=11,
                    approve=lambda slot, members: slot.id != "item_archetype")
    assert run.slots["item_archetype"].state is State.PROPOSED
    assert not run.frozen


def test_cross_module_demands_survive_the_freeze_and_are_reported(reg):
    """`PPB-A5` — the planner finishes before the world does. The registered slots
    close; the demand on a module that has not registered stays visible and is NOT
    silently dropped."""
    run = run_cycle(reg, "EVIDENCE", _fake_model(_ALL_GOOD), evidence_n=11)
    targets = {r.target for r in run.cross_module_demands()}
    assert targets == {"equip_slot"}, (
        "progression_kind used to be here and is now a registered slot, so its row is "
        "gone; equip_slot is deliberately left unregistered so this channel still has "
        "a subject. If it ever empties, this test stops proving anything."
    )
    assert run.frozen, (
        "an unregistered TARGET is another module's obligation, not this module's — "
        "PPB-A5 says the planner is done when internally closed. A pool-wide freeze "
        "across many modules is a different gate and is not built."
    )


def test_a_module_freezes_when_ITS_closure_settles_not_when_the_pool_does(reg):
    """The exact live scenario, and the reason `closure_for` exists.

    Three consecutive runs against a real model produced no artifact at all, and in
    two of them the reason was `progression_stage` — a slot `item` does not
    reference and cannot be blocked by. Item's contract was complete and unusable.
    That is `PPB-A5` inverted by a pool-wide gate."""
    run = run_cycle(reg, "E", _fake_model({**_ALL_GOOD,
                                           "progression_stage": [_BAD_TAGS]}),
                    evidence_n=11, heal_rounds=0)
    assert run.slots["progression_stage"].state is State.PROPOSED
    assert not run.frozen, "the pool as a whole is NOT closed"
    assert "item" in run.artifacts, (
        "item references instrument_tag, item_archetype and progression_kind — all "
        "settled — so its contract is complete and must be consumable"
    )
    assert "progression" not in run.artifacts
    assert sorted(run.artifacts["item"].slots) == [
        "instrument_tag", "item_archetype", "progression_kind"], (
        "an item artifact must carry progression_kind: gates_on points at it, and a "
        "consumer handed a code it cannot resolve has an artifact with a hole in it"
    )
    assert "progression_stage" not in run.artifacts["item"].slots


def test_a_module_does_not_freeze_while_something_it_references_is_open(reg):
    run = run_cycle(reg, "E", _fake_model({**_ALL_GOOD,
                                           "progression_kind": [_BAD_TAGS]}),
                    evidence_n=11, heal_rounds=0)
    assert "item" not in run.artifacts, (
        "progression_kind is in item's closure via item_archetype.gates_on"
    )
    assert any("item: not frozen" in line and "progression_kind" in line
               for line in run.log)


def test_the_freeze_digest_is_of_content_not_of_order(reg):
    a = run_cycle(reg, "E", _fake_model(_ALL_GOOD), evidence_n=11)
    b = run_cycle(reg, "E", _fake_model(_ALL_GOOD), evidence_n=11)
    assert a.digest == b.digest


# ── the two kinds that had never run (PARTITION, CONFIRM) ───────────────────

def test_the_planner_assigns_ordinals_per_group_from_the_returned_order(reg):
    """`QTY-A5` — order in, numbers out. Two groups, each numbered 1..N in its own
    right; a global 1..N across groups would be the bug this shape prevents."""
    from app.pool.kinds import Ladder
    members = json.loads(_GOOD_STAGES)["members"]
    out = Ladder().finalize(reg["progression_stage"], members)
    by_kind: dict[str, list[int]] = {}
    for m in out:
        by_kind.setdefault(m["body"]["kind"], []).append(m["ordinal"])
    assert by_kind == {"cultivation_realm": [1, 2, 3, 4], "skill_mastery": [1, 2]}
    assert [m["code"] for m in out] == [m["code"] for m in members], "order preserved"


def test_ordinals_are_stamped_only_after_the_slot_settles(reg):
    """If the planner stamped before validation, `no_model_assigned_ordinal` would be
    reading the planner's own field and could never fail (`NV-1`)."""
    run = run_cycle(reg, "E", _fake_model(_ALL_GOOD), evidence_n=11,
                    approve=lambda slot, members: slot.id != "progression_stage")
    assert run.slots["progression_stage"].state is State.PROPOSED
    assert all("ordinal" not in m for m in run.slots["progression_stage"].members), (
        "an unapproved ladder must carry no numbers — it is still changing"
    )


def test_a_model_assigned_ordinal_is_a_hard_failure(reg):
    numbered = [{**m, "ordinal": i + 1}
                for i, m in enumerate(json.loads(_GOOD_STAGES)["members"])]
    v = criteria.evaluate(reg["progression_stage"], numbered, [])
    assert v.hard_broken
    assert any(f.criterion == "no_model_assigned_ordinal" for f in v.findings)


def test_a_group_with_one_band_is_not_a_partition(reg):
    members = json.loads(_GOOD_STAGES)["members"][:5]      # drops one skill_mastery band
    v = criteria.evaluate(reg["progression_stage"], members, [])
    assert v.hard_broken
    assert any(f.criterion == "every_group_is_a_partition" for f in v.findings)


def test_confirm_keeps_a_declared_default_without_evidence(reg):
    """The asymmetry the operation has: the platform already carried the burden of
    proof for what it declared, so keeping it costs nothing."""
    members = json.loads(_GOOD_KINDS)["members"]
    refused = json.loads(_GOOD_KINDS)["refused"]
    v = criteria.evaluate(reg["progression_kind"], members, refused)
    assert v.passed, v


def test_confirm_rejects_an_addition_with_no_evidence(reg):
    members = json.loads(_GOOD_KINDS)["members"] + [
        {"code": "bloodline", "name": {"en": "bloodline"}, "provenance": "PROPOSED",
         "evidence": None}]
    v = criteria.evaluate(reg["progression_kind"], members, [])
    assert v.hard_broken
    assert any(f.criterion == "additions_carry_evidence" for f in v.findings)


# ── the reference check (it needs the pool, so it needs the loop to pass it) ─

def test_a_reference_to_a_code_no_settled_slot_provides_is_a_hard_failure(reg):
    members = [{"code": "sword", "name": {"en": "s"}, "provenance": "CITED",
                "evidence": {"kind": "span"},
                "body": {"class": "Weapon", "instrument_tags": ["blade"],
                         "gates_on": ["qi_refinement"]}}]
    pool = {"instrument_tag": [{"code": "blade"}],
            "progression_kind": [{"code": "cultivation_realm"}]}
    v = criteria.evaluate(reg["item_archetype"], members, [],
                          registry_enums=reg.engine_enums, pool=pool)
    assert v.hard_broken
    assert any(f.criterion == "references_resolve" for f in v.findings)


def test_the_loop_actually_passes_the_pool_to_the_criteria(reg):
    """The check above is optional-by-default, so it is default-uncovered unless the
    loop supplies the pool. This asserts the loop does — otherwise a broken reference
    would only be caught by the register, one step too late to heal."""
    bad_arch = json.dumps({"members": [
        {"code": "sword", "name": {"en": "sword"}, "provenance": "CITED",
         "evidence": {"kind": "span", "chunk": "ch65"},
         "body": {"class": "Weapon", "instrument_tags": ["blade"],
                  "gates_on": ["no_such_kind"]}},
        {"code": "banner", "name": {"en": "banner"}, "provenance": "CITED",
         "evidence": {"kind": "span", "chunk": "ch65"},
         "body": {"class": "Tool", "instrument_tags": ["haft"]}},
    ], "refused": []})
    run = run_cycle(reg, "E", _fake_model({**_ALL_GOOD, "item_archetype": [bad_arch]}),
                    evidence_n=11, heal_rounds=0)
    assert run.slots["item_archetype"].state is State.PROPOSED
    assert "references_resolve" in run.slots["item_archetype"].verdict
    assert not run.frozen


