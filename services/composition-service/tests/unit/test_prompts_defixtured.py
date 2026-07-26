"""A2 — the LLM propose prompts must NOT carry POC-fixture rules welded to one novel (the LLM-side
of propose.py's P-06 'fixture severing'). Guard: no book-specific literal may appear."""

from __future__ import annotations

from app.engine.plan_forge import prompts

# Literals that name ONE specific POC novel — telling EVERY book to reproduce them is the defect.
_BANNED_POC_LITERALS = [
    "Nữ chính",           # a specific protagonist placeholder
    "Nhập Môn", "Biến Hóa Đầu Tiên", "Thử Nghiệm", "Quyết Định Tiếp Tục",  # POC arc-2 event titles
    "Bước Lên Tiên Lộ",   # a POC arc title
    "Thực dụng", "Tự giác giới hạn", "Hài hước khô",  # POC trait list
    "PA, HA, CD, THR", "PA/HA/CD/THR",  # POC variable set forced onto every book
    "tốc độ, linh thạch",  # POC event-3 content
    "exactly 7 events", "exactly 5", "exactly these 7",
    "mì, mùi, cửa sổ",    # POC mundane-detail anchors
]


def test_analyze_prompt_has_no_poc_fixture_literals():
    for lit in _BANNED_POC_LITERALS:
        assert lit not in prompts.ANALYZE_SYSTEM, f"ANALYZE_SYSTEM still welded to the POC: {lit!r}"


def test_materialize_prompt_has_no_poc_fixture_literals():
    for lit in _BANNED_POC_LITERALS:
        assert lit not in prompts.MATERIALIZE_SYSTEM, f"MATERIALIZE_SYSTEM still welded to the POC: {lit!r}"


def test_the_universal_rules_are_preserved():
    # de-fixturing must NOT drop the book-agnostic contract rules
    for p in (prompts.ANALYZE_SYSTEM, prompts.MATERIALIZE_SYSTEM):
        assert "ARC COVERAGE" in p
        assert "CONTINUITY" in p
        assert "absent" in p.lower()  # the "absent ≠ invented" severing principle is stated
    assert "coupled_to_realm must always be false" in prompts.MATERIALIZE_SYSTEM
