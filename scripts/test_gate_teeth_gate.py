"""Teeth for `scripts/gate-teeth-gate.py` — the gate that checks gates can fail.

Every test here pins a bug the gate had on its FIRST run against the real repo, because each
one is a way the check quietly certifies something it has not verified:

  * it reported ITSELF toothless (it exits via `rc = 1 … return rc`, not a literal `return 1`)
  * it swept in 30 perf load-rigs as "toothless gates", burying the one real finding
  * it flagged `runbook-verification-lint.sh` toothless — that script's check is an embedded
    Python heredoc whose `sys.exit(1)` aborts under `set -e`, so it CAN fail
  * it certified itself as having a "built-in selftest" by matching its own string literal
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "gtg", Path(__file__).resolve().parent / "gate-teeth-gate.py"
)
gtg = importlib.util.module_from_spec(_SPEC)
sys.modules["gtg"] = gtg
_SPEC.loader.exec_module(gtg)


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


# ── the HARD rule: a gate must be able to return non-zero ─────────────────────────────────

@pytest.mark.parametrize("name,body,expected", [
    # Real shapes taken from the repo, not invented ones.
    ("a.sh", "#!/usr/bin/env bash\nset -e\necho hi\nexit 1\n", True),
    ("b.sh", '#!/usr/bin/env bash\nset -e\nexit "$violations"\n', True),
    ("c.sh", "#!/usr/bin/env bash\necho WARN advisory\nexit 0\n", False),
    ("d.py", "import sys\nsys.exit(1)\n", True),
    ("e.py", "def main():\n    rc = 1\n    return rc\n", True),
    ("f.py", "def main():\n    return 1\n", True),
    ("g.py", "def main():\n    print('report only')\n    return 0\n", False),
    ("h.py", "import sys\nsys.exit(0)\n", False),
])
def test_failure_path_detection(tmp_path, name, body, expected):
    assert gtg.has_failure_path(_write(tmp_path, name, body)) is expected


def test_shell_gate_whose_check_is_an_embedded_python_heredoc(tmp_path):
    """`runbook-verification-lint.sh`: the trailing `exit 0` is unreachable on failure because
    `set -e` aborts on the heredoc's non-zero exit. Measured: with set -e → rc=1, without → 0."""
    with_set_e = "#!/usr/bin/env bash\nset -euo pipefail\npython - <<'PY'\nimport sys\nsys.exit(1 if errors else 0)\nPY\nexit 0\n"
    assert gtg.has_failure_path(_write(tmp_path, "r.sh", with_set_e)) is True

    without = with_set_e.replace("set -euo pipefail\n", "")
    assert gtg.has_failure_path(_write(tmp_path, "r2.sh", without)) is False, \
        "without set -e the trailing `exit 0` really does swallow the failure"


# ── the gate must not be its own witness ──────────────────────────────────────────────────

def test_a_gate_cannot_certify_itself_by_mentioning_selftest_in_prose(tmp_path):
    """Only a SHAPE is a proof: a `def`, a `selftest()` function, or a CLI flag.

    This test used to assert that an `echo "SELFTEST PASS"` line counted — the
    idea being that prose claims and literals differ. **It does not hold, and
    the counter-example was live:** `dp-oracle-bite-gate.py` contains
    `"SELFTEST FAIL" in out`, a literal it uses to read the COVERAGE GATE's
    output, and on that string it was certified as carrying a self-test it did
    not have. A literal is not evidence about the file that contains it.

    Narrowing to the three shapes cost exactly one certification — that one.
    Every genuine shell self-test here defines `selftest()`, so the echo line
    they all also have was never what was carrying them.
    """
    claimed = _write(tmp_path, "claim-lint.py",
                     '"""This gate has a SELFTEST built in."""\nimport sys\nsys.exit(1)\n')
    assert gtg.teeth_proof("claim-lint.py", claimed) is None

    commented = _write(tmp_path, "claim2-lint.sh",
                       "#!/usr/bin/env bash\n# SELFTEST: flags a bad input\nexit 1\n")
    assert gtg.teeth_proof("claim2-lint.sh", commented) is None

    # The live shape, reduced: a literal used to READ SOMEONE ELSE's verdict.
    reader = _write(tmp_path, "reader-gate.py",
                    "import sys\nout = run_other_gate()\n"
                    'if "SELFTEST FAIL" in out:\n    sys.exit(2)\n')
    assert gtg.teeth_proof("reader-gate.py", reader) is None, \
        "a literal naming another gate's selftest output is not a proof about THIS file"

    real = _write(tmp_path, "real-lint.sh",
                  "#!/usr/bin/env bash\nselftest() {\n"
                  '  echo "[x] SELFTEST PASS — flags a bad input"\n}\nexit 1\n')
    assert gtg.teeth_proof("real-lint.sh", real) == "built-in selftest"

    flagged = _write(tmp_path, "flag-gate.py",
                     'import sys\nif "--self-test" in sys.argv:\n    sys.exit(0)\n')
    assert gtg.teeth_proof("flag-gate.py", flagged) == "built-in selftest"


def test_the_analyzer_does_not_certify_itself():
    """It matched its own `return "built-in selftest"` literal and reported itself proven."""
    me = Path(gtg.__file__)
    assert gtg.teeth_proof(me.name, me) == "test file scripts/test_gate_teeth_gate.py", \
        "the analyzer's proof must be THIS file, not its own vocabulary"


# ── scope: a perf load-rig is not an enforcement gate ─────────────────────────────────────

@pytest.mark.parametrize("name,is_gate", [
    ("foo-lint.sh", True), ("foo-gate.py", True), ("foo-validator.sh", True),
    ("foo-check.sh", True), ("foo-scan.py", True), ("runbook-drift-check.sh", True),
    ("w1-capacity.sh", False), ("soak.sh", False), ("k6-game-server.sh", False),
    ("scale-rig.sh", False),
])
def test_only_enforcement_scripts_count_as_gates(name, is_gate):
    assert bool(gtg._IS_GATE.search(name)) is is_gate


# ── the live repo state this gate is asserting ────────────────────────────────────────────

def test_every_ci_invoked_gate_in_this_repo_can_fail():
    """The HARD rule, against the real tree — no gate wired into CI is advisory-only."""
    toothless = [
        rel for rel in gtg.ci_invoked_scripts()
        if (gtg.ROOT / "scripts" / rel).exists()
        and Path(rel).name not in gtg.NOT_A_GATE
        and not gtg.has_failure_path(gtg.ROOT / "scripts" / rel)
    ]
    assert toothless == [], f"wired into CI but cannot report a violation: {toothless}"
