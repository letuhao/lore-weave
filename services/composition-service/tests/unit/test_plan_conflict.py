"""The comparison half of the plan-liveness check — the part that must NOT be a model's opinion.

Every case here was derived from a live POC on two isolated throwaway books (2026-08-01), not
invented: the extractor's real output shape, glossary's real name columns, and the two failure
modes the POC actually hit (an empty `cached_name`, and a control that agreed with the seed).
"""
from __future__ import annotations

import unicodedata

from app.engine.plan_conflict import (
    PLAN_CONFLICT_KIND,
    asserted_gone,
    name_index,
    norm_name,
    plan_conflicts,
)


class _Eff:
    def __init__(self, entity_ref, status):
        self.entity_ref, self.status = entity_ref, status


class _Ev:
    def __init__(self, *effects):
        self.status_effects = list(effects)


DAO, VIEN = "e-dao", "e-vien"
CAST = [
    {"entity_id": DAO, "cached_name": "Tô Thanh Dao", "cached_aliases": ["Dao", "Thanh Dao"]},
    {"entity_id": VIEN, "cached_name": "Lạc Viên", "cached_aliases": []},
]


# ── the acceptance case ───────────────────────────────────────────────────────────────────

def test_the_MI_DE_defect_is_a_conflict():
    """Scene 1's prose kills her; the plan has her in scene 2. This is the whole run's
    acceptance test, reduced to the comparison."""
    gone = asserted_gone([_Ev(_Eff("Tô Thanh Dao", "gone"))])
    conflicts, unlinked = plan_conflicts(
        gone, name_index(CAST), {DAO: "alive", VIEN: "alive"})
    assert conflicts == [{"entity_id": DAO, "name": "Tô Thanh Dao"}]
    assert unlinked == []


def test_CONTROL_a_scene_that_kills_NOBODY_is_clean():
    """The counterweight the live POC ran as its own control: same cast, same plan, a passage
    whose events carry no status_effects at all. Without this, "always conflict" passes the
    test above and every scene becomes unpublishable."""
    conflicts, unlinked = plan_conflicts(
        asserted_gone([_Ev(), _Ev()]), name_index(CAST), {DAO: "alive", VIEN: "alive"})
    assert conflicts == [] and unlinked == []


def test_a_death_the_plan_does_NOT_contradict_is_not_a_conflict():
    """The character dies and no later scene needs them. That is a story, not a defect — and a
    check that fired here would fire on every planned death in the book."""
    gone = asserted_gone([_Ev(_Eff("Tô Thanh Dao", "gone"))])
    conflicts, _ = plan_conflicts(gone, name_index(CAST), {VIEN: "alive"})
    assert conflicts == []


# ── the join, which is where this quietly fails ───────────────────────────────────────────

def test_an_ALIAS_resolves_to_the_entity():
    """Prose says "Dao"; glossary stores "Tô Thanh Dao". Indexing only the canonical name makes
    the guard blind to the shorter form fiction actually uses."""
    gone = asserted_gone([_Ev(_Eff("Dao", "gone"))])
    conflicts, unlinked = plan_conflicts(gone, name_index(CAST), {DAO: "alive"})
    assert conflicts == [{"entity_id": DAO, "name": "Dao"}] and unlinked == []


def test_DECOMPOSED_vietnamese_diacritics_still_join():
    """The two byte-sequences look identical on screen. The extractor's output and glossary's
    stored name both come from user text, so one side can be NFD — and an un-normalised join
    fails silently on the language this project is written in."""
    nfd = unicodedata.normalize("NFD", "Tô Thanh Dao")
    assert nfd != "Tô Thanh Dao", "fixture is wrong: these must be different strings"
    gone = asserted_gone([_Ev(_Eff(nfd, "gone"))])
    conflicts, _ = plan_conflicts(gone, name_index(CAST), {DAO: "alive"})
    assert conflicts and conflicts[0]["entity_id"] == DAO


def test_an_UNRESOLVABLE_name_is_reported_not_dropped():
    """The failure the live POC hit: glossary held the cast with an EMPTY `cached_name`, so the
    index was empty, the death WAS detected, and nothing linked. A function that returned only
    conflicts would have called that scene clean."""
    gone = asserted_gone([_Ev(_Eff("Mộ Dung Tuyết", "gone"))])
    conflicts, unlinked = plan_conflicts(gone, name_index(CAST), {DAO: "alive"})
    assert conflicts == []
    assert unlinked == ["Mộ Dung Tuyết"], "an unplaceable assertion is a GAP, not a pass"


def test_an_empty_name_index_reports_every_assertion_as_unlinked():
    gone = asserted_gone([_Ev(_Eff("Tô Thanh Dao", "gone"))])
    conflicts, unlinked = plan_conflicts(gone, name_index([]), {DAO: "alive"})
    assert conflicts == [] and unlinked == ["Tô Thanh Dao"]


def test_a_cast_row_with_a_NULL_cached_name_does_not_poison_the_index():
    idx = name_index([{"entity_id": DAO, "cached_name": None, "cached_aliases": None},
                      {"entity_id": VIEN, "cached_name": "Lạc Viên", "cached_aliases": []}])
    assert idx == {norm_name("Lạc Viên"): VIEN}


# ── the extractor's side ──────────────────────────────────────────────────────────────────

def test_only_gone_counts_active_is_not_a_death():
    assert asserted_gone([_Ev(_Eff("Lạc Viên", "active"))]) == {}


def test_dict_shaped_effects_parse_too():
    """The SDK returns models; a persisted job returns JSON. One of those turns up later."""
    got = asserted_gone([{"status_effects": [{"entity_ref": "Dao", "status": "gone"}]}])
    assert got == {norm_name("Dao"): "Dao"}


def test_malformed_effects_are_skipped_not_raised():
    """This runs on a draft the author already paid for — it may not throw."""
    got = asserted_gone([_Ev(_Eff(None, "gone"), _Eff("", "gone"), _Eff("Dao", "gone")),
                         {"status_effects": "not a list"}, None])
    assert got == {norm_name("Dao"): "Dao"}


def test_the_same_person_named_twice_is_one_assertion():
    got = asserted_gone([_Ev(_Eff("Tô Thanh Dao", "gone")), _Ev(_Eff("tô thanh dao", "gone"))])
    assert len(got) == 1


# ── the plan side ─────────────────────────────────────────────────────────────────────────

def test_a_plan_that_says_GONE_is_agreement_not_conflict():
    """The plan rung only emits `alive` today. This pins the explicit `== "alive"` test so a
    future rung that CAN say gone is not read as agreement by an `in` check."""
    gone = asserted_gone([_Ev(_Eff("Tô Thanh Dao", "gone"))])
    conflicts, _ = plan_conflicts(gone, name_index(CAST), {DAO: "gone"})
    assert conflicts == []


def test_no_plan_at_all_yields_no_conflicts():
    gone = asserted_gone([_Ev(_Eff("Tô Thanh Dao", "gone"))])
    assert plan_conflicts(gone, name_index(CAST), None) == ([], [])


def test_the_kind_is_distinct_from_the_gone_entity_present_kind():
    """Two different defects with two different judge questions and two different author
    actions. One name for one concept."""
    assert PLAN_CONFLICT_KIND == "plan_liveness_conflict"
    assert PLAN_CONFLICT_KIND != "gone_entity_present"
