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

from app.generators import item_l2, loot_l2
from app.pool.consume import MissingSlot, NotVisible, PoolView
from app.pool.freeze import (Freeze, FrozenSlot, closure_for, consumers_of,
                             digest_of, freeze_of)
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
         "body": {"class": "Weapon", "instrument_tags": ["blade"],
                  "equip_slot": "main_hand"}},
        {"code": "banner", "name": {"en": "banner"}, "provenance": "CITED",
         "evidence": {"kind": "span"},
         "body": {"class": "Tool", "instrument_tags": ["ward"]}},
    ],
    "equip_slot": [
        {"code": "main_hand", "name": {"en": "main hand"}, "provenance": "DECLARED"},
        {"code": "body", "name": {"en": "body"}, "provenance": "DECLARED"},
    ],
}


@pytest.fixture
def view(reg):
    return PoolView(freeze_of(reg, SETTLED), consumer="item")


def _private(reg, slot_id: str, *, owner: str, also_private: str = ""):
    """A registry with one slot forced PRIVATE, bypassing the load-time invariant.

    The invariant is real and the registry obeys it, which leaves the withholding
    path with no production subject. Constructing one here is legitimate — the code
    under test reads visibility as DATA — but it has to be visible that this is
    constructed, hence a named helper rather than an inline `replace`."""
    from dataclasses import replace
    from app.pool.registry import Registry, Visibility as V
    slots = dict(reg.slots)
    slots[slot_id] = replace(slots[slot_id], visibility=V.PRIVATE, owner=owner)
    if also_private:
        slots[also_private] = replace(slots[also_private], visibility=V.PRIVATE,
                                      owner=owner)
    return Registry(slots=slots, engine_enums=reg.engine_enums)


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
    assert {u.target for u in back.unmet} == {"lex_tag"}, (
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
    assert item == {"instrument_tag", "item_archetype", "progression_kind", "equip_slot"}
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
                                           "progression_kind", "equip_slot"}


def test_a_scoped_freeze_carries_only_the_unmet_targets_its_own_slots_want(reg):
    f = freeze_of(reg, SETTLED, scope={"instrument_tag", "item_archetype"})
    assert {u.target for u in f.unmet} == {"lex_tag"}
    narrow = freeze_of(reg, SETTLED, scope={"instrument_tag"})
    assert narrow.unmet == (), (
        "instrument_tag references nothing, so it is waiting on nothing — a hole "
        "another slot has is not this scope's to report"
    )


# ── the refusals ────────────────────────────────────────────────────────────

def test_an_unregistered_slot_raises_and_names_who_else_is_waiting(view):
    """The alternative is `[]`, which reads as *this world has no lexical tags* when
    the truth is *nobody has decided yet*. This project shipped that exact confusion
    twice already."""
    with pytest.raises(MissingSlot, match="no module has registered it"):
        view.members("lex_tag")
    with pytest.raises(MissingSlot, match="item_archetype.lex_tags"):
        view.members("lex_tag")


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

def test_the_contract_supplies_three_of_fourteen_item_fields_and_is_blocked_on_one(view):
    """`ICT-A2` says the item module's pool footprint is SMALL and its bulk is
    tier 2. This is that claim with a number, computed against a real freeze."""
    c = item_l2.census(view)
    assert c.total == len(item_l2.ITEM_DEF_FIELDS) == 14
    assert set(c.frozen) == {"class", "instrument_tags", "equip"}
    assert {f for f, _ in c.blocked} == {"lex_tags"}
    assert len(c.own) == 10
    assert c.contract_reach == 0.75, (
        "it was 0.5 until item registered equip_slot. The remaining quarter is "
        "lex_tag, which WA_001 owns and item cannot close — and it is the same "
        "target the abductive register reports. Two independent mechanisms, one "
        "answer."
    )


def test_the_blocked_fields_are_exactly_the_registers_unmet_targets(view, reg):
    """The convergence is the point. If these two ever disagree, one of them is
    reading a stale list."""
    blocked_slots = {f.slot for f in item_l2.ITEM_DEF_FIELDS
                     if f.source is item_l2.Source.BLOCKED}
    assert blocked_slots == set(reg.dangling_targets()) == {"lex_tag"}, (
        "this used to read `set(dangling) | {'lex_tag'}` — the union was papering "
        "over a real disagreement, because lex_tag was named in a DOCUMENT and "
        "referenced by nothing, so the register could not see it. Writing it as a "
        "reference on item_archetype made the two agree without a fudge."
    )


# ── the SECOND consumer: does contract alone suffice? ───────────────────────

def test_a_module_that_owns_no_slot_still_gets_a_contract(reg):
    """`loot` owns nothing. `item_archetype.consumed_by` has named `loot.table`
    since the slot was registered, and an ownership-seeded closure handed it the
    empty set — a consumer with no contract, which the architecture has no account
    of. The declaration was already there, read by nothing."""
    assert "loot" in consumers_of(reg)
    assert not [s for s in reg.slots.values() if s.owner == "loot"]
    assert closure_for(reg, "loot") == {"item_archetype", "instrument_tag",
                                        "progression_kind", "equip_slot"}


