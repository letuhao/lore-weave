"""Every chapter entry point must RECORD its source-injection scan, not merely run it.

The defect this exists to stop, measured live 2026-08-02
--------------------------------------------------------
A real translation of a chapter carrying `Ignore all previous instructions …` finished with

    WARNING untrusted source carries 1 directive-looking span(s) at block_translate:blocks[0..3]
    chapter_translations.source_injection_hits = NULL

The detector fired and the row said *nobody looked*. `scan_untrusted_source` was called on
several paths and the number was written on two — and the path this platform actually runs for
a structured chapter (DECOUPLED BLOCK, plus the V3 pipeline that delegates to it) was not one
of them. Every unit test was green, because each half was tested where it lived.

Why this test and not a repo gate
---------------------------------
The failure is not "a module forgot to import something" — `injection-coverage-lint` already
passed on that module, correctly, because the module DOES scan. The failure is that the scan
had no consumer on that path. So what has to be checked is the set of ENTRY POINTS, and that
set has to be derived from the dispatch rather than listed by the person adding a path.

`_entry_points()` reads `chapter_worker`'s own AST: every function imported from a worker
module and called with `chapter_translation_id=`. That is the definition of a chapter
translation entry point in this service, and it is what found the two paths this file's fix
covers — including `translate_chapter_v3`, which the author (me) had not noticed at all.

So a SIXTH path fails here on the day it is added, in two ways: the registry comparison names
it, and the reachability check refuses it until it records.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

WORKERS = pathlib.Path(__file__).resolve().parents[1] / "app" / "workers"

#: What each entry point does about the scan. `records` = calls `record_source_injection`
#: itself; `delegates` = hands the whole chapter to another entry point that does.
#:
#: Not the denominator — `_entry_points()` is. This only says what the answer should BE, and
#: the test below asserts the two agree in both directions, so a path cannot be added here
#: without existing, or exist without being here.
EXPECTED: dict[tuple[str, str], str] = {
    ("session_translator", "translate_chapter"): "records",
    ("session_translator", "translate_chapter_blocks"): "records",
    ("decoupled_translate", "start_chapter"): "records",
    ("decoupled_block_translate", "start_chapter_blocks"): "records",
    ("v3.orchestrator", "decoupled_v3_block_start"): "delegates",
    ("v3.orchestrator", "translate_chapter_v3"): "delegates",
    ("v3.orchestrator", "translate_chapter_blocks_v3"): "delegates",
}

#: Called with `chapter_translation_id=` but not a translation entry point — it publishes the
#: finished result. Listed explicitly rather than filtered by a name pattern, so a future
#: `emit_*` that DOES translate cannot slip through on the shape of its name.
NOT_AN_ENTRY_POINT = {("translation_events", "emit_translation_published")}


def _tree(module: str) -> ast.Module:
    return ast.parse((WORKERS / (module.replace(".", "/") + ".py")).read_text(encoding="utf-8"))


def _entry_points() -> dict[tuple[str, str], str]:
    """Derived, not declared: what `chapter_worker` actually dispatches a chapter to."""
    tree = _tree("chapter_worker")
    # name -> the SET of functions it can be, because one name is deliberately two of them:
    # the v2/v3 choice is made by ASSIGNMENT (`_translate_text = translate_chapter`) under an
    # `if`, while the v3 half arrives as an import alias. A one-target map keeps whichever it
    # saw last and silently drops the other — which is how the first version of this test
    # missed `translate_chapter` and `translate_chapter_blocks_v3`, two of the seven paths.
    alias: dict[str, set[tuple[str, str]]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                alias.setdefault(a.asname or a.name, set()).add(
                    (node.module.lstrip("."), a.name))
    for _ in range(3):  # settle a short chain; these are one hop in practice
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and isinstance(node.value, ast.Name)
                    and node.value.id in alias):
                alias.setdefault(node.targets[0].id, set()).update(alias[node.value.id])
    found: dict[tuple[str, str], str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not any(k.arg == "chapter_translation_id" for k in node.keywords):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
        for target in alias.get(name, ()):
            if target not in NOT_AN_ENTRY_POINT:
                found[target] = name
    return found


def _fn(module: str, name: str) -> ast.AST:
    for node in ast.walk(_tree(module)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{module}.{name} does not exist")


def _calls(node: ast.AST) -> set[str]:
    return {
        f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
        for f in (c.func for c in ast.walk(node) if isinstance(c, ast.Call))
    }


def test_the_entry_point_set_is_exactly_what_the_dispatch_calls():
    """A sixth chapter path reds here, rather than joining the silent ones."""
    derived = set(_entry_points())
    assert derived == set(EXPECTED), (
        "chapter_worker's dispatch and this file disagree.\n"
        f"  only in the dispatch: {sorted(derived - set(EXPECTED))}\n"
        f"  only in EXPECTED:     {sorted(set(EXPECTED) - derived)}\n"
        "A new chapter path must decide how it records its source-injection scan."
    )


@pytest.mark.parametrize(("module", "name"), sorted(EXPECTED))
def test_every_chapter_entry_point_records_its_scan(module, name):
    node = _fn(module, name)
    calls = _calls(node)
    if EXPECTED[(module, name)] == "records":
        assert "record_source_injection" in calls, (
            f"{module}.{name} starts a chapter translation and never records its scan. "
            "Detection is not a defence until somebody is told — this is the exact shape "
            "that left source_injection_hits NULL on the live block pipeline."
        )
        return
    # `delegates`: one hop, and the hop must land on something that records.
    targets = [ep for ep in EXPECTED if ep[1] in calls and EXPECTED[ep] == "records"]
    assert targets, (
        f"{module}.{name} is declared as delegating, but calls no entry point that records: "
        f"{sorted(calls)}"
    )


def test_scanning_without_persisting_is_not_available_to_a_chapter_path():
    """The two halves are one function, so a path cannot take one without the other.

    A bare `scan_untrusted_source` in a chapter-path module is how the block pipeline logged a
    real hit and stored nothing. It stays legal in `injection_report` (which defines it) and in
    the sub-chapter prompt builders — `extraction_prompt`, `v3/corrector`,
    `v3/bilingual_extractor` — which have no `chapter_translations` row to write to and whose
    coverage `injection-coverage-lint` tracks separately.
    """
    allowed = {"injection_report.py", "extraction_prompt.py", "corrector.py",
               "bilingual_extractor.py"}
    offenders = []
    for path in sorted(WORKERS.rglob("*.py")):
        if path.name in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == \
                    "scan_untrusted_source":
                offenders.append(f"{path.relative_to(WORKERS)}:{node.lineno}")
    assert not offenders, (
        "scan-without-persist reintroduced at: " + ", ".join(offenders) +
        "\nUse `record_source_injection(pool, chapter_translation_id, text)` — it does both."
    )
