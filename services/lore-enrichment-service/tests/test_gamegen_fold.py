"""S3 — the fold, and every way it refuses.

No DB, no port, no network — deliberately no ``xdist_group`` mark. The fold is a
pure function on purpose (`PGN-A10`); a fold that needed a database to be tested
would be a fold that could vary with one.

The load-bearing tests here are the refusals. A fold that produces a plausible
structure is easy; the properties doc 39 claims are all about what it *declines*
to produce.
"""

from __future__ import annotations

import pytest

from app.gamegen.fold import (
    ORDINAL_LEAVES,
    OUT_OF_SCOPE_OWNERS,
    ApprovedAnswer,
    FoldRefusal,
    assert_no_magnitude_leaked,
    fold,
)

# The three kinds §10's fixture declares.
KINDS = ["internal_energy", "swordsmanship", "comprehension"]
FP = "787c69388addda04170236c72ba1dfd8ee3c69d46d705c3739ec50967a8b225b"


def ans(path, target, value, *, aid=None, not_stated=False, reason=None) -> ApprovedAnswer:
    return ApprovedAnswer(
        answer_id=aid or f"a:{target}:{path}",
        answer_hash=f"h:{target}:{path}",
        question_id=path.replace(".", "_"),
        question_path=path,
        target_ref=target,
        value=value,
        not_stated=not_stated,
        not_stated_reason=reason,
    )


def full_set(*, kinds=None, tier_count=9, tier_names="{n}層", **override) -> list[ApprovedAnswer]:
    """A complete, approvable answer set. ``override`` replaces one
    ``(path, target)`` so a test can break exactly one thing."""
    kinds = kinds or ["internal_energy"]
    out = [ans("kind.quantity", "element:progression_system", kinds)]
    for k in kinds:
        t = f"kind:{k}"
        out += [
            ans("kind.name", t, "內功"),
            ans("kind.progression_type", t, "stage"),
            ans("kind.curve", t, "stage"),
            ans("kind.cap_rule", t, "tier_based"),
            ans("kind.initial_tier", t, 0),
            ans("kind.tier_count", t, tier_count),
            ans("kind.tier[].tier_index", t, "ascending"),
            ans("kind.tier[].name", t, tier_names),
            ans("kind.tier[].within_tier_curve", t, "linear"),
            ans("kind.tier[].breakthrough", t, "at_max"),
        ]
    for (path, target), replacement in override.pop("swap", {}).items():
        out = [a for a in out if not (a.question_path == path and a.target_ref == target)]
        if replacement is not None:
            out.append(replacement)
    return out


def run(**kw):
    return fold(element_kind="progression_system", schema_fingerprint=FP, answers=full_set(**kw))


# ── the happy path, and what makes it dense ─────────────────────────────────


def test_the_fold_is_dense_not_sparse() -> None:
    """§5's headline. v1's ``{tier_count: 24}`` made S5 synthesise **132 required
    values** from one integer, of which exactly one had a policy path."""
    s = run(tier_count=9)
    tiers = s.body["kinds"][0]["tiers"]
    assert len(tiers) == 9
    assert all(set(t) == {"tier_index", "name", "within_tier_curve", "breakthrough"} for t in tiers)


def test_every_leaf_carries_the_answer_that_produced_it() -> None:
    """*"Where did this come from"* always has an answer, at every leaf, not just
    at the top of the artifact."""
    s = run()
    for tier in s.body["kinds"][0]["tiers"]:
        for leaf, cell in tier.items():
            assert cell["answer_id"], f"{leaf} has no answer_id"


def test_a_naming_PATTERN_expands_to_dense_rows(*_) -> None:
    """`PGN-A11` — the human approves the pattern, the code does the expansion.
    Nine leaves, ONE decision."""
    s = run(tier_count=9, tier_names="{n}層")
    names = [t["name"]["value"] for t in s.body["kinds"][0]["tiers"]]
    assert names == ["1層", "2層", "3層", "4層", "5層", "6層", "7層", "8層", "9層"]
    aids = {t["name"]["answer_id"] for t in s.body["kinds"][0]["tiers"]}
    assert len(aids) == 1, "nine names, one approved answer"


