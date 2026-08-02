"""Teeth for `guard-sdk-entry-gate.py` — S9.

This gate is unusual: its PASS is the steady state and its FAIL is a future event. That makes
it the easiest kind of gate to ship broken — it would print OK forever and nobody would notice,
which is precisely the "a gate that has never been observed to fail is not a gate" finding this
run's Phase 0 recorded three times.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "g9", pathlib.Path(__file__).resolve().parent / "guard-sdk-entry-gate.py"
)
g9 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(g9)


def test_today_it_passes_because_the_criterion_is_NOT_met():
    """1 of 3. Not extracting is the correct state, so the gate must be quiet about it —
    a gate that reds for a decision working as designed gets silenced."""
    assert g9.main() == 0


def test_it_FAILS_the_moment_a_third_service_adopts(monkeypatch):
    """The failure path, exercised. Without this the gate could print OK forever with a broken
    comparison and read as enforcement.

    Simulated by monkeypatching the ADOPTION SCAN, not the threshold: lowering
    `REQUIRED_ADOPTERS` would test that 1 >= 1, which is arithmetic, not the criterion.
    """
    monkeypatch.setattr(
        g9, "_adopting_modules",
        lambda svc: ["x.py"] if svc in ("composition-service", "translation-service",
                                        "knowledge-service") else [],
    )
    assert g9.main() == 1


def test_TWO_adopters_is_still_not_enough():
    """The boundary, and the reason the threshold is three: one implementation is a design,
    two is a coincidence. An off-by-one here would trigger the extraction a slice early — the
    premature abstraction this whole slice was inverted to prevent."""
    import contextlib, io

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(g9, "_adopting_modules",
                   lambda svc: ["x.py"] if svc in ("composition-service",
                                                   "translation-service") else [])
        with contextlib.redirect_stdout(io.StringIO()):
            assert g9.main() == 0


def test_the_scan_finds_the_REAL_composition_adopters():
    """The gate's input must be the repo, not a constant. If `_adopting_modules` returned []
    for everything, every assertion above would still pass — 0 < 3 and the monkeypatched cases
    never touch the filesystem."""
    mods = g9._adopting_modules("composition-service")
    assert mods, "the scan found no adopter in the service that has one"
    assert any("canon_check.py" in m for m in mods)


def test_a_test_file_is_not_an_adopter():
    """Coverage counted from tests would let a service satisfy the criterion by importing the
    contract in a test — the shape ROT-0 spent an audit on."""
    for m in g9._adopting_modules("composition-service"):
        assert "/tests/" not in m and not pathlib.Path(m).name.startswith("test_")
