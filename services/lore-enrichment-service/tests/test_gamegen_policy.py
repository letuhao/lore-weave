"""S4 — the numeric policy: coverage, narrowing, and `PGN-A16`'s integers.

No DB, no port, no network — deliberately no ``xdist_group`` mark.

The two properties this stage claims are both refusals, and both are tested for
their failing half first: **coverage** (a magnitude with no band) and
**narrowing** (a book policy that widens). A policy module that only proved it can
represent a policy would prove nothing doc 39 §6 asks for.
"""

from __future__ import annotations

import pytest

from app.gamegen.brief import load_contract
from app.gamegen.policy import (
    Band,
    Policy,
    PolicyError,
    assert_covers_magnitudes,
    body_json,
    from_body,
    magnitude_paths,
    narrow,
    policy_hash,
)

FP = load_contract()["fingerprint"]


def full_bands(**over) -> dict[str, Band]:
    b = {p: Band(0, 1000, 100) for p in magnitude_paths()}
    b.update(over)
    return b


def system(**over) -> Policy:
    return Policy(
        element_kind="progression_system", schema_fingerprint=FP, tier="system",
        policy_version=1, bands=full_bands(**over),
    )


# ── coverage, asserted against the engine's own schema ──────────────────────


def test_the_magnitude_set_comes_from_the_generated_contract() -> None:
    """Not re-derived here — a second implementation of a Rust type is a mirror
    nothing forces to agree (`CPL-A2`). These are the seven `PGN-A5` classes."""
    assert magnitude_paths() == {
        "kind.curve.rate_milli",
        "kind.curve.base_rate_milli",
        "kind.curve.difficulty_milli",
        "kind.cap_rule.cap",
        "kind.initial_value",
        "kind.derives_from.rate_factor_milli",
        "kind.tier[].tier_max",
    }


def test_a_complete_policy_covers_its_magnitudes() -> None:
    assert_covers_magnitudes(system())


def test_a_magnitude_with_NO_band_is_refused() -> None:
    """**The failing half.** S5 would invent the number and the engine's default
    would ship wearing this policy's signature."""
    bands = full_bands()
    del bands["kind.tier[].tier_max"]
    p = Policy(element_kind="progression_system", schema_fingerprint=FP, tier="system",
               policy_version=1, bands=bands)
    with pytest.raises(PolicyError) as e:
        assert_covers_magnitudes(p)
    assert "kind.tier[].tier_max" in str(e.value)
    assert "wearing this policy's signature" in str(e.value)


def test_a_band_for_a_NON_magnitude_is_refused() -> None:
    """Set equality runs both ways. A knob nothing reads gets tuned by someone
    watching for an effect that cannot arrive."""
    p = Policy(element_kind="progression_system", schema_fingerprint=FP, tier="system",
               policy_version=1, bands=full_bands(**{"kind.tier_count": Band(1, 9, 9)}))
    with pytest.raises(PolicyError) as e:
        assert_covers_magnitudes(p)
    assert "does not class as a magnitude" in str(e.value)


def test_an_EMPTY_policy_is_refused() -> None:
    p = Policy(element_kind="progression_system", schema_fingerprint=FP, tier="system",
               policy_version=1, bands={})
    with pytest.raises(PolicyError):
        assert_covers_magnitudes(p)


def test_a_policy_authored_against_a_MOVED_schema_is_refused() -> None:
    """A magnitude may have been added, removed, or RECLASSIFIED — the last one
    matters most, and the path list alone cannot see it."""
    p = Policy(element_kind="progression_system", schema_fingerprint="0" * 64,
               tier="system", policy_version=1, bands=full_bands())
    with pytest.raises(PolicyError) as e:
        assert_covers_magnitudes(p)
    assert "schema MOVED" in str(e.value)
    assert "reclassified" in str(e.value)


# ── PGN-A15: a book NARROWS, and cannot widen ───────────────────────────────


def test_a_book_policy_narrows_and_inherits_the_rest() -> None:
    """One knob narrowed, six inherited — which is what makes S4 *review of a diff
    against a shipped baseline* rather than authorship."""
    child = narrow(parent=system(), book_version=1,
                   child_bands={"kind.tier[].tier_max": Band(200, 400, 300)})
    assert child.tier == "book"
    assert child.bands["kind.tier[].tier_max"] == Band(200, 400, 300)
    assert child.bands["kind.initial_value"] == Band(0, 1000, 100), "inherited"
    assert_covers_magnitudes(child)


def test_a_book_policy_that_WIDENS_is_refused_by_path() -> None:
    """**`PGN-A15` itself.** Without this, *narrow* is a word in a document and a
    book policy is a second global policy with extra steps."""
    with pytest.raises(PolicyError) as e:
        narrow(parent=system(), book_version=1,
               child_bands={"kind.cap_rule.cap": Band(0, 5000, 100)})
    assert "kind.cap_rule.cap" in str(e.value)
    assert "WIDENS" in str(e.value)
    assert "ceiling, not a suggestion" in str(e.value)