def test_the_fixtures_OWN_convention_is_expressible_as_a_pattern() -> None:
    """**The multilingual bite, and the reason `NUMERALS` exists.**

    Doc 39 §1 says the sub-levels are named *一層…九層 by convention* — one
    pattern, one decision (`PGN-A11`). The first implementation expanded ``{n}``
    with ``str(index + 1)`` and produced ``1層, 2層, 3層``: **ASCII digits for a
    Chinese corpus.** An author wanting the real names would have had to fall back
    to an explicit 9-item list — nine decisions — which defeats `PGN-A11` exactly
    where the fixture needs it. ML-4, in the one module whose corpus is Chinese.
    """
    s = run(tier_count=9, tier_names="{n:cn}層")
    names = [t["name"]["value"] for t in s.body["kinds"][0]["tiers"]]
    assert names == ["一層", "二層", "三層", "四層", "五層", "六層", "七層", "八層", "九層"]
    assert len({t["name"]["answer_id"] for t in s.body["kinds"][0]["tiers"]}) == 1


def test_chinese_numerals_are_correct_past_ten() -> None:
    """十, 十一, 二十, 二十一 — not 一十 and not 二十〇. Tiers cap at 64, so 1–99
    is the whole reachable range and a 百 arm would be untested code."""
    s = run(tier_count=25, tier_names="{n:cn}")
    names = [t["name"]["value"] for t in s.body["kinds"][0]["tiers"]]
    assert names[9] == "十" and names[10] == "十一" and names[19] == "二十"
    assert names[20] == "二十一" and names[24] == "二十五"


def test_an_unknown_numeral_system_is_refused_by_name() -> None:
    """Left as a literal, ``九{n:jp}`` would ship the placeholder to a player —
    the silent degradation ML-4 forbids."""
    with pytest.raises(FoldRefusal) as e:
        run(tier_names="{n:jp}層")
    assert "numeral system this module does not have" in str(e.value)
    assert "'cn'" in str(e.value)


def test_an_explicit_name_list_is_also_accepted() -> None:
    names = ["一層", "二層", "三層"]
    s = run(tier_count=3, tier_names=names)
    assert [t["name"]["value"] for t in s.body["kinds"][0]["tiers"]] == names


def test_the_fold_is_deterministic() -> None:
    """T4 below the human signature. Same answers, same bytes."""
    assert run().content_hash == run().content_hash


def test_changing_one_answer_moves_the_content_hash() -> None:
    assert run(tier_count=9).content_hash != run(tier_count=8).content_hash


def test_three_kinds_fold_independently() -> None:
    s = fold(element_kind="progression_system", schema_fingerprint=FP, answers=full_set(kinds=KINDS))
    assert [k["id"] for k in s.body["kinds"]] == KINDS


# ── PGN-A9, both directions ─────────────────────────────────────────────────


def test_every_approved_answer_maps_to_at_least_one_pointer() -> None:
    """The forward half of the ledger."""
    answers = full_set(tier_count=9)
    s = fold(element_kind="progression_system", schema_fingerprint=FP, answers=answers)
    assert set(s.consumption) == {a.answer_id for a in answers}
    assert all(len(v) >= 1 for v in s.consumption.values())


def test_the_tier_answers_map_to_one_pointer_PER_TIER() -> None:
    """The expansion is visible in the ledger, which is what makes *"one decision,
    nine leaves"* auditable rather than merely true."""
    s = run(tier_count=9)
    assert len(s.consumption["a:kind:internal_energy:kind.tier[].name"]) == 9


def test_an_unconsumed_approved_answer_is_a_REFUSAL() -> None:
    """**The bite `PGN-A9` asks for.** A count identity cannot see this: rows-in
    equals rows-out while a leaf vanishes."""
    answers = full_set() + [ans("kind.name", "kind:a_kind_nobody_declared", "幻功")]
    with pytest.raises(FoldRefusal) as e:
        fold(element_kind="progression_system", schema_fingerprint=FP, answers=answers)
    assert "reached no position" in str(e.value)
    assert "a_kind_nobody_declared" in str(e.value)


def test_the_answer_refs_are_hash_linked_not_id_linked() -> None:
    """v1 referenced answers by bare id, so an UPDATE after pinning could
    retroactively convert an invented tier into an extracted one with every hop
    of the chain still green."""
    s = run()
    assert all(isinstance(h, str) and h for _, h in s.answer_refs)
    assert dict(s.answer_refs)["a:kind:internal_energy:kind.name"] == (
        "h:kind:internal_energy:kind.name"
    )


# ── PGN-A5 / T2: no magnitude reaches the structure ─────────────────────────


