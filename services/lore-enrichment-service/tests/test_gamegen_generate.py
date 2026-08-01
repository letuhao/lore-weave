"""S5 — generation, and the four things it refuses.

No DB, no network. The load-bearing tests are the refusals: a generator that
produces plausible TOML is easy, and every property doc 39 §7 claims is about what
it declines to produce.
"""

from __future__ import annotations

import pytest

from app.gamegen.brief import load_contract
from app.gamegen.fold import ApprovedAnswer, fold
from app.gamegen.generate import (
    REPAIR_OPS,
    AdmissionRefusal,
    assert_repairs_are_admissible,
    generate,
)
from app.gamegen.policy import Band, Policy, magnitude_paths

FP = load_contract()["fingerprint"]


def _policy(**over) -> Policy:
    b = {p: Band(0, 100_000, 100) for p in magnitude_paths()}
    b.update(over)
    return Policy(element_kind="progression_system", schema_fingerprint=FP,
                  tier="system", policy_version=1, bands=b)


def ans(path, target, value, *, not_stated=False, reason=None) -> ApprovedAnswer:
    return ApprovedAnswer(f"a:{target}:{path}", f"h:{target}:{path}",
                          path.replace(".", "_"), path, target, value, not_stated, reason)


def _body(*, tier_count=2, cap="tier_based", curve="stage", **swap):
    t = "kind:internal_energy"
    answers = [
        ans("kind.quantity", "element:progression_system", ["internal_energy"]),
        ans("kind.name", t, "內功"),
        ans("kind.progression_type", t, "stage"),
        ans("kind.curve", t, curve),
        ans("kind.cap_rule", t, cap),
        ans("kind.initial_tier", t, 0),
        ans("kind.tier_count", t, tier_count),
        ans("kind.tier[].tier_index", t, "ascending"),
        ans("kind.tier[].name", t, "練氣{n:cn}層"),
        ans("kind.tier[].within_tier_curve", t, "linear"),
        ans("kind.tier[].breakthrough", t, "at_max"),
    ]
    for (path, target), repl in swap.pop("replace", {}).items():
        answers = [a for a in answers if not (a.question_path == path and a.target_ref == target)]
        answers.append(repl)
    return fold(element_kind="progression_system", schema_fingerprint=FP,
                answers=answers).body


# ── the artifact ────────────────────────────────────────────────────────────


def test_the_structure_supplies_shape_and_the_policy_supplies_every_number() -> None:
    """`PGN-A5` at the point where it finally bites. S3 refuses a magnitude
    reaching the structure; here is where a number has to come from *somewhere*,
    and the only somewhere is a band a human authored or narrowed."""
    art = generate(body=_body(tier_count=2),
                   policy=_policy(**{"kind.tier[].tier_max": Band(0, 1000, 250)}))
    assert 'name = "內功"' in art.toml
    assert 'quantity = "internal_energy"' in art.toml
    # Every tier_max lies inside the band and NOWHERE else could it have come
    # from — the structure carries no number at all (S3 refuses one).
    maxima = [art.magnitudes[f"internal_energy.tier[{i}].tier_max"] for i in range(2)]
    assert all(f"tier_max = {v}" in art.toml for v in maxima)
    assert all(0 <= v <= 1001 for v in maxima), maxima


def test_the_generated_toml_carries_the_CJK_names_unescaped() -> None:
    """ML-5. A ``\\uXXXX`` ladder is a ladder a human cannot read in review, and
    review is the entire point of the artifact."""
    art = generate(body=_body(tier_count=3), policy=_policy())
    assert 'name = "練氣一層"' in art.toml
    assert 'name = "練氣三層"' in art.toml
    assert "\\u" not in art.toml


def test_every_engine_defaulted_field_is_NAMED_with_its_reason() -> None:
    """§7.2: *"you are approving 24 tiers of which 132 fields will be
    engine-defaulted"* is the number that turns an invisible hole into something a
    human can veto. A count nobody can see is not that."""
    art = generate(body=_body(tier_count=4), policy=_policy())
    assert "internal_energy.body_or_soul" in art.default_provenance
    assert art.default_provenance["internal_energy.body_or_soul"], "the reason travels too"
    assert sum(1 for k in art.default_provenance if "initial_value_on_advance" in k) == 4