def test_widening_only_the_LOWER_bound_is_also_refused() -> None:
    """Containment is two-sided. A book that lowers a floor has widened just as
    surely as one that raises a ceiling, and only one of those is intuitive."""
    with pytest.raises(PolicyError) as e:
        narrow(parent=system(**{"kind.initial_value": Band(50, 500, 100)}),
               book_version=1, child_bands={"kind.initial_value": Band(0, 500, 100)})
    assert "WIDENS" in str(e.value)


def test_an_equal_band_is_a_legal_narrowing() -> None:
    """Containment, not strict containment — restating a band unchanged is how an
    author says *"I looked at this one and kept it"*, which is a real review
    signal and must not be an error."""
    narrow(parent=system(), book_version=1,
           child_bands={"kind.initial_value": Band(0, 1000, 100)})


def test_a_book_cannot_introduce_a_knob_the_system_does_not_have() -> None:
    """Introducing is authorship. It is how a per-book override quietly becomes a
    second global policy."""
    parent = Policy(element_kind="progression_system", schema_fingerprint=FP,
                    tier="system", policy_version=1,
                    bands={p: Band(0, 10, 5) for p in magnitude_paths()
                           if p != "kind.initial_value"})
    with pytest.raises(PolicyError) as e:
        narrow(parent=parent, book_version=1,
               child_bands={"kind.initial_value": Band(0, 10, 5)})
    assert "introduces" in str(e.value)
    assert "authorship" in str(e.value)


def test_a_book_policy_cannot_be_narrowed_again() -> None:
    """A chain could otherwise widen one step at a time with every individual step
    looking legal."""
    child = narrow(parent=system(), book_version=1,
                   child_bands={"kind.cap_rule.cap": Band(100, 200, 150)})
    with pytest.raises(PolicyError) as e:
        narrow(parent=child, book_version=2,
               child_bands={"kind.cap_rule.cap": Band(100, 200, 150)})
    assert "only a System policy may be narrowed" in str(e.value)


# ── PGN-A16: fixed-point saturating integers ────────────────────────────────


def test_a_float_band_is_refused() -> None:
    """A float makes S5's output depend on IEEE rounding, and T4 (*same inputs →
    same artifact*) would hold only on one platform's libm."""
    with pytest.raises(PolicyError) as e:
        Band(0, 1000.5, 100)
    assert "PGN-A16" in str(e.value)


def test_a_BOOLEAN_band_is_refused() -> None:
    """``isinstance(True, int)`` is True in Python, so without an explicit arm
    ``True`` is a legal rate of 1 and a policy typo becomes a balance decision."""
    with pytest.raises(PolicyError) as e:
        Band(0, True, 0)
    assert "not an integer" in str(e.value)


def test_an_inverted_band_is_refused() -> None:
    with pytest.raises(PolicyError):
        Band(500, 100, 200)


def test_a_default_outside_its_own_band_is_refused() -> None:
    """Every check green, and S5 emitting a number no reviewer could have
    chosen."""
    with pytest.raises(PolicyError) as e:
        Band(0, 100, 500)
    assert "outside its own band" in str(e.value)


def test_a_fixed_knob_is_expressible() -> None:
    """``min == max`` is how an author says *"this one is deliberately not a
    choice"* — refusing it would push that intent into a comment."""
    narrow(parent=system(), book_version=1,
           child_bands={"kind.cap_rule.cap": Band(300, 300, 300)})


# ── the hash, and what it must separate ─────────────────────────────────────


def test_the_policy_hash_separates_the_TIER() -> None:
    """The same numbers shipped as a System baseline and as one book's narrowing
    are different facts about WHO CHOSE THEM, and T2 is *"I can tell where a
    number came from"*."""
    sysp = system()
    bookp = Policy(element_kind=sysp.element_kind, schema_fingerprint=FP, tier="book",
                   policy_version=1, bands=sysp.bands)
    assert body_json(sysp) == body_json(bookp)
    assert policy_hash(sysp) != policy_hash(bookp)


def test_the_policy_hash_moves_with_any_band() -> None:
    assert policy_hash(system()) != policy_hash(
        system(**{"kind.initial_value": Band(0, 1000, 101)})
    )


def test_the_policy_hash_is_stable_and_order_independent() -> None:
    """Two dicts with the same pairs in different insertion order are the same
    policy; a hash that disagreed would make re-publishing an unchanged baseline
    look like a balance change."""
    a = system()
    reordered = Policy(element_kind=a.element_kind, schema_fingerprint=FP, tier="system",
                       policy_version=1,
                       bands={p: a.bands[p] for p in sorted(a.bands, reverse=True)})
    assert policy_hash(a) == policy_hash(reordered)


def test_a_policy_round_trips_through_its_stored_body() -> None:
    a = system(**{"kind.cap_rule.cap": Band(10, 20, 15)})
    b = from_body(element_kind=a.element_kind, schema_fingerprint=FP, tier="system",
                  policy_version=1, body=body_json(a))
    assert policy_hash(a) == policy_hash(b)


def test_an_unknown_tier_is_refused() -> None:
    with pytest.raises(PolicyError):
        Policy(element_kind="progression_system", schema_fingerprint=FP, tier="global",
               policy_version=1, bands=full_bands())