def test_a_planted_magnitude_is_refused_by_pointer() -> None:
    """§6's bite-test, moved to the stage that can actually stop it: plant
    ``tier_max: 500`` in a structure and watch the fold refuse. A number here is a
    balance decision reviewed as prose, and after S5 it is indistinguishable from
    one the policy produced."""
    s = run()
    s.body["kinds"][0]["tiers"][3]["tier_max"] = {"state": "value", "value": 500, "answer_id": "x"}
    with pytest.raises(FoldRefusal) as e:
        assert_no_magnitude_leaked(s.body)
    assert "/kinds/0/tiers/3/tier_max" in str(e.value)
    assert "500" in str(e.value)


def test_the_ordinal_class_is_allowed_through() -> None:
    """Otherwise the check is a ban on numbers, and a ladder has no ordinals."""
    s = run()
    assert_no_magnitude_leaked(s.body)
    assert s.body["kinds"][0]["tiers"][4]["tier_index"]["value"] == 4
    assert s.body["kinds"][0]["tier_count"]["value"] == 9


def test_a_magnitude_hidden_inside_a_nested_value_is_still_found() -> None:
    """The walk descends into cell values. A guard that only checked top-level
    leaves would be defeated by one level of nesting."""
    s = run()
    s.body["kinds"][0]["cap_rule"]["value"] = {"soft_cap": 1200}
    with pytest.raises(FoldRefusal) as e:
        assert_no_magnitude_leaked(s.body)
    assert "soft_cap" in str(e.value)


def test_a_magnitude_cannot_hide_behind_an_ORDINAL_KEY_NAME() -> None:
    """**Found by probe, and it is the sharper version of the guard's job.**

    The first walk carried ``leaf`` down through nested values, so a cap-rule
    answered as ``{"soft_cap": null, "tier_count": 500}`` re-bound ``leaf`` to
    ``"tier_count"`` and **500 sailed through**: a magnitude smuggled in by naming
    its key after an ordinal. An allow-list keyed on a name the *input* controls is
    not an allow-list. Only a number sitting directly at a cell's own ``value``
    slot may be ordinal now.
    """
    with pytest.raises(FoldRefusal) as e:
        run(swap={("kind.cap_rule", "kind:internal_energy"): ans(
            "kind.cap_rule", "kind:internal_energy", {"soft_cap": None, "tier_count": 500})})
    assert "500" in str(e.value)
    assert "/kinds/0/cap_rule/value/tier_count" in str(e.value)


def test_an_ordinal_leaf_still_passes_after_that_fix() -> None:
    """The narrowing must not break the legitimate case, or the whole guard gets
    widened back the first time a real ladder trips it."""
    s = run(tier_count=5)
    assert_no_magnitude_leaked(s.body)
    assert s.body["kinds"][0]["tiers"][2]["tier_index"]["value"] == 2


def test_the_schema_fingerprint_is_part_of_the_content_ADDRESS() -> None:
    """**The probe's other finding.** With the fingerprint outside the hash,
    re-folding the same answers after the schema MOVED produced the same
    ``content_hash``; the store's ``ON CONFLICT`` returned the OLD row and the new
    fingerprint was silently discarded, so the stored structure claimed a schema
    nobody asserted — the exact drift the column exists to make loud."""
    a = fold(element_kind="progression_system", schema_fingerprint="a" * 64,
             answers=full_set())
    b = fold(element_kind="progression_system", schema_fingerprint="b" * 64,
             answers=full_set())
    assert a.body == b.body, "same answers, same structure"
    assert a.content_hash != b.content_hash, "and yet a different address"


def test_a_boolean_is_not_a_magnitude() -> None:
    """``isinstance(True, int)`` is True in Python. Without the explicit bool arm
    every flag in the structure would read as a leaked magnitude, the check would
    be unusable, and the natural fix would be to widen the allow-list until it
    stopped firing."""
    s = run()
    s.body["kinds"][0]["curve"]["value"] = True
    assert_no_magnitude_leaked(s.body)


# ── PGN-A20: out of scope is a REFUSAL that names its owner ─────────────────


