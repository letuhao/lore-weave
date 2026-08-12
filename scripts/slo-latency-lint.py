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


def check(cfg: Path, repo_root: Path = REPO_ROOT) -> int:
    """`repo_root` is a parameter so `--self-test` can drive the REAL checker
    over a synthetic tree instead of re-implementing its rules — the defect that
    let twelve production rules be deleted with a sibling gate's suite green."""
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
            if not (repo_root / "services" / svc).is_dir():
                violations.append(f"{rid}: service {svc!r} has no services/{svc}/ directory")
            services_with_rows.add(svc)

    for svc in sorted(LATENCY_HEAVY - services_with_rows):
        print(f"[slo-latency-lint] WARN: latency-heavy service {svc!r} has no SLO row", file=sys.stderr)

    # SHRINK ARM (`GT-F5`). `LATENCY_HEAVY` is a hand-kept list, and a name in it
    # that is not a real service exempts nothing while looking like coverage —
    # the nudge silently stops applying to a service that was renamed. Three
    # other lists in this repo needed this arm; it is cheaper to add than to
    # rediscover. Measured 2026-08-12: all four names are real, 0 dead rows.
    for svc in sorted(LATENCY_HEAVY):
        if not (repo_root / "services" / svc).is_dir():
            violations.append(
                f"LATENCY_HEAVY names {svc!r}, which has no services/{svc}/ directory — "
                "the nudge applies to nothing; delete the row or fix the name")

    if violations:
        for v in violations:
            print(f"[slo-latency-lint] FAIL: {v}", file=sys.stderr)
        print(f"[slo-latency-lint] {len(violations)} violation(s)", file=sys.stderr)
        return 1

    print(f"[slo-latency-lint] clean — {len(endpoints)} endpoint SLO(s) valid "
          f"({len(seen_ids)} unique id(s), {len(services_with_rows)} service(s) covered)")
    return 0


VALID_ROW = ("  - id: r1\n    service: {svc}\n    method: GET\n    path: /v1/x\n"
             "    p95_ms: 250\n    window: 30d\n    owner: team\n")


def self_test() -> int:
    """Every rule against input that violates it AND input that must not trip it.

    It drives the REAL `check()` over synthetic configs and a synthetic services
    tree. A case that re-implemented the loop would be testing a copy.
    """
    import tempfile

    failures = 0

    import contextlib
    import io

    # The DEFAULT tree contains every `LATENCY_HEAVY` name, so the shrink arm
    # stays quiet and each probe below tests exactly ONE rule. Omitting them was
    # my first version, and it made the shrink arm fire in every probe — an arm
    # reding for the right reason in the wrong case, which certifies nothing.
    DEFAULT_DIRS = ("svc-a", *sorted(LATENCY_HEAVY))

    def probe(name: str, body: str | None, want: int, svc_dirs=DEFAULT_DIRS) -> None:
        nonlocal failures
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for s in svc_dirs:
                (root / "services" / s).mkdir(parents=True, exist_ok=True)
            cfg = root / "latency.yaml"
            if body is not None:
                cfg.write_text(body, encoding="utf-8")
            try:
                # The checker's own diagnostics are the SUBJECT here, not output
                # anyone needs to read; 13 probes x 4 nudge lines drowns the
                # verdicts that matter.
                with contextlib.redirect_stderr(io.StringIO()), \
                        contextlib.redirect_stdout(io.StringIO()):
                    got = check(cfg, repo_root=root)
            except Exception as e:  # noqa: BLE001 - a crash is what this asserts against
                failures += 1
                print(f"  FAIL {name}: raised {type(e).__name__}: {e} — it must return a code")
                return
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok ' if ok else 'FAIL'} {name}: rc={got} (want {want})")

    good = "endpoints:\n" + VALID_ROW.format(svc="svc-a")

    probe("a valid config passes", good, 0)
    probe("a MISSING file is misuse, not a pass", None, 2)
    probe("malformed YAML is misuse", "endpoints: [oops\n", 2)
    probe("an EMPTY endpoints list is misuse, not a clean run", "endpoints: []\n", 2)
    probe("a non-list endpoints is misuse", "endpoints: {}\n", 2)

    probe("a missing required field fails",
          "endpoints:\n  - id: r1\n    service: svc-a\n    method: GET\n    path: /v1/x\n"
          "    p95_ms: 250\n    window: 30d\n", 1)
    probe("a NEGATIVE p95_ms fails",
          good.replace("p95_ms: 250", "p95_ms: -1"), 1)
    # `True` is an int in Python; without the explicit bool guard `p95_ms: true`
    # would sail through as the number 1.
    probe("a BOOLEAN p95_ms fails (bool is an int in Python)",
          good.replace("p95_ms: 250", "p95_ms: true"), 1)
    probe("an unknown HTTP method fails",
          good.replace("method: GET", "method: FETCH"), 1)
    probe("a duplicate id fails",
          "endpoints:\n" + VALID_ROW.format(svc="svc-a")
          + VALID_ROW.format(svc="svc-a").replace("path: /v1/x", "path: /v1/y"), 1)
    probe("a duplicate (method, path) fails",
          "endpoints:\n" + VALID_ROW.format(svc="svc-a")
          + VALID_ROW.format(svc="svc-a").replace("id: r1", "id: r2"), 1)
    probe("a service with no services/<name>/ directory fails",
          good.replace("service: svc-a", "service: ghost-service"), 1)

    # THE SHRINK ARM. `LATENCY_HEAVY` is hand-kept; a name in it that is not a
    # real service exempts nothing while looking like coverage.
    probe("a LATENCY_HEAVY name with no service directory fails",
          good, 1, svc_dirs=("svc-a",))  # none of the 4 heavy names exist here
    probe("...and with those directories present, the same config is clean",
          good, 0)

    print(f"slo-latency-lint --self-test: {'every rule bites, and none cries wolf' if not failures else f'{failures} rule(s) did not behave'}")
    return 1 if failures else 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-test", "--selftest"):
        return self_test()
    cfg = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "contracts/slo/latency.yaml"
    rc = self_test()
    if rc:
        return rc
    return check(cfg)


if __name__ == "__main__":
    sys.exit(main())
