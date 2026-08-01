"""`PPB-A6` stops being a rule and becomes a mechanism.

*No module ever reads another module's L2 output* has been written in doc 03 since
the redesign, enforced by nobody. The pool was produced, hashed, and read by
nothing, so the claim had never been under load in either direction: no consumer
existed to violate it, and none existed to prove it was satisfiable either.

These tests are the load. Three independent things have to hold, and each fails a
different way:

* the freeze is **usable** — a consumer given only the artifact can do its work
* the freeze is **binding** — a value outside it is refused, not tolerated
* the boundary is **structural** — crossing it requires an import that reds here,
  not a lapse of discipline that reds in code review
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from app.generators import item_l2
from app.pool.consume import MissingSlot, NotVisible, PoolView
from app.pool.freeze import (Freeze, FrozenSlot, closure_for, digest_of,
                             freeze_of)
from app.pool.registry import Visibility, load_registry

REGISTRY = pathlib.Path(__file__).resolve().parents[3] / "contracts" / "pool" / "registry.json"
APP = pathlib.Path(__file__).resolve().parents[1] / "app"


@pytest.fixture(scope="module")
def reg():
    return load_registry(REGISTRY)


SETTLED = {
    "instrument_tag": [
        {"code": "blade", "name": {"en": "blade"}, "covers": ["sword"], "provenance": "PROPOSED"},
        {"code": "ward", "name": {"en": "ward"}, "covers": ["banner"], "provenance": "PROPOSED"},
    ],
    "item_archetype": [
        {"code": "sword", "name": {"en": "sword"}, "provenance": "CITED",
         "evidence": {"kind": "span"},
         "body": {"class": "Weapon", "instrument_tags": ["blade"]}},
        {"code": "banner", "name": {"en": "banner"}, "provenance": "CITED",
         "evidence": {"kind": "span"},
         "body": {"class": "Tool", "instrument_tags": ["ward"]}},
    ],
}


@pytest.fixture
def view(reg):
    return PoolView(freeze_of(reg, SETTLED), consumer="item")


def _rehash(f: Freeze, slots: dict) -> Freeze:
    """Rebuild a freeze around edited slots, re-deriving the digest.

    Written after the first draft of the visibility tests constructed a `Freeze`
    with different members and the ORIGINAL digest — and `verify()` refused it,
    correctly. The check caught the test.
    """
    built = Freeze(digest="", slots=slots, unmet=f.unmet)
    return Freeze(digest=digest_of(built.pool), slots=slots, unmet=f.unmet)


# ── the artifact ────────────────────────────────────────────────────────────

def test_a_freeze_survives_a_round_trip_through_a_file(tmp_path, reg):
    f = freeze_of(reg, SETTLED)
    p = tmp_path / "pool.freeze.json"
    f.write(p)
    back = Freeze.read(p)                       # read() verifies
    assert back.digest == f.digest
    assert back.pool == f.pool
    assert {u.target for u in back.unmet} == {"equip_slot"}, (
        "the hole travels WITH the artifact — a consumer must not have to consult "
        "the registry to learn what the contract could not source"
    )


def test_an_edited_freeze_refuses_to_load(tmp_path, reg):
    """A digest stored beside content and never recomputed is a label. A consumer
    PINS this digest into what it generates, so a mismatched artifact would put a
    truthful-looking provenance on different bytes."""
    p = tmp_path / "pool.freeze.json"
    freeze_of(reg, SETTLED).write(p)
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw["slots"]["instrument_tag"]["members"][0]["code"] = "tampered"
    p.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        Freeze.read(p)


def test_an_unknown_schema_version_refuses_rather_than_reads_a_moved_field(reg):
    f = freeze_of(reg, SETTLED)
    bumped = Freeze(digest=f.digest, slots=f.slots, unmet=f.unmet, schema_version=99)
    with pytest.raises(ValueError, match="schema_version"):
        bumped.verify()


def test_the_freeze_digest_is_the_one_the_loop_computes(reg):
    """One digest function, or the checksum quietly stops checking."""
    assert freeze_of(reg, SETTLED).digest == digest_of(SETTLED)


def test_a_closure_is_neither_the_module_nor_the_whole_pool(reg):
    """Both wrong answers are available and both were tried. The module alone drops
    `progression_kind`, which `item_archetype.gates_on` points at — the artifact
    would carry an unresolvable code. The whole pool drags in `progression_stage`,
    which item never references and which blocked three live runs."""
    item = closure_for(reg, "item")
    assert item == {"instrument_tag", "item_archetype", "progression_kind"}
    assert {s.id for s in reg.slots.values() if s.owner == "item"} < item
    assert item < set(reg.slots)


def test_a_closure_terminates_on_a_reference_cycle(reg):
    """`item_archetype -> progression_kind` and a hypothetical way back. The walk
    is over a graph, and a graph the authors control is still a graph."""
    from dataclasses import replace
    from app.pool.registry import FieldRef, Registry
    looped = Registry(
        slots={**reg.slots,
               "progression_kind": replace(
                   reg["progression_kind"],
                   member=(FieldRef("back", "slot:item_archetype"),))},
        engine_enums=reg.engine_enums)
    assert closure_for(looped, "item") == {"instrument_tag", "item_archetype",
                                           "progression_kind"}


def test_a_scoped_freeze_carries_only_the_unmet_targets_its_own_slots_want(reg):
    f = freeze_of(reg, SETTLED, scope={"instrument_tag", "item_archetype"})
    assert {u.target for u in f.unmet} == {"equip_slot"}
    narrow = freeze_of(reg, SETTLED, scope={"instrument_tag"})
    assert narrow.unmet == (), (
        "instrument_tag references nothing, so it is waiting on nothing — a hole "
        "another slot has is not this scope's to report"
    )


# ── the refusals ────────────────────────────────────────────────────────────

def test_an_unregistered_slot_raises_and_names_who_else_is_waiting(view):
    """The alternative is `[]`, which reads as *this world has no equip slots* when
    the truth is *nobody has decided yet*. This project shipped that exact confusion
    twice already."""
    with pytest.raises(MissingSlot, match="no module has registered it"):
        view.members("equip_slot")
    with pytest.raises(MissingSlot, match="item_archetype.equip_slot"):
        view.members("equip_slot")


def test_a_private_slot_belonging_to_another_module_is_refused(reg):
    """`EPL-A7` draws the SHARED/PRIVATE line, and until the consumer existed there
    was nothing on the other side of it. Both registered slots are SHARED today, so
    the subject is constructed — the check is over the freeze's DATA, and that data
    varies."""
    f = freeze_of(reg, SETTLED)
    private = Freeze(
        digest=f.digest,
        slots={**f.slots,
               "instrument_tag": FrozenSlot("instrument_tag", owner="progression",
                                            visibility=Visibility.PRIVATE,
                                            members=f.slots["instrument_tag"].members)},
        unmet=f.unmet)
    v = PoolView(private, consumer="item")
    with pytest.raises(NotVisible, match="PRIVATE to 'progression'"):
        v.members("instrument_tag")
    assert PoolView(private, consumer="progression").codes("instrument_tag") == ("blade", "ward")


def test_may_not_look_and_looked_and_found_nothing_are_different_answers(reg):
    f = freeze_of(reg, SETTLED)
    private = _rehash(f, {**f.slots,
                          "instrument_tag": FrozenSlot("instrument_tag", owner="progression",
                                                       visibility=Visibility.PRIVATE,
                                                       members=())})
    v = PoolView(private, consumer="item")
    assert v.has("instrument_tag") is False
    with pytest.raises(NotVisible):
        v.members("instrument_tag")


def test_a_view_must_name_its_consumer(reg):
    with pytest.raises(ValueError, match="name its consumer"):
        PoolView(freeze_of(reg, SETTLED), consumer="")


# ── the freeze as a CONSTRAINT, not as data ─────────────────────────────────

def test_a_planned_def_carries_only_what_the_contract_fixed(view):
    plans = item_l2.plan(view)
    assert [p.archetype for p in plans] == ["sword", "banner"]
    assert plans[0].item_class == "Weapon" and plans[0].instrument_tags == ("blade",)
    assert all(p.pool_digest == view.digest for p in plans)
    assert all(p.display_name == {} for p in plans), (
        "the spine must not invent vocabulary — that is the model's half (EPL-A6)"
    )


def test_a_def_that_reaches_outside_the_frozen_codes_is_refused(view):
    ok, bad = item_l2.accept(view, [
        {"archetype": "sword", "class": "Weapon", "instrument_tags": ["blade"],
         "display_name": {"en": "Jade Blade"}},
        {"archetype": "sword", "class": "Armor", "instrument_tags": ["blade"]},
        {"archetype": "sword", "class": "Weapon", "instrument_tags": ["blade", "invented"]},
        {"archetype": "airship", "class": "Weapon", "instrument_tags": []},
    ])
    assert [d["display_name"]["en"] for d in ok] == ["Jade Blade"]
    assert [(r.field_name, r.archetype) for r in bad] == [
        ("class", "sword"), ("instrument_tags", "sword"), ("archetype", "airship")]


def test_a_tag_that_belongs_to_a_DIFFERENT_archetype_is_still_the_wrong_tag(view):
    """The looseness a live run hid. `accept` first checked membership in the union
    of all frozen tags, and the run passed 14 of 14 — it would have passed just as
    happily with every tag shuffled between archetypes, because every code was
    frozen. A closed set that is not the RIGHT closed set admits the error it was
    written to catch."""
    ok, bad = item_l2.accept(view, [
        {"archetype": "sword", "class": "Weapon", "instrument_tags": ["ward"]},
    ])
    assert not ok
    assert bad[0].field_name == "instrument_tags" and bad[0].value == ["ward"]
    assert "different archetype" in bad[0].why


def test_a_def_may_NARROW_its_archetypes_tags(view):
    """Subset, not equality. The archetype says what a thing of this kind CAN carry;
    a concrete def carrying fewer is a decision, not a violation."""
    ok, bad = item_l2.accept(view, [
        {"archetype": "sword", "class": "Weapon", "instrument_tags": []},
    ])
    assert ok and not bad


def test_an_accepted_def_pins_the_pool_it_was_generated_against(view):
    ok, _ = item_l2.accept(view, [{"archetype": "sword", "class": "Weapon",
                                   "instrument_tags": []}])
    assert ok[0]["pool_digest"] == view.digest, (
        "a def that cannot name its contract version is a def nobody can re-derive"
    )


# ── the measurement ICT-A2 asserts without a number ─────────────────────────

def test_the_contract_supplies_two_of_fourteen_item_fields_and_is_blocked_on_two(view):
    """`ICT-A2` says the item module's pool footprint is SMALL and its bulk is
    tier 2. This is that claim with a number, computed against a real freeze."""
    c = item_l2.census(view)
    assert c.total == len(item_l2.ITEM_DEF_FIELDS) == 14
    assert set(c.frozen) == {"class", "instrument_tags"}
    assert {f for f, _ in c.blocked} == {"equip", "lex_tags"}
    assert len(c.own) == 10
    assert c.contract_reach == 0.5, (
        "half of what the CONTRACT owes is blocked on two slots nobody registered — "
        "and they are the same two the abductive register has reported since the "
        "first cycle. Two independent mechanisms, one answer."
    )


def test_the_blocked_fields_are_exactly_the_registers_unmet_targets(view, reg):
    """The convergence is the point. If these two ever disagree, one of them is
    reading a stale list."""
    blocked_slots = {f.slot for f in item_l2.ITEM_DEF_FIELDS
                     if f.source is item_l2.Source.BLOCKED}
    assert blocked_slots == set(reg.dangling_targets()) | {"lex_tag"}
    assert "equip_slot" in reg.dangling_targets()


# ── the boundary is structural ──────────────────────────────────────────────

FORBIDDEN = {"app.pool.loop", "app.pool.criteria", "app.pool.kinds", "app.pool.register"}


def _imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_no_generator_reaches_past_the_freeze():
    """The mechanism `PPB-A6` never had. A generator may import the freeze and the
    view; importing the LOOP, the CRITERIA or the REGISTER means it is reading the
    machinery that produced the pool rather than the pool, and importing another
    generator means it is reading someone else's L2."""
    files = sorted((APP / "generators").rglob("*.py"))
    assert files, "no generators found — this test would pass by having no subject"
    for f in files:
        imports = _imports(f)
        assert not (imports & FORBIDDEN), (
            f"{f.name} imports {sorted(imports & FORBIDDEN)} — that is across the freeze")
        others = {i for i in imports
                  if i.startswith("app.generators.") and not f.name.startswith(i.split(".")[-1])}
        assert not others, f"{f.name} imports another generator: {sorted(others)}"


def test_the_view_exposes_no_way_to_reach_generated_content():
    """The mechanism is an ABSENCE, and an absence needs a test or it erodes. If
    someone adds `view.output_of(module)` this reds, instead of the rule quietly
    becoming a code-review topic again."""
    from app.pool import consume
    surface = {n for n in dir(consume.PoolView)
               if not n.startswith("_") and n not in {"freeze", "consumer"}}
    assert surface == {"digest", "visible_slots", "has", "members", "codes", "member", "unmet"}, (
        f"PoolView's surface changed: {sorted(surface)}. Every method here returns "
        f"CONTRACT (L1). Adding one that returns another module's generated content "
        f"is the thing PPB-A6 forbids, so it has to be a deliberate edit here."
    )