def test_an_out_of_scope_requirement_is_recorded_with_its_owner() -> None:
    """**The fixture's headline sentence.** 陳玄一在寒潭閉關三年 — 閉關三年 generates a
    ``TrainingSource::Time``; 寒潭 is a *place*, and no place module exists. The
    honest artifact says so and names who owns it; a pipeline that silently
    generated a place-less training rule would be the `QTY-Q5` class shipping in
    the POC that exists to prove it cannot."""
    answers = full_set(
        swap={
            ("kind.tier[].breakthrough", "kind:internal_energy"): ans(
                "kind.tier[].breakthrough",
                "kind:internal_energy",
                {"out_of_scope": "place", "requirement": "寒潭 — advancement requires a sealed place"},
            )
        }
    )
    s = fold(element_kind="progression_system", schema_fingerprint=FP, answers=answers)
    cell = s.body["kinds"][0]["tiers"][0]["breakthrough"]
    assert cell["state"] == "refused"
    assert "place element module" in cell["owner"]
    assert "寒潭" in cell["requirement"]
    # and it is CONSUMED, not dropped — the requirement stays visible
    assert len(s.consumption["a:kind:internal_energy:kind.tier[].breakthrough"]) == 9


def test_an_out_of_scope_marker_with_no_known_owner_is_refused() -> None:
    """A refusal that does not name an owner decays into *"the pipeline does not
    support that"* within one session."""
    answers = full_set(
        swap={
            ("kind.cap_rule", "kind:internal_energy"): ans(
                "kind.cap_rule", "kind:internal_energy", {"out_of_scope": "weather"}
            )
        }
    )
    with pytest.raises(FoldRefusal) as e:
        fold(element_kind="progression_system", schema_fingerprint=FP, answers=answers)
    assert "names no owning module" in str(e.value)
    assert sorted(OUT_OF_SCOPE_OWNERS)[0] in str(e.value)


# ── PGN-A4: not_stated survives into the structure as itself ────────────────


def test_a_not_stated_answer_becomes_a_sentinel_not_a_default() -> None:
    """The whole reason a cell is not a bare value. Flattening this to a default
    would be the silent drop with the author's intent in it."""
    answers = full_set(
        swap={
            ("kind.tier[].within_tier_curve", "kind:internal_energy"): ans(
                "kind.tier[].within_tier_curve", "kind:internal_energy", None,
                not_stated=True, reason="absent_from_corpus",
            )
        }
    )
    s = fold(element_kind="progression_system", schema_fingerprint=FP, answers=answers)
    cell = s.body["kinds"][0]["tiers"][0]["within_tier_curve"]
    assert cell == {
        "state": "not_stated",
        "answer_id": "a:kind:internal_energy:kind.tier[].within_tier_curve",
        "reason": "absent_from_corpus",
    }


def test_not_stated_on_the_CARDINALITY_is_refused() -> None:
    """`PGN-A4` makes not_stated complete; this is the field where complete is
    still not resolvable. Defaulting to one ladder would author the book's
    premise."""
    answers = full_set(
        swap={
            ("kind.quantity", "element:progression_system"): ans(
                "kind.quantity", "element:progression_system", None,
                not_stated=True, reason="absent_from_corpus",
            )
        }
    )
    with pytest.raises(FoldRefusal) as e:
        fold(element_kind="progression_system", schema_fingerprint=FP, answers=answers)
    assert "author the book's premise" in str(e.value)


def test_not_stated_on_TIER_COUNT_is_refused() -> None:
    """A ladder whose height is unknown cannot be made dense, and emitting zero
    tiers would look like a deliberate flat progression."""
    answers = full_set(
        swap={
            ("kind.tier_count", "kind:internal_energy"): ans(
                "kind.tier_count", "kind:internal_energy", None,
                not_stated=True, reason="absent_from_corpus",
            )
        }
    )
    with pytest.raises(FoldRefusal) as e:
        fold(element_kind="progression_system", schema_fingerprint=FP, answers=answers)
    assert "cannot be made dense" in str(e.value)


# ── the rest of the refusals ────────────────────────────────────────────────


def test_a_missing_answer_is_refused_and_names_the_position() -> None:
    answers = full_set(swap={("kind.curve", "kind:internal_energy"): None})
    with pytest.raises(FoldRefusal) as e:
        fold(element_kind="progression_system", schema_fingerprint=FP, answers=answers)
    assert "kind.curve" in str(e.value)
    assert "default nobody chose" in str(e.value)


def test_a_missing_cardinality_answer_is_refused() -> None:
    answers = [a for a in full_set() if a.question_path != "kind.quantity"]
    with pytest.raises(FoldRefusal) as e:
        fold(element_kind="progression_system", schema_fingerprint=FP, answers=answers)
    assert "structurally valid element containing nothing" in str(e.value)


