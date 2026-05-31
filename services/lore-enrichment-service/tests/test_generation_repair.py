"""Normalization-repair tests (RAID C11) — malformed → repaired-or-rejected.

Acceptance: a fixture of malformed LLM outputs each repairs to a schema-valid
map OR raises a typed :class:`RepairError`. No silent data loss: a record is
never discarded while reporting success, and an un-repairable case asserts the
reject path raises (not returns None/[]).
"""

from __future__ import annotations

import pytest

from app.generation.repair import (
    RepairError,
    cjk_ratio,
    has_english_leakage,
    repair_generation,
)

KEYS = ["历史", "地理", "文化"]

# A clean, valid Chinese dimension map (the schema target).
_CLEAN = (
    '{"历史": "蓬萊自上古为仙人所居。", '
    '"地理": "地处东海之中，云雾缭绕。", '
    '"文化": "岛上修真者重道法，轻俗务。"}'
)


# ── repairable fixtures: each must repair to all expected keys ───────────────


def test_clean_json_passes_unchanged():
    out, report = repair_generation(_CLEAN, expected_keys=KEYS)
    assert set(out.keys()) == set(KEYS)
    assert not report.changed
    assert all(out[k] for k in KEYS)


def test_fenced_json_is_stripped():
    raw = f"```json\n{_CLEAN}\n```"
    out, report = repair_generation(raw, expected_keys=KEYS)
    assert set(out.keys()) == set(KEYS)
    assert report.stripped_fence


def test_bare_fence_is_stripped():
    raw = f"```\n{_CLEAN}\n```"
    out, report = repair_generation(raw, expected_keys=KEYS)
    assert set(out.keys()) == set(KEYS)
    assert report.stripped_fence


def test_surrounding_prose_is_extracted():
    raw = f"好的，这是补全结果：\n{_CLEAN}\n希望对你有帮助！"
    out, report = repair_generation(raw, expected_keys=KEYS)
    assert set(out.keys()) == set(KEYS)
    assert report.extracted_from_prose


def test_trailing_comma_is_tolerated():
    raw = (
        '{"历史": "蓬萊自上古为仙人所居。", '
        '"地理": "地处东海之中。", '
        '"文化": "重道法。",}'  # trailing comma
    )
    out, report = repair_generation(raw, expected_keys=KEYS)
    assert set(out.keys()) == set(KEYS)
    assert report.fixed_trailing_comma


def test_values_are_trimmed():
    raw = '{"历史": "  蓬萊自上古为仙人所居。  ", "地理": "东海之中。", "文化": "重道法。"}'
    out, report = repair_generation(raw, expected_keys=KEYS)
    assert out["历史"] == "蓬萊自上古为仙人所居。"
    assert "历史" in report.trimmed_keys


def test_extra_keys_dropped_but_recorded_not_silent():
    raw = (
        '{"历史": "上古仙居。", "地理": "东海。", "文化": "道法。", '
        '"乱入字段": "应被丢弃但需记录"}'
    )
    out, report = repair_generation(raw, expected_keys=KEYS)
    assert set(out.keys()) == set(KEYS)  # extra key not in output
    assert "乱入字段" in report.dropped_keys  # but RECORDED (no silent loss)


def test_numeric_scalar_in_chinese_dim_rejected():
    # DEFERRED-046: a pure-numeric scalar for a CHINESE dimension is a digit
    # hallucination (cjk_ratio 0) and must be REJECTED, not coerced-and-kept.
    # (Updated from the pre-046 test that expected {"文化":123}→"123" to pass.)
    raw = '{"历史": "上古仙居。", "地理": "东海。", "文化": 123}'
    with pytest.raises(RepairError):
        repair_generation(raw, expected_keys=KEYS)


def test_scalar_coerced_for_non_chinese_dim():
    # The scalar→string COERCION mechanism (recorded in coerced_keys) still
    # applies where the dimension is not required to be Chinese — only the
    # downstream CJK-ratio reject (046) is scoped to chinese_dimensions.
    keys = ["历史", "features"]
    raw = '{"历史": "上古仙居于东海。", "features": 123}'
    out, report = repair_generation(raw, expected_keys=keys, chinese_dimensions={"历史"})
    assert out["features"] == "123"
    assert "features" in report.coerced_keys


