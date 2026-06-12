"""M1a: V3 Verifier deterministic rule-tier — gold-set + unit checks.

The gold-set is the permanent regression gate: each seeded error MUST be caught,
and a clean translation MUST stay clean (no false positives).
"""
from app.workers.v3.verifier import verify_rules


def _types(report, block=0):
    return {i.type for i in report.issues if i.block_index == block}


# ── Gold-set: seeded errors the rule-tier MUST catch ──────────────────────────

def test_gold_wrong_name():
    r = verify_rules(
        {0: "提拉米走进房间。"}, {0: "Tirana bước vào phòng."},
        {"提拉米": "Tirami"}, "vi",
    )
    assert "wrong_name" in _types(r)
    assert r.high  # high-severity → eligible for M1b targeted re-translate


def test_gold_correct_name_passes():
    r = verify_rules(
        {0: "提拉米走进房间。"}, {0: "Tirami bước vào phòng."},
        {"提拉米": "Tirami"}, "vi",
    )
    assert "wrong_name" not in _types(r)


def test_gold_source_script_leak():
    r = verify_rules({0: "魔王來了。"}, {0: "魔王 đã đến."}, {}, "vi")
    assert "untranslated" in _types(r)


def test_gold_no_leak_for_cjk_target():
    # zh -> ja: CJK in the target is expected, not a leak.
    r = verify_rules({0: "魔王來了。"}, {0: "魔王が来た。"}, {}, "ja")
    assert "untranslated" not in _types(r)


def test_gold_number_dropped():
    r = verify_rules(
        {0: "三天后，3个人离开了。"}, {0: "Sau đó, vài người rời đi."}, {}, "vi",
    )
    assert "number_mismatch" in _types(r)


def test_gold_omission():
    r = verify_rules({0: "一。二。三。四。五。"}, {0: "Một. Hai."}, {}, "vi")
    assert "omission" in _types(r)


def test_gold_repetition():
    draft = {0: "Anh ấy mỉm cười. Anh ấy mỉm cười. Anh ấy mỉm cười."}
    r = verify_rules({0: "他不停地笑。"}, draft, {}, "vi")
    assert "repetition" in _types(r)
    assert r.high


def test_gold_clean_translation_has_no_issues():
    r = verify_rules(
        {0: "提拉米对魔王说了几句话。"},
        {0: "Tirami nói vài câu với Ma Vương."},
        {"提拉米": "Tirami"}, "vi",
    )
    assert r.issues == []


# ── Scoring / report ──────────────────────────────────────────────────────────

def test_quality_score_drops_with_severity():
    r = verify_rules(
        {0: "提拉米來了。"}, {0: "Tirana 來了。"},  # wrong_name(high) + leak(high)
        {"提拉米": "Tirami"}, "vi",
    )
    assert r.high
    assert r.quality_score() < 100
    assert r.block_indices_with_high() == {0}


def test_empty_draft_block_is_skipped():
    r = verify_rules({0: "提拉米。"}, {0: "   "}, {"提拉米": "Tirami"}, "vi")
    assert r.issues == []


def test_single_char_glossary_name_no_substring_false_positive():
    """review-impl MED-1: '王' is a substring of '国王' (king) — it must NOT force
    'Vương' when the draft correctly renders the larger word. The len>=2 guard
    prevents this spurious high-severity flag (which M1b would re-translate on)."""
    r = verify_rules({0: "国王说话了。"}, {0: "Nhà vua đã nói."}, {"王": "Vương"}, "vi")
    assert "wrong_name" not in _types(r)
