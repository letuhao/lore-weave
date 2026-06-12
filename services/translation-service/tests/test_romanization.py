"""M1c: V3 romanization policy (prompt-level, zh→vi Hán-Việt)."""
from app.workers.v3.romanization import romanization_instruction


def test_zh_to_vi_returns_han_viet_instruction():
    inst = romanization_instruction("zh", "vi")
    assert inst
    assert "Hán-Việt" in inst and "pinyin" in inst


def test_zh_variants_to_vi():
    assert romanization_instruction("zh-Hans", "vi")
    assert romanization_instruction("ZH-HANT", "vi")
    # review-impl LOW-1: region/script-tagged codes must also match (primary subtag).
    assert romanization_instruction("zh-CN", "vi-VN")
    assert romanization_instruction("zh-Hant-TW", "vi")


def test_other_pairs_return_empty():
    assert romanization_instruction("en", "vi") == ""
    assert romanization_instruction("zh", "en") == ""   # pinyin is conventional for en
    assert romanization_instruction("ja", "vi") == ""
    assert romanization_instruction("", "") == ""
