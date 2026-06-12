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


# ── D-V3-TRANSLATION-PROMPT-ECHO: verbatim source echo ────────────────────────

def test_echo_verbatim_copy_flagged_high():
    """The model copied the source under [BLOCK N] instead of translating → HIGH
    untranslated so the corrector re-translates it."""
    src = "魔王終於來到了城堡。"
    r = verify_rules({0: src}, {0: src}, {}, "vi")
    assert "untranslated" in _types(r) and r.high


def test_echo_caught_for_cjk_target_where_script_leak_cannot_fire():
    """zh→ja: a verbatim echo can't be caught by the rule-2 CJK script-leak (target IS
    CJK) — the echo check catches it."""
    src = "魔王終於來到了城堡裡面。"
    r = verify_rules({0: src}, {0: src}, {}, "ja")
    assert "untranslated" in _types(r)


def test_echo_ignores_short_block():
    """A short verbatim block (< _ECHO_MIN_CHARS) is not flagged — too noisy. (ja target
    so the rule-2 CJK script-leak doesn't also fire and mask the echo guard.)"""
    r = verify_rules({0: "魔王。"}, {0: "魔王。"}, {}, "ja")
    assert "untranslated" not in _types(r)


def test_echo_ignores_pure_number_symbol_passthrough():
    """A number/symbol block legitimately passes through unchanged — never an echo flag."""
    r = verify_rules({0: "12:34:56 — 2024"}, {0: "12:34:56 — 2024"}, {}, "vi")
    assert "untranslated" not in _types(r)


def test_echo_not_flagged_for_real_translation():
    r = verify_rules(
        {0: "魔王終於來到了城堡。"}, {0: "Ma vương cuối cùng đã đến lâu đài."}, {}, "vi",
    )
    assert "untranslated" not in _types(r)


def test_echo_normalizes_whitespace():
    """A copy that differs only in whitespace is still an echo."""
    r = verify_rules({0: "魔王 終於 來到了城堡。"}, {0: "魔王   終於 來到了城堡。"}, {}, "vi")
    assert "untranslated" in _types(r)


def test_block_prompt_forbids_echo():
    """The block translator prompt carries the explicit anti-echo rule (prompt-format
    half of D-V3-TRANSLATION-PROMPT-ECHO)."""
    from app.workers.session_translator import _BLOCK_SYSTEM_PROMPT
    assert "NEVER copy the source" in _BLOCK_SYSTEM_PROMPT
