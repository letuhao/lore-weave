"""A2 — the plan_forge ENGINE must not carry POC-fixture rules welded to one novel (the LLM-side of
propose.py's P-06 'fixture severing'). Guard: no book-specific literal may appear.

Scope widened 2026-07-29, because the narrow version let the exact defect it names ship. It scanned
`prompts.py` only — so `normalize.post_normalize_spec` renamed every placeholder protagonist to the
banned literal `Nữ chính` and REPLACED authored English mechanic rules with two fixed Vietnamese
sentences, on both propose paths, with this file green the whole time. A guard that covers one file
of a multi-file rule is a guard that reads as coverage while providing none.

So the sweep is now over the deterministic engine SOURCE as well: any module that can put text into
a spec is scanned for the same banned literals.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.engine.plan_forge import prompts

#: Deterministic modules that can WRITE text into a spec. A book-specific literal in any of these is
#: the same defect as one in a prompt: it reaches every book, and here it reaches them silently
#: (no model involved, nothing to refuse it).
_ENGINE_SOURCES = ["normalize.py", "propose.py", "ingest.py", "propose_llm.py", "links.py"]
_ENGINE_DIR = Path(prompts.__file__).parent

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


def _emitted_string_literals(path: Path) -> list[str]:
    """Every string this module can EMIT — docstrings and comments excluded, deliberately.

    The distinction is the whole point. Naming `Nữ chính` in a docstring that explains why the engine
    must never emit it is the fix; naming it in an assignment is the bug. Comments never enter the
    AST, so they are excluded for free.
    """
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            first = body[0] if body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    return [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings
    ]


def test_engine_modules_emit_no_poc_fixture_literals():
    """The deterministic path must not weld one novel into every book either.

    Regression: `post_normalize_spec` rewrote any placeholder protagonist to `Nữ chính` and swapped
    an English mechanic's authored rules for two hardcoded Vietnamese ones — verified live turning
    ["Partners share body heat…", "Resonance decays with distance…"] into Mị Đế's cultivation rules.
    """
    for name in _ENGINE_SOURCES:
        path = _ENGINE_DIR / name
        assert path.exists(), f"{name} moved — update _ENGINE_SOURCES or this guard rots silently"
        for lit in _emitted_string_literals(path):
            for banned in _BANNED_POC_LITERALS:
                assert banned not in lit, (
                    f"{name} can emit a literal welded to ONE novel: {banned!r} in {lit[:80]!r}"
                )


def test_the_universal_rules_are_preserved():
    # de-fixturing must NOT drop the book-agnostic contract rules
    for p in (prompts.ANALYZE_SYSTEM, prompts.MATERIALIZE_SYSTEM):
        assert "ARC COVERAGE" in p
        assert "CONTINUITY" in p
        assert "absent" in p.lower()  # the "absent ≠ invented" severing principle is stated
    assert "coupled_to_realm must always be false" in prompts.MATERIALIZE_SYSTEM
