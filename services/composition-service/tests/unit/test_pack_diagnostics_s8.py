"""S8 — the pack's diagnostics ride the job.

Every number here was already computed and then discarded: only `grounding_available` and
`reinjected_promise_count` reached a job result, so *"was anything dropped?"* and *"was the
chapter I am continuing summarised away?"* had no answer anywhere once the request ended.

⚠ THE SEMANTICS v1 OF THIS SLICE INVERTED. `over_budget=True` does NOT mean content was lost.
It means the PROTECTED segments alone exceeded the budget and were KEPT — an oversized prompt,
nothing load-bearing discarded. The silent signals are `dropped_count` and
`l4_dropped_no_position`. Shipping the inverted reading would have produced an alarm that fires
when nothing is wrong and stays quiet when something is.
"""
from __future__ import annotations

from app.packer import budget as B
from app.packer.pack import PackedContext
from app.packer.profile import BookProfile


def _pc(**kw) -> PackedContext:
    base = dict(blocks={}, prompt="", profile=BookProfile(), token_count=0, dropped_count=0,
                l4_dropped_no_position=0, grounding_available=True, over_budget=False)
    base.update(kw)
    return PackedContext(**base)


def test_the_diagnostics_carry_every_number_the_pack_measured():
    d = _pc(dropped_count=3, l4_dropped_no_position=2, recent_floor_compressed=5,
            over_budget=True, token_count=6100, reinjected_promise_count=4,
            warnings=["grounding thin"]).diagnostics()
    assert d == {
        "dropped_count": 3, "l4_dropped_no_position": 2, "recent_floor_compressed": 5,
        "over_budget": True, "token_count": 6100, "grounding_available": True,
        "reinjected_promise_count": 4, "warnings": ["grounding thin"],
    }


def test_over_budget_is_NOT_the_content_loss_signal():
    """A pack can blow its budget having dropped NOTHING — that is what protection means. An
    alarm keyed on `over_budget` fires here, where nothing is wrong."""
    d = _pc(over_budget=True, dropped_count=0, l4_dropped_no_position=0).diagnostics()
    assert d["over_budget"] is True
    assert d["dropped_count"] == 0 and d["l4_dropped_no_position"] == 0


def test_content_CAN_be_lost_while_the_budget_reads_fine():
    """The mirror image, and the reason `dropped_count` is the one to watch: the trim SUCCEEDED
    — it got under budget — by discarding lore and references."""
    d = _pc(over_budget=False, dropped_count=7).diagnostics()
    assert d["over_budget"] is False and d["dropped_count"] == 7


def test_the_two_readings_are_produced_by_the_REAL_budget_pass_not_by_a_stand_in():
    """Both states above are reachable from `enforce_budget` itself, so the semantics under
    test are the shipped ones rather than my description of them."""
    small_protected = [B.Segment("canon", "a rule", B.PRIO_CANON, protected=True)]
    big_protected = [B.Segment("canon", "a rule " * 200, B.PRIO_CANON, protected=True)]
    droppable = [B.Segment("lore", "a hit " * 200, B.PRIO_LORE),
                 B.Segment("lore", "another " * 200, B.PRIO_LORE)]

    # protected ALONE over budget → over_budget True, and nothing droppable existed to lose.
    r1 = B.enforce_budget(big_protected, 10, B.default_counter())
    assert r1.over_budget is True and r1.dropped_count == 0

    # A protected floor that FITS, plus droppable overflow → the trim succeeds (under budget,
    # so `over_budget` is False) by discarding content. The budget must exceed the protected
    # floor for this state to exist at all — the first version of this fixture used the big
    # floor with a 200-token budget, so both halves were over-budget and the test proved the
    # opposite of its own name.
    r2 = B.enforce_budget(small_protected + droppable, 200, B.default_counter())
    assert r2.over_budget is False and r2.dropped_count > 0


def test_recent_floor_compressed_is_carried_because_it_is_the_continuity_signal():
    """`> 0` means the scene is being written against an LLM SUMMARY of its own chapter rather
    than the prose — which is how "He is the anchor" became "She's a Scribe" one scene later.
    It was computed and dropped on the floor before this slice."""
    assert _pc(recent_floor_compressed=4).diagnostics()["recent_floor_compressed"] == 4


def test_warnings_are_COPIED_so_a_consumer_cannot_mutate_the_pack():
    warns = ["grounding thin"]
    d = _pc(warnings=warns).diagnostics()
    d["warnings"].append("injected")
    assert warns == ["grounding thin"]


def test_a_clean_pack_reports_zeros_rather_than_omitting_the_keys():
    """An absent key and a zero are different, and a consumer that treats a missing field as
    "fine" is the silent-empty shape. Every key is always present."""
    d = _pc().diagnostics()
    assert set(d) == {"dropped_count", "l4_dropped_no_position", "recent_floor_compressed",
                      "over_budget", "token_count", "grounding_available",
                      "reinjected_promise_count", "warnings"}
    assert d["dropped_count"] == 0 and d["warnings"] == []