def test_two_answers_for_one_position_are_refused_rather_than_picked_between() -> None:
    answers = full_set() + [ans("kind.curve", "kind:internal_energy", "linear", aid="second")]
    with pytest.raises(FoldRefusal) as e:
        fold(element_kind="progression_system", schema_fingerprint=FP, answers=answers)
    assert "refuses rather than picking one" in str(e.value)


def test_a_name_list_of_the_wrong_length_is_refused() -> None:
    """Truncating or padding both hide which of the two answers the human got
    wrong."""
    with pytest.raises(FoldRefusal) as e:
        run(tier_count=9, tier_names=["一層", "二層"])
    assert "2 tier names for 9 tiers" in str(e.value)


def test_a_constant_tier_name_pattern_is_refused() -> None:
    """Every tier gets the same name: reads as a ladder, is not one."""
    with pytest.raises(FoldRefusal) as e:
        run(tier_names="內功")
    assert "no {n} placeholder" in str(e.value)


def test_a_tier_count_above_the_engine_maximum_is_refused_here() -> None:
    """Refused next to the answer that produced it, not three stages later."""
    with pytest.raises(FoldRefusal) as e:
        run(tier_count=65)
    assert "MAX_TIERS_PER_KIND" in str(e.value)


def test_a_repeated_kind_in_the_cardinality_answer_is_refused() -> None:
    """Built by hand rather than through ``full_set``: that helper would emit two
    answer sets for the repeated kind and the duplicate-answer refusal would fire
    first, so the test would pass while proving something else."""
    answers = full_set(kinds=["internal_energy"])
    answers = [a for a in answers if a.question_path != "kind.quantity"]
    answers.append(
        ans("kind.quantity", "element:progression_system",
            ["internal_energy", "internal_energy"])
    )
    with pytest.raises(FoldRefusal) as e:
        fold(element_kind="progression_system", schema_fingerprint=FP, answers=answers)
    assert "repeats a kind" in str(e.value)


# ── T3: the batch ceiling ───────────────────────────────────────────────────


def test_a_batch_above_the_declared_ceiling_is_refused() -> None:
    """T3's remaining arm. A batch big enough that nobody read it is how *"nothing
    reaches players unreviewed"* fails while every signature is present."""
    with pytest.raises(FoldRefusal) as e:
        fold(
            element_kind="progression_system", schema_fingerprint=FP, answers=full_set(),
            max_batch_size=10, batch_sizes=[3, 40],
        )
    assert "ceiling is 10" in str(e.value)


def test_no_ceiling_is_the_default_and_is_honest_about_it() -> None:
    """A ceiling nobody chose is a number that looks like a policy."""
    fold(element_kind="progression_system", schema_fingerprint=FP, answers=full_set(), batch_sizes=[10_000])


# ── the pointer encoding ────────────────────────────────────────────────────


def test_the_pointer_encoder_escapes_rfc6901_specials() -> None:
    """Tested DIRECTLY, and here is the honest reason.

    My first version of this test folded a kind id containing a ``/`` and asserted
    the escape appeared in the ledger. It never does — kinds are an **array**, so
    a kind reaches a pointer as its index and never as its id. The escaping is
    therefore correct and currently **unreachable through** :func:`fold`: an
    `NV-3` subject-never-reached, and asserting on it through the fold would have
    been a green test proving nothing.

    So the function is tested for what it does, and the fold is tested (below) for
    the property that actually holds today: pointers are index-based, so an
    author-supplied id cannot shape one at all.
    """
    from app.gamegen.fold import _pointer

    assert _pointer("kinds", 0, "name") == "/kinds/0/name"
    assert _pointer("a/b") == "/a~1b"
    assert _pointer("a~b") == "/a~0b"
    assert _pointer("~/") == "/~0~1"


def test_an_author_supplied_id_never_shapes_a_pointer() -> None:
    """Why the escaping has no live subject, asserted rather than assumed — if a
    future schema keyed kinds by id instead of index, this reds and the escaping
    stops being decorative."""
    s = run(kinds=["wu/xia"])
    assert s.body["kinds"][0]["id"] == "wu/xia"
    assert s.consumption["a:kind:wu/xia:kind.name"] == ["/kinds/0/name"]
    assert not any("wu" in p for ps in s.consumption.values() for p in ps)
