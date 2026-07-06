#!/usr/bin/env python3
"""D-D-PERF-NIGHTLY — consume-side p95 assertion for contracts/slo/latency.yaml.

`slo-latency-lint.py` guards that the SLO SoT is well-formed (emit-side). THIS is
the consume-side: given a k6 run summary, it asserts the MEASURED p95 of each
endpoint against its contracted target and reds when an endpoint blows its budget.

Pairing with the driver (tests/perf/k6/http_platform_slo.js): the k6 script records
one Trend metric per SLO row, named `slo_<id>`, so the summary carries a per-endpoint
`p(95)`. This runner maps `latency.yaml` rows → those metrics.

A row the k6 run could NOT drive (missing resource id / auth) has no metric → it is
SKIPPED, not failed, UNLESS --require-all is set (a full nightly against a seeded
stack expects every row measured). This keeps the harness runnable partially at dev
time while still catching "the nightly silently measured nothing".

  slo_assert.py <k6-summary.json> [--slo contracts/slo/latency.yaml] [--require-all]
  slo_assert.py --self-test        # no stack needed: proves the assertion trips on a breach

Exit 0 = all measured endpoints within target (and, with --require-all, all measured);
1 = at least one breach (or a skipped row under --require-all); 2 = misuse / bad input.
Cross-platform (pure Python + PyYAML), matching the repo's other .py gates.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("[slo-assert] ERROR: PyYAML not installed (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
METRIC_PREFIX = "slo_"  # tests/perf/k6/http_platform_slo.js names its Trends slo_<id>

PASS, BREACH, SKIPPED = "PASS", "BREACH", "SKIPPED"


def load_slo(path: Path) -> list[dict[str, Any]]:
    """Return the SLO rows (id + p95_ms), or raise ValueError on a malformed file."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    endpoints = doc.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        raise ValueError("top-level `endpoints:` must be a non-empty list")
    rows = []
    for row in endpoints:
        if not isinstance(row, dict) or not row.get("id"):
            raise ValueError(f"malformed SLO row: {row!r}")
        rows.append(row)
    return rows


def measured_p95(summary: dict[str, Any], slo_id: str) -> float | None:
    """The measured p95 (ms) for one SLO id, or None if the run produced no metric."""
    metric = (summary.get("metrics") or {}).get(f"{METRIC_PREFIX}{slo_id}")
    if not isinstance(metric, dict):
        return None
    values = metric.get("values")
    if not isinstance(values, dict):
        return None
    # k6 Trend summary keys the 95th percentile as "p(95)".
    p95 = values.get("p(95)")
    return float(p95) if isinstance(p95, (int, float)) and not isinstance(p95, bool) else None


def evaluate(rows: list[dict[str, Any]], summary: dict[str, Any], *, require_all: bool = False):
    """Compare each SLO row's measured p95 to its target.

    Returns (results, ok). results is a list of {id, target, measured, status};
    ok is False iff any BREACH — or, under require_all, any SKIPPED row.
    """
    results = []
    ok = True
    for row in rows:
        slo_id = row["id"]
        target = row.get("p95_ms")
        got = measured_p95(summary, slo_id)
        if got is None:
            status = SKIPPED
            if require_all:
                ok = False
        elif isinstance(target, (int, float)) and not isinstance(target, bool) and got <= target:
            status = PASS
        else:
            status = BREACH
            ok = False
        results.append({"id": slo_id, "target": target, "measured": got, "status": status})
    return results, ok


def _print_report(results: list[dict[str, Any]]) -> None:
    for r in results:
        measured = f"{r['measured']:.0f}ms" if r["measured"] is not None else "—"
        target = f"{r['target']:.0f}ms" if isinstance(r["target"], (int, float)) else "?"
        line = f"[slo-assert] {r['status']:<7} {r['id']:<24} measured={measured:<8} target={target}"
        print(line, file=sys.stderr if r["status"] == BREACH else sys.stdout)


def _self_test() -> int:
    """Prove the assertion trips on a breach without needing a live stack (CI smoke)."""
    rows = [
        {"id": "fast_ep", "p95_ms": 500},
        {"id": "slow_ep", "p95_ms": 500},
        {"id": "undriven_ep", "p95_ms": 500},
    ]
    summary = {"metrics": {
        "slo_fast_ep": {"values": {"p(95)": 120.0}},
        "slo_slow_ep": {"values": {"p(95)": 999.0}},  # deliberately over budget
    }}
    results, ok = evaluate(rows, summary)
    by_id = {r["id"]: r["status"] for r in results}
    expected = {"fast_ep": PASS, "slow_ep": BREACH, "undriven_ep": SKIPPED}
    if by_id != expected or ok:
        print(f"[slo-assert] SELF-TEST FAILED: statuses={by_id} ok={ok} expected={expected}", file=sys.stderr)
        return 2
    # require_all must additionally red on the skipped row.
    _, ok_req = evaluate(rows, summary, require_all=True)
    if ok_req:
        print("[slo-assert] SELF-TEST FAILED: --require-all did not red on a SKIPPED row", file=sys.stderr)
        return 2
    print("[slo-assert] self-test OK — breach trips the gate, skip reds under --require-all")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Assert measured p95 vs contracts/slo/latency.yaml")
    ap.add_argument("summary", nargs="?", help="k6 run summary JSON")
    ap.add_argument("--slo", default=str(REPO_ROOT / "contracts/slo/latency.yaml"))
    ap.add_argument("--require-all", action="store_true",
                    help="fail if any SLO row had no measurement (full seeded nightly)")
    ap.add_argument("--self-test", action="store_true",
                    help="prove the assertion logic without a live stack, then exit")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    if not args.summary:
        print("[slo-assert] ERROR: a k6 summary JSON path is required (or --self-test)", file=sys.stderr)
        return 2

    slo_path = Path(args.slo)
    summary_path = Path(args.summary)
    if not slo_path.is_file():
        print(f"[slo-assert] ERROR: SLO file not found: {slo_path}", file=sys.stderr)
        return 2
    if not summary_path.is_file():
        print(f"[slo-assert] ERROR: k6 summary not found: {summary_path}", file=sys.stderr)
        return 2
    try:
        rows = load_slo(slo_path)
    except (ValueError, yaml.YAMLError) as e:
        print(f"[slo-assert] ERROR: bad SLO file: {e}", file=sys.stderr)
        return 2
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[slo-assert] ERROR: bad k6 summary: {e}", file=sys.stderr)
        return 2

    results, ok = evaluate(rows, summary, require_all=args.require_all)
    _print_report(results)
    n_breach = sum(1 for r in results if r["status"] == BREACH)
    n_skip = sum(1 for r in results if r["status"] == SKIPPED)
    n_pass = sum(1 for r in results if r["status"] == PASS)
    print(f"[slo-assert] {n_pass} within budget, {n_breach} breach, {n_skip} not measured")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