# ── PGN-A9, the second direction ────────────────────────────────────────────


def test_every_position_in_the_structure_was_READ() -> None:
    art = generate(body=_body(tier_count=3), policy=_policy())
    # 6 kind cells + 3 tiers x 4 cells + the id
    assert len(art.read_set) == 6 + 12 + 1


def test_a_leaf_nobody_read_is_a_REFUSAL_with_its_pointer() -> None:
    """**The bite.** v1 offered T6's count identity as the mechanism, which cannot
    see `PGN-A9`'s own worked example: rows-in equals rows-out while a leaf
    vanishes. So the check is positional, not numeric."""
    body = _body(tier_count=2)
    body["kinds"][0]["a_position_s5_ignores"] = {
        "state": "value", "value": "x", "answer_id": "a1"}
    with pytest.raises(AdmissionRefusal) as e:
        generate(body=body, policy=_policy())
    assert "/kinds/0/a_position_s5_ignores" in str(e.value)
    assert "shaped nothing" in str(e.value)


# ── the refusals ────────────────────────────────────────────────────────────


def test_not_stated_on_a_REQUIRED_position_is_refused_by_name() -> None:
    """`PGN-A4` makes it a complete answer; this is where complete stops being
    resolvable. An engine default filling a human's silence is the silent-drop
    class with a signature on it."""
    body = _body(replace={("kind.curve", "kind:internal_energy"): ans(
        "kind.curve", "kind:internal_energy", None,
        not_stated=True, reason="absent_from_corpus")})
    with pytest.raises(AdmissionRefusal) as e:
        generate(body=body, policy=_policy())
    assert "/kinds/0/curve" in str(e.value)
    assert "absent_from_corpus" in str(e.value)


def test_a_REFUSED_cell_carries_its_owner_into_the_admission_refusal() -> None:
    """`PGN-A20` end to end: 寒潭 is a place, no place module exists, and
    generating around it would delete the requirement."""
    body = _body(replace={("kind.tier[].breakthrough", "kind:internal_energy"): ans(
        "kind.tier[].breakthrough", "kind:internal_energy",
        {"out_of_scope": "place", "requirement": "寒潭 — a sealed place"})})
    with pytest.raises(AdmissionRefusal) as e:
        generate(body=body, policy=_policy())
    assert "place element module" in str(e.value)
    assert "寒潭" in str(e.value)
    assert "delete the requirement" in str(e.value)


def test_a_magnitude_with_no_policy_band_is_refused() -> None:
    """S4's coverage check should have caught it. This is the second, independent
    place it cannot slip through — because an invented number is indistinguishable
    afterwards from one a human chose."""
    thin = _policy()
    bands = {k: v for k, v in thin.bands.items() if k != "kind.tier[].tier_max"}
    with pytest.raises(AdmissionRefusal) as e:
        generate(body=_body(), policy=Policy(
            element_kind="progression_system", schema_fingerprint=FP, tier="system",
            policy_version=1, bands=bands))
    assert "kind.tier[].tier_max" in str(e.value)
    assert "would otherwise have to invent" in str(e.value)


# ── PGN-A17: repair may ADJUST, never REMOVE / WEAKEN / SUBSTITUTE ──────────


def test_an_adjust_repair_is_admissible() -> None:
    assert_repairs_are_admissible([{"op": "adjust", "path": "/kinds/0/tiers/0/tier_max"}])


@pytest.mark.parametrize("op", sorted(k for k, ok in REPAIR_OPS.items() if not ok))
def test_a_remove_weaken_or_substitute_repair_cannot_reach_admitted(op: str) -> None:
    """**The attack needs no adversary.** The validator refuses a tier whose
    requirement resolves to nothing; repair round 2 sets it to ``None``; verdict
    *admitted*, ``repair_round: 2`` honestly recorded, every trust property green
    — and the human-approved *"advancement requires a sealed place"* is gone.
    Repair runs entirely below the signature."""
    with pytest.raises(AdmissionRefusal) as e:
        assert_repairs_are_admissible([{"op": op, "path": "/kinds/0/tiers/9/breakthrough"}])
    assert op.upper() in str(e.value)
    assert "returns to the S3 gate" in str(e.value)


