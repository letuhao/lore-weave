"""Teeth for `scripts/db-safety-gate.py` — proof each of its checks goes red on a bad input.

Every case here is a defect this gate MISSED at some point, reproduced as a test so it
cannot come back quietly. The gate has been wrong in the most expensive direction twice:

  * it iterated an ALLOWLIST of trees (`services`, `scripts`, `infra`, `sdks`,
    `contracts`, `crates`) and `tests/` was never in it — so the gate whose entire
    subject is destructive SQL in test code could not see `tests/integration/`, where
    four harnesses apply `0002_events_table.up.sql` (`DROP TABLE IF EXISTS events`)
    against whatever `LW_INTEGRATION_DB` names. It reported PASS throughout.
  * its config check required `TEST` in the variable name AND a `loreweave_`-prefixed
    database, so `LW_INTEGRATION_META_DB: …/metaworker_meta` was invisible twice over —
    while `metaworker_live_smoke` handed exactly that DSN to `mustApply`.

Both are the same failure: a check that cannot fire is indistinguishable from a clean
tree, and it costs more than no check because it is BELIEVED.

The last test is the pair to those: the gate must stay quiet on the real repo. Without
it, "goes red" is satisfied by a gate that reddens on everything.

db-safety-gate: file-ok — the destructive SQL in this file is FIXTURE TEXT written into
tmp_path files and fed to the gate's own scanners; no statement here reaches a database,
and there is no DB connection in the module. The gate flagging it is the gate working.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent / "db-safety-gate.py"
_SPEC = importlib.util.spec_from_file_location("db_safety_gate", _PATH)
gate = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = gate
_SPEC.loader.exec_module(gate)

REPO_ROOT = Path(gate.REPO_ROOT)


# ── 1. the tree the gate could not see ───────────────────────────────────────────────

def test_tests_tree_is_scanned():
    """`tests/` must appear in the full walk.

    This is the allowlist bug stated directly. Asserting on the file ITERATOR rather
    than on a finding matters: a gate can be blind to a whole tree and still look
    healthy, because everything it does see is genuinely clean.
    """
    scanned = {
        Path(p).resolve().relative_to(REPO_ROOT).parts[0]
        for p in gate.iter_files_full()
        if Path(p).is_file()
    }
    assert "tests" in scanned, (
        "tests/ is not being scanned — the live smokes that apply "
        "DROP TABLE IF EXISTS events live there"
    )
    # Not a bare `tests` special-case: the walk must be a denylist, so the other trees
    # the old allowlist named are all still covered.
    for tree in ("services", "scripts", "contracts"):
        assert tree in scanned, f"{tree}/ dropped out of the walk"


def test_destructive_sql_in_tests_tree_is_a_finding(tmp_path):
    """A `TRUNCATE` in a tests/ harness is red. Exit 0 before the denylist change."""
    f = tmp_path / "some_live_smoke_test.go"
    f.write_text('func T(t *testing.T) {\n\tdb.Exec(`TRUNCATE events`)\n}\n', encoding="utf-8")
    findings = gate.scan_test_file(str(f))
    assert [x.kind for x in findings] == ["TRUNCATE-in-test"]


def test_pragma_with_a_reason_clears_it(tmp_path):
    """The exemption path works — otherwise the only way past the gate is --no-verify,
    and a gate people bypass is a gate that is off."""
    f = tmp_path / "some_live_smoke_test.go"
    f.write_text(
        "func T(t *testing.T) {\n"
        "\t// db-safety-gate: ok — guarded by EnsureThrowawayDB above\n"
        "\tdb.Exec(`TRUNCATE events`)\n}\n",
        encoding="utf-8",
    )
    assert gate.scan_test_file(str(f)) == []


# ── 2. the CI DSN that named a real-looking database ─────────────────────────────────

def _workflow(tmp_path, line):
    d = tmp_path / ".github" / "workflows"
    d.mkdir(parents=True)
    f = d / "ci.yml"
    f.write_text(f"jobs:\n  x:\n    env:\n      {line}\n", encoding="utf-8")
    return f


@pytest.mark.parametrize(
    "line",
    [
        # The name that actually slipped through: no TEST in the variable, no
        # `loreweave_` prefix on the database, and handed straight to `mustApply`.
        "LW_INTEGRATION_META_DB: postgres://u:p@localhost:5432/metaworker_meta?sslmode=disable",
        # The 2026-07 incident verbatim — a CI job pointed at the real books database.
        "LW_INTEGRATION_DB: postgres://u:p@localhost:5432/loreweave_book?sslmode=disable",
        "SOME_URL: postgresql://u:p@db:5432/worldservice_meta",
    ],
)
def test_ci_dsn_without_a_throwaway_marker_is_a_finding(tmp_path, line):
    f = _workflow(tmp_path, line)
    kinds = [x.kind for x in gate.scan_config_file(str(f))]
    assert kinds, f"no finding for {line}"
    assert kinds[0] in ("CI-DSN→unmarked-DB", "test-URL→production-DB")


@pytest.mark.parametrize(
    "line",
    [
        "LW_INTEGRATION_DB: postgres://u:p@localhost:5432/publisher_smoke?sslmode=disable",
        "LW_INTEGRATION_META_DB: postgres://u:p@localhost:5432/metaworker_meta_smoke?sslmode=disable",
        "BOOK_TEST_DATABASE_URL: postgres://u:p@localhost:5432/loreweave_book_test",
    ],
)
def test_marked_ci_dsn_is_clean(tmp_path, line):
    """A marked database must NOT be a finding. The check is worth nothing if the only
    way to satisfy it is to delete the line."""
    f = _workflow(tmp_path, line)
    assert gate.scan_config_file(str(f)) == []


def test_ci_dsn_check_does_not_apply_outside_workflows(tmp_path):
    """A compose file names a service's REAL database — that is what it is for. Firing
    there would train people to blanket-exempt the file, taking the workflow lines with
    it."""
    f = tmp_path / "docker-compose.yml"
    f.write_text(
        "services:\n  api:\n    environment:\n"
        "      DATABASE_URL: postgres://u:p@postgres:5432/loreweave_book\n",
        encoding="utf-8",
    )
    assert gate.scan_config_file(str(f)) == []


# ── 3. the vendored guard, five copies of it ─────────────────────────────────────────

def test_testsafe_copies_are_identical_in_this_repo():
    assert gate.check_testsafe_copies() == []


def test_testsafe_copy_divergence_is_reported(monkeypatch, tmp_path):
    """Widen ONE copy's throwaway marker — i.e. reintroduce the 2026-07 incident in a
    single service — and the gate must name that copy.

    The realistic failure is not a deleted guard, it is a guard that still exists,
    still runs, and quietly accepts one more name than its siblings.
    """
    good = "package testsafe\nvar m = `(test|smoke)`\n"
    bad = "package testsafe\nvar m = `(test|smoke|loreweave)`\n"
    for name, body in (("a", good), ("b", good), ("c", bad)):
        d = tmp_path / "services" / name / "testsafe"
        d.mkdir(parents=True)
        (d / "testsafe.go").write_text(body, encoding="utf-8")

    monkeypatch.setattr(gate, "REPO_ROOT", str(tmp_path))
    out = "\n".join(gate.check_testsafe_copies())
    assert "DIVERGED" in out
    assert "services/c/testsafe/testsafe.go" in out


def test_no_testsafe_copies_at_all_is_a_finding(monkeypatch, tmp_path):
    """Anti-vacuity. A comparison over an empty set passes trivially, so an empty scan
    must report a BROKEN CHECK rather than a clean repo — the same shape as the
    `|| true` that once let this gate's sibling invent findings from a truncated read.
    """
    monkeypatch.setattr(gate, "REPO_ROOT", str(tmp_path))
    out = "\n".join(gate.check_testsafe_copies())
    assert "found NO testsafe" in out


# ── 4. the pair to every test above: quiet on the real tree ──────────────────────────

def test_gate_is_green_on_the_real_repo():
    """If this ever fails, fix the finding — do not relax the gate."""
    assert gate.main() == 0
