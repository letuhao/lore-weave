"""T69 — every vector reader in this package must request the index fixture.

T25 ③ deleted the passage vector DDL, so `passage_embeddings_<dim>` is created by whoever
needs it. T25n gave the two benchmarks `ensure_passage_vector_index`. T65 gave four tests in
`test_passages_repo.py` a `passage_vector_index` fixture. **Both times the list was written by
hand, and both times it was short one reader** — `test_eval_fixture_loader.py` calls
`find_passages_by_vector` and asked for nothing, so it passed only when `test_passages_repo`
happened to run first under `pytest-randomly` and left the index behind. It failed roughly
every other full run, which reads exactly like flake.

Enumerating readers is what failed twice. This derives the list instead.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
#: Reads that go through `db.index.vector.queryNodes` and therefore need the index to exist.
_VECTOR_READS = {"find_passages_by_vector"}
#: This file NAMES the readers in prose; it must not be scored as one.
_EXEMPT = {__file__.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]}


def _tests_calling_a_vector_read(path: pathlib.Path) -> dict[str, set[str]]:
    """{test function name: fixture names it requests} for tests that call a vector read."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        calls = {
            c.func.id for c in ast.walk(node)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        }
        if not calls & _VECTOR_READS:
            continue
        args = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
        out[node.name] = args
    return out


def test_every_vector_reading_test_requests_the_index_fixture():
    """Derived, not enumerated — that is the whole point of this file.

    A test that queries a vector index without ensuring one does not fail honestly: it fails
    only when it happens to run before whichever other test creates the index, so it reads as
    flake and gets re-run rather than fixed.
    """
    missing: list[str] = []
    for path in sorted(_HERE.glob("test_*.py")):
        if path.name in _EXEMPT:
            continue
        for name, fixtures in _tests_calling_a_vector_read(path).items():
            if "passage_vector_index" not in fixtures:
                missing.append(f"{path.name}::{name}")
    assert not missing, (
        "these tests query a passage vector index without requesting "
        "`passage_vector_index`, so they pass only when another test created it first:\n  "
        + "\n  ".join(missing)
    )


def test_the_scanner_itself_can_SEE_a_reader():
    """Non-vacuity. If `_tests_calling_a_vector_read` found nothing anywhere, the check above
    would pass on an empty set forever — green because it is blind, which is the failure this
    whole file exists to stop one level down."""
    found = {
        f"{p.name}::{n}"
        for p in _HERE.glob("test_*.py") if p.name not in _EXEMPT
        for n in _tests_calling_a_vector_read(p)
    }
    assert found, (
        "the scanner found NO test calling a vector read anywhere in this package — either "
        "every reader was removed (then delete this file) or the detector is broken"
    )


@pytest.mark.parametrize("src,expected", [
    ("async def test_a(neo4j_driver):\n    find_passages_by_vector(s)\n", {"test_a"}),
    ("async def test_b(neo4j_driver):\n    other_call(s)\n", set()),
    ("def helper():\n    find_passages_by_vector(s)\n", set()),
])
def test_the_scanner_matches_tests_and_only_tests(tmp_path, src, expected):
    """Validated on cases it was not derived from: a non-test function that calls the same
    read must NOT be scored, or a helper would make every file look guilty."""
    f = tmp_path / "test_probe.py"
    f.write_text(src, encoding="utf-8")
    assert set(_tests_calling_a_vector_read(f)) == expected