def test_an_UNTYPED_repair_op_is_refused() -> None:
    """v1 constrained *how many* repairs and never *what a repair may change*. An
    unrecognised op is a repair nobody constrained."""
    with pytest.raises(AdmissionRefusal) as e:
        assert_repairs_are_admissible([{"op": "tidy_up", "path": "/kinds/0"}])
    assert "not one of" in str(e.value)


def test_generate_runs_the_repair_check_BEFORE_producing_anything() -> None:
    """Otherwise a Remove would be caught only after the artifact existed, and an
    artifact that exists is an artifact something can read."""
    with pytest.raises(AdmissionRefusal):
        generate(body=_body(), policy=_policy(), repair_ops=[{"op": "remove", "path": "/x"}])


# ── the ladder rises, and the ENGINE says so ────────────────────────────────


def test_the_ladder_RISES_across_the_band() -> None:
    """**Found by running the chain end to end, not by reading.** Every unit test
    above passed while every tier got the band's scalar default, and the engine
    refused: *"tier 1 does not raise tier_max above the tier before it. A ladder
    whose rungs do not rise is a ladder an actor can never climb."*

    ``tier[].tier_max`` is *n* numbers; a policy supplying one cannot express a
    ladder. The band is the SPAN and the rungs are interpolated across it —
    `PGN-A11`'s shape one tier down, with monotonicity holding by construction
    rather than by a check that would refuse a policy a human legitimately wrote.
    """
    art = generate(body=_body(tier_count=5),
                   policy=_policy(**{"kind.tier[].tier_max": Band(0, 1000, 500)}))
    maxima = [art.magnitudes[f"internal_energy.tier[{i}].tier_max"] for i in range(5)]
    assert maxima == sorted(set(maxima)), f"strictly rising, got {maxima}"
    assert maxima[0] >= 0


def test_the_ladder_rises_even_when_the_band_is_narrower_than_the_tier_count() -> None:
    """The degenerate case a human reaches by narrowing hard. Truncating integer
    interpolation would repeat values here, and the engine would refuse a policy
    that was legal at S4."""
    art = generate(body=_body(tier_count=8),
                   policy=_policy(**{"kind.tier[].tier_max": Band(10, 12, 11)}))
    maxima = [art.magnitudes[f"internal_energy.tier[{i}].tier_max"] for i in range(8)]
    assert maxima == sorted(set(maxima)), f"strictly rising, got {maxima}"


def test_the_generated_artifact_is_ADMITTED_by_the_engines_own_binary() -> None:
    """**The POC-1 seam.** Not a mock and not a re-implementation: the artifact is
    handed to `progression-validate`, which runs the same `resolve_and_pin` path a
    reality load runs and stamps the versions compiled into it (`PGN-A7`).

    Skips when the binary is not built — a Python-only checkout is a legitimate
    state, and a test that failed there would be deleted rather than fixed.
    """
    import json
    import pathlib
    import subprocess
    import tempfile

    root = pathlib.Path(__file__).resolve().parents[3]
    exe = root / "target" / "debug" / (
        "progression-validate.exe" if __import__("os").name == "nt" else "progression-validate")
    if not exe.is_file():
        pytest.skip(f"{exe} not built (cargo build -p ruleset-loader --bin progression-validate)")

    art = generate(body=_body(tier_count=3),
                   policy=_policy(**{"kind.tier[].tier_max": Band(0, 1000, 250)}))
    p = pathlib.Path(tempfile.gettempdir()) / "gamegen-poc1.toml"
    p.write_text(art.toml, encoding="utf-8")
    r = subprocess.run([str(exe), f"reality={p}"], capture_output=True, text=True,
                       encoding="utf-8")
    p.unlink(missing_ok=True)

    verdict = json.loads(r.stdout)
    assert verdict["verdict"] == "admitted", f"{r.stdout}\n{r.stderr}"
    assert r.returncode == 0
    assert verdict["progression_digest"], "an admitted verdict names the table it admitted"
    # The stamp is the binary's own, not something this side supplied.
    assert isinstance(verdict["engine_schema_version"], int)
    assert isinstance(verdict["engine_law_version"], int)
