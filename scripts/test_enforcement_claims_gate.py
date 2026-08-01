"""Teeth for `scripts/enforcement-claims-gate.py`.

The gate has shipped since Phase 0 with NO red-ability proof — it sat in the 47 that
`gate-teeth-gate` holds at baseline. A gate that has never been observed to fail is not a gate,
and this one in particular has already gone green for a bad reason once: it named contracts in
its own docstring, so `scripts/` counted as a live reader of every contract it discussed and it
satisfied its own check by DISCUSSING the problem.

S12 also generalised it — from the 12 machine-contract rows to every path the 125-row standards
index NAMES — so both halves need teeth.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("ecg", _ROOT / "scripts" / "enforcement-claims-gate.py")
ecg = importlib.util.module_from_spec(_SPEC)
sys.modules["ecg"] = ecg
_SPEC.loader.exec_module(ecg)

_INDEX = (_ROOT / "docs" / "standards" / "README.md").read_text(encoding="utf-8")


# ── the S12 generalisation: a named path that does not exist ──────────────────────────────

def test_the_real_index_has_no_phantom_paths():
    """The control. Without it every test below could pass because the checker is broken."""
    assert ecg.unresolved_paths(_INDEX) == []


def test_a_gate_script_the_index_names_but_that_does_not_exist_is_REPORTED():
    """THE S12 shape: a standard whose enforcement is a script that was renamed, moved, or
    never written. It reads as covered."""
    injected = _INDEX + "\n| x | enforced by `scripts/never-written-gate.py` | live |\n"
    assert ecg.unresolved_paths(injected) == ["scripts/never-written-gate.py"]


def test_a_markdown_LINK_to_a_missing_doc_is_caught_too():
    """The index names things both ways. The contract-row regex once matched only the
    backticked form and silently skipped four rows — including both LOCKED contracts — while
    reporting the smaller number as though it were the set."""
    injected = _INDEX + "\nSee [docs/standards/does-not-exist.md](../standards/does-not-exist.md).\n"
    assert "docs/standards/does-not-exist.md" in ecg.unresolved_paths(injected)


def test_PROSE_that_merely_mentions_a_directory_is_not_treated_as_a_path():
    """A gate that manufactures findings gets switched off, which is the failure mode this
    whole family is about. Only a repo-relative path with a real extension counts."""
    injected = _INDEX + "\nSee services/foo and the scripts directory for details.\n"
    assert ecg.unresolved_paths(injected) == []


def test_a_GLOB_resolves_by_matching_at_least_one_file():
    """`contracts/api/glossary-service/*.yaml` is a real and correct way to name a set. It
    cannot be stat'd, and skipping it would let a deleted directory pass."""
    assert ecg.unresolved_paths("`contracts/api/glossary-service/*.yaml`") == []
    assert ecg.unresolved_paths("`contracts/api/no-such-service/*.yaml`") == \
        ["contracts/api/no-such-service/*.yaml"]


def test_the_named_set_is_not_EMPTY_which_would_make_every_test_above_vacuous():
    """A regex that matched nothing would satisfy "no phantom paths" perfectly. The index
    names 10 gate scripts among 91 paths; asserting a floor keeps a future tightening of the
    pattern from silently emptying the input.
    MEASURED 2026-08-01: 91. The first version of the pattern found 43 — it matched only
    repo-relative link targets, and this index sits at `docs/standards/` so most of its links
    are `../../contracts/x.yaml`. It reported "43 paths, 0 missing" while never looking at a
    single doc link. This floor is what makes that regression visible.
    """
    named = ecg.declared_paths(_INDEX)
    assert len(named) >= 85, f"the index names {len(named)} paths — the pattern narrowed"
    assert sum(1 for p in named if p.startswith("scripts/")) >= 8


# ── the original half: a contract nothing reads ───────────────────────────────────────────

def test_the_gate_does_not_count_ITSELF_as_a_reader():
    """It names contracts in its own docstring as examples. `scripts/` is not a library, so
    without this exclusion it read as a live reader of every contract it discussed — the gate
    satisfying its own check by talking about the problem, which is how the S12 gate went green
    on its own motivating example three times."""
    hits = ecg.readers_of("contracts/canon/guardrail_rules.yaml",
                          [(str(_ROOT / "scripts" / "enforcement-claims-gate.py"),
                            "scripts/enforcement-claims-gate.py")])
    assert hits == []


def test_a_test_file_is_not_a_reader():
    """A contract read ONLY by its own tests is not enforced anywhere — that is the shape of a
    standard that exists in the suite and nowhere in production."""
    assert ecg.is_test_path("services/x/tests/unit/test_thing.py")
    assert ecg.is_test_path("services/x/internal/api/thing_test.go")
    assert not ecg.is_test_path("services/x/internal/api/thing.go")


def test_an_enforcement_cell_naming_PROSE_yields_no_artifact():
    """"planned perf-nightly p95 assertion" is an intention, not an artifact. Treating it as
    one would let a row claim enforcement by a file that was never meant to exist."""
    assert ecg.enforcement_artifacts("planned perf-nightly p95 assertion") == []
    assert ecg.enforcement_artifacts("gate: `scripts/ai-provider-gate.py`") == \
        ["scripts/ai-provider-gate.py"]
