"""D-D-PERF-NIGHTLY — unit tests for the p95 SLO assertion runner.

Proves the consume-side gate: a measured p95 within target PASSes, over-budget
BREACHes (reds the gate), an undriven row is SKIPPED, and --require-all reds on a
skip. This is the enforceable acceptance for "a deliberately-slow endpoint trips
the gate" — the test IS the effect-proof, not a self-report.

Run: python -m pytest scripts/perf/test_slo_assert.py -q
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "slo_assert", Path(__file__).resolve().parent / "slo_assert.py"
)
slo_assert = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(slo_assert)

ROWS = [
    {"id": "book_list_chapters", "p95_ms": 500},
    {"id": "notifications_list", "p95_ms": 400},
    {"id": "knowledge_search", "p95_ms": 1500},
]


def _summary(**p95_by_id):
    return {"metrics": {f"slo_{k}": {"values": {"p(95)": v}} for k, v in p95_by_id.items()}}


def test_within_budget_passes():
    results, ok = slo_assert.evaluate(ROWS, _summary(book_list_chapters=300, notifications_list=120))
    assert ok
    by_id = {r["id"]: r["status"] for r in results}
    assert by_id["book_list_chapters"] == slo_assert.PASS
    assert by_id["notifications_list"] == slo_assert.PASS
    # knowledge_search had no metric → skipped, not a failure (partial dev run).
    assert by_id["knowledge_search"] == slo_assert.SKIPPED


def test_over_budget_breaches_and_reds():
    results, ok = slo_assert.evaluate(ROWS, _summary(book_list_chapters=900))
    assert not ok, "an over-budget endpoint must red the gate"
    breach = next(r for r in results if r["id"] == "book_list_chapters")
    assert breach["status"] == slo_assert.BREACH
    assert breach["measured"] == 900


def test_exactly_at_target_passes():
    # p95 == target is within budget (<=), not a breach.
    _, ok = slo_assert.evaluate([{"id": "x", "p95_ms": 500}], _summary(x=500))
    assert ok


def test_skip_is_green_by_default_but_reds_under_require_all():
    summary = _summary(book_list_chapters=300)  # only 1 of 3 measured
    _, ok_default = slo_assert.evaluate(ROWS, summary)
    assert ok_default, "unmeasured rows are green by default (partial run)"
    _, ok_require = slo_assert.evaluate(ROWS, summary, require_all=True)
    assert not ok_require, "--require-all must red when a row was never measured"


def test_measured_p95_reads_k6_trend_shape():
    assert slo_assert.measured_p95(_summary(foo=42.5), "foo") == 42.5
    assert slo_assert.measured_p95({"metrics": {}}, "foo") is None
    assert slo_assert.measured_p95({"metrics": {"slo_foo": {"values": {}}}}, "foo") is None


def test_self_test_entrypoint_is_green():
    # The CI/no-stack smoke path must itself pass (exit 0).
    assert slo_assert._self_test() == 0