def test_list_value_joined_with_chinese_separator():
    raw = '{"历史": "上古仙居。", "地理": "东海。", "文化": ["道法", "丹术", "符箓"]}'
    out, report = repair_generation(raw, expected_keys=KEYS)
    assert out["文化"] == "道法、丹术、符箓"
    assert "文化" in report.coerced_keys


def test_output_preserves_expected_key_order():
    out, _ = repair_generation(_CLEAN, expected_keys=KEYS)
    assert list(out.keys()) == KEYS  # C6 declaration order preserved


# ── un-repairable fixtures: each must RAISE (reject path, no silent drop) ────


def test_no_json_object_raises():
    with pytest.raises(RepairError):
        repair_generation("我无法完成这个请求。", expected_keys=KEYS)


def test_invalid_json_after_repair_raises():
    with pytest.raises(RepairError):
        repair_generation('{"历史": "x" "地理": ', expected_keys=KEYS)


def test_missing_required_dimension_raises_no_silent_drop():
    # 文化 absent → must RAISE, not silently return a 2-key map.
    raw = '{"历史": "上古仙居。", "地理": "东海。"}'
    with pytest.raises(RepairError):
        repair_generation(raw, expected_keys=KEYS)


def test_empty_value_after_repair_raises():
    raw = '{"历史": "上古仙居。", "地理": "东海。", "文化": "   "}'
    with pytest.raises(RepairError):
        repair_generation(raw, expected_keys=KEYS)


def test_null_value_raises():
    raw = '{"历史": "上古仙居。", "地理": "东海。", "文化": null}'
    with pytest.raises(RepairError):
        repair_generation(raw, expected_keys=KEYS)


def test_nested_object_value_raises():
    raw = '{"历史": "上古仙居。", "地理": "东海。", "文化": {"x": "y"}}'
    with pytest.raises(RepairError):
        repair_generation(raw, expected_keys=KEYS)


def test_json_array_top_level_raises():
    with pytest.raises(RepairError):
        repair_generation('["历史", "地理"]', expected_keys=KEYS)


def test_empty_expected_keys_raises():
    with pytest.raises(RepairError):
        repair_generation(_CLEAN, expected_keys=[])


# ── English-leakage: a Chinese dimension answered in English is caught ───────


def test_english_leakage_in_chinese_dimension_raises():
    raw = (
        '{"历史": "Penglai is a legendary immortal isle in the eastern sea, '
        'famed since ancient times.", '
        '"地理": "东海之中。", "文化": "重道法。"}'
    )
    with pytest.raises(RepairError):
        repair_generation(raw, expected_keys=KEYS)


def test_english_leakage_can_be_scoped_to_chinese_dims_only():
    # features/inhabitants are English-LABELLED dims; if a caller marks only the
    # Chinese dims as requiring Chinese content, an English value elsewhere is ok.
    keys = ["历史", "features"]
    raw = '{"历史": "上古仙居于东海。", "features": "Jade Pool, Cloud Terrace"}'
    out, _ = repair_generation(
        raw, expected_keys=keys, chinese_dimensions={"历史"}
    )
    assert out["历史"]
    assert out["features"] == "Jade Pool, Cloud Terrace"


def test_chinese_proper_noun_value_not_flagged_as_leakage():
    # A short Chinese value is high-CJK and must NOT trip the leakage guard.
    raw = '{"历史": "玉虛宮乃昆仑之巅。", "地理": "东海。", "文化": "道法。"}'
    out, _ = repair_generation(raw, expected_keys=KEYS)
    assert out["历史"] == "玉虛宮乃昆仑之巅。"


# ── helper functions ─────────────────────────────────────────────────────────


def test_cjk_ratio_pure_chinese_is_one():
    assert cjk_ratio("玉虛宮乃昆仑之巅") == 1.0


def test_cjk_ratio_pure_english_is_zero():
    assert cjk_ratio("hello world") == 0.0


def test_cjk_ratio_empty_is_zero():
    assert cjk_ratio("   ") == 0.0


def test_has_english_leakage_flags_english_sentence():
    assert has_english_leakage("This is an English sentence about Penglai.")


def test_has_english_leakage_passes_chinese():
    assert not has_english_leakage("蓬萊乃东海仙岛。")
