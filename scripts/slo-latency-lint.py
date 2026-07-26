#!/usr/bin/env python3
"""P2·D — presence/shape gate for contracts/slo/latency.yaml.

The platform-latency SLO SoT (one p95 target per top-level user HTTP endpoint) is
only trustworthy if it can't drift into a malformed/duplicate/typo'd state. This
lint is that guard — the emit-side enforcement; the perf-nightly p95 assertion
(D-D-PERF-NIGHTLY) is the consume-side, gated on a perf harness that doesn't exist.

Checks (HARD = exit 1):
  * file parses as YAML with a top-level `endpoints:` list
  * every row has the required fields (id, service, method, path, p95_ms, window, owner)
  * p95_ms is a positive number; method is a known HTTP verb
  * `id` is unique; (method, path) is unique
  * `service` names a real services/<name>/ directory (catches a typo)
Soft (WARN only, never fails): a latency-heavy service with no row.

Exit 0 = clean; 1 = violations; 2 = misuse / missing config.
Cross-platform (pure Python + PyYAML), matching the repo's other .py gates.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[slo-latency-lint] ERROR: PyYAML not installed (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REQUIRED = ("id", "service", "method", "path", "p95_ms", "window", "owner")
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
# Services whose user surface is latency-sensitive enough that a missing SLO row is
# worth a nudge (not a failure — a service may legitimately have no sync user route).
LATENCY_HEAVY = {"chat-service", "knowledge-service", "translation-service", "composition-service"}

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    cfg = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "contracts/slo/latency.yaml"
    if not cfg.is_file():
        print(f"[slo-latency-lint] ERROR: config not found: {cfg}", file=sys.stderr)
        return 2
    try:
        doc = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        print(f"[slo-latency-lint] ERROR: malformed YAML: {e}", file=sys.stderr)
        return 2

    endpoints = doc.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        print("[slo-latency-lint] ERROR: top-level `endpoints:` must be a non-empty list", file=sys.stderr)
        return 2

    violations: list[str] = []
    seen_ids: set[str] = set()
    seen_routes: set[tuple[str, str]] = set()
    services_with_rows: set[str] = set()

    for i, row in enumerate(endpoints):
        where = f"endpoints[{i}]"
        if not isinstance(row, dict):
            violations.append(f"{where}: not a mapping")
            continue
        rid = row.get("id", where)
        for field in REQUIRED:
            if row.get(field) in (None, ""):
                violations.append(f"{rid}: missing required field `{field}`")

        p95 = row.get("p95_ms")
        if not isinstance(p95, (int, float)) or isinstance(p95, bool) or p95 <= 0:
            violations.append(f"{rid}: p95_ms must be a positive number, got {p95!r}")

        method = row.get("method")
        if method not in METHODS:
            violations.append(f"{rid}: method {method!r} not in {sorted(METHODS)}")

        if isinstance(row.get("id"), str):
            if row["id"] in seen_ids:
                violations.append(f"{rid}: duplicate id")
            seen_ids.add(row["id"])

        if method and row.get("path"):
            key = (str(method), str(row["path"]))
            if key in seen_routes:
                violations.append(f"{rid}: duplicate route {method} {row['path']}")
            seen_routes.add(key)

        svc = row.get("service")
        if isinstance(svc, str) and svc:
            if not (REPO_ROOT / "services" / svc).is_dir():
                violations.append(f"{rid}: service {svc!r} has no services/{svc}/ directory")
            services_with_rows.add(svc)

    for svc in sorted(LATENCY_HEAVY - services_with_rows):
        print(f"[slo-latency-lint] WARN: latency-heavy service {svc!r} has no SLO row", file=sys.stderr)

    if violations:
        for v in violations:
            print(f"[slo-latency-lint] FAIL: {v}", file=sys.stderr)
        print(f"[slo-latency-lint] {len(violations)} violation(s)", file=sys.stderr)
        return 1

    print(f"[slo-latency-lint] clean — {len(endpoints)} endpoint SLO(s) valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