def test_the_second_generator_does_its_job_from_contract_alone(reg):
    """The falsifiable question `PPB-A6` asserts an answer to. If a drop table
    needed the item generator's ItemDefs, the two-layer split would be wrong."""
    v = PoolView(freeze_of(reg, SETTLED, scope=closure_for(reg, "loot"),
                           for_consumer="loot"), consumer="loot")
    table = loot_l2.build(v)
    assert [r.archetype for r in table.rows] == ["sword", "banner"]
    assert table.rows[0].item_class == "Weapon"
    assert table.pool_digest == v.digest
    assert set(r.archetype for r in table.rows) <= set(v.codes("item_archetype")), (
        "every row must name something the CONTRACT has; a row naming anything else "
        "came from somewhere this generator should not be reading"
    )

    # `assert not hasattr(r, "def_id")` was the first attempt and it can never fail:
    # DropRow has no such field, so the assertion re-states the class definition
    # instead of testing anything (`NV-1`). Pinning the field SET does have a
    # possible violation — adding `def_id` to the row reds here, which is the moment
    # the decision would actually be made.
    import dataclasses
    assert {f.name for f in dataclasses.fields(loot_l2.DropRow)} == {
        "archetype", "item_class", "instrument_tags"}, (
        "a row naming a concrete def would be reading item's L2, and would have to be "
        "regenerated every time item regenerated"
    )


def test_a_shared_slot_may_not_reference_a_private_one(reg, tmp_path):
    """The invariant the second consumer produced, and it did not come from
    reasoning — it came from a test failing.

    `equip_slot` was registered PRIVATE on a sound argument: item is the only
    referrer. Withholding its members from loot's artifact then left `item_archetype`
    — SHARED — carrying `"equip_slot": "main_hand"` in its bodies. Two individually
    correct decisions; the privacy defeated by their combination, which is the third
    shape `NV` names. Visibility may not decrease along a reference."""
    raw = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for s in raw["slots"]:
        if s["id"] == "equip_slot":
            s["visibility"] = "PRIVATE"
    bad = tmp_path / "registry.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="SHARED and references"):
        load_registry(bad)


def test_no_slot_can_be_private_while_a_shared_slot_points_at_it(reg):
    """The consequence, stated so it is not mistaken for an oversight: `EPL-A7`'s
    PRIVATE branch has NO production subject, and cannot have one for any slot a
    shared slot references. Every registered slot is SHARED today for that reason,
    not by default. The withholding machinery below is exercised on constructed
    data, and that is the honest description of its coverage."""
    assert {s.visibility for s in reg.slots.values()} == {Visibility.SHARED}
    referenced = {f.target_slot for s in reg.slots.values() for f in s.refs()}
    assert referenced == {"instrument_tag", "equip_slot", "progression_kind", "lex_tag"}


def test_a_private_slot_is_WITHHELD_from_another_consumers_artifact(reg):
    """Withholding the MEMBERS is what enforces `EPL-A7` — if they travelled and
    only the reader refused, the rule would rest on the good manners of whoever
    opened the file. Constructed subject, per the test above."""
    scope = closure_for(reg, "loot")
    hidden = _private(reg, "instrument_tag", owner="item")
    art = freeze_of(hidden, SETTLED, scope=scope, for_consumer="loot")
    assert art.withheld == ("instrument_tag",)
    assert "instrument_tag" not in art.slots, "the MEMBERS must not be in the bytes"

    for_item = freeze_of(hidden, SETTLED, scope=closure_for(hidden, "item"),
                         for_consumer="item")
    assert for_item.withheld == () and "instrument_tag" in for_item.slots


def test_a_withheld_slot_is_NOT_VISIBLE_rather_than_missing(reg):
    """Named but not carried, so *may not look* stays distinguishable from *is not
    there*. Dropping it silently would have loot conclude the world has no
    instrument tags — the exact confusion this project has now caught three times."""
    hidden = _private(reg, "instrument_tag", owner="item")
    v = PoolView(freeze_of(hidden, SETTLED, scope=closure_for(hidden, "loot"),
                           for_consumer="loot"), consumer="loot")
    with pytest.raises(NotVisible, match="WITHHELD"):
        v.members("instrument_tag")
    assert v.has("instrument_tag") is False
    assert "instrument_tag" not in v.visible_slots()


def test_the_second_generator_reports_what_it_could_not_reach(reg):
    """A generator that silently worked around a refusal would hide the decision a
    human has to make. Three different ways a contract can fail a consumer, and
    they must not collapse into one."""
    hidden = _private(reg, "equip_slot", owner="item", also_private="item_archetype")
    v = PoolView(freeze_of(hidden, SETTLED, scope=closure_for(hidden, "loot"),
                           for_consumer="loot"), consumer="loot")
    reasons = loot_l2.what_it_could_not_reach(v)
    assert any(r.startswith("equip_slot: NOT VISIBLE") for r in reasons)
    assert any(r.startswith("lex_tag: MISSING") for r in reasons)
    assert any(r.startswith("item_rarity: MISSING") for r in reasons)
    assert len(reasons) == 3


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


def test_a_generator_is_a_pure_function_of_its_view():
    """The import check alone does not close `PPB-A6`. Once one generator's output
    is persisted, a second could read it with `json.load(path)` and import nothing
    suspicious — the boundary would hold in the import graph and leak through the
    filesystem.

    So a generator gets no I/O at all: it receives a `PoolView` and returns a value,
    and persistence is the pipeline's job. That is checkable, and it is checkable
    NOW, before any L2 store exists — which matters, because the natural moment to
    add this check is the moment it is already too late."""
    io_modules = {"pathlib", "os", "io", "shutil", "sqlite3", "requests", "httpx",
                  "urllib", "urllib.request", "socket", "subprocess"}
    files = sorted((APP / "generators").rglob("*.py"))
    assert files
    for f in files:
        bad = _imports(f) & io_modules
        assert not bad, (
            f"{f.name} imports {sorted(bad)}. A generator is a pure function of its "
            f"view; if it needs to persist something, the caller persists it.")
        src = f.read_text(encoding="utf-8")
        tree = ast.parse(src)
        calls = {n.func.id for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "open" not in calls, f"{f.name} calls open()"


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
