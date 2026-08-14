#!/usr/bin/env python3
"""`DFO-6` — keep `contracts/testing/live-suites.yaml` honest.

# The problem this gate has, stated before the rules

The registry is AUTHORED, because a live suite cannot be discovered from Rust
source: `epoch_activation_live` reads its DSNs through a helper, and
`spine_drain_once_live` reaches `env::var` with the name as a PARAMETER. A
discovery pass that misses a suite reports complete coverage of an incomplete
list, which is worse than no discovery at all.

So this gate never greps Rust for env vars. It checks the registry against two
things that cannot lie about themselves:

  * **`foundation-ci.yml`**, which is structured YAML. Every `cargo test -p X
    --test Y` leg in it must have a `ci: true` row naming the same databases,
    and every `ci: true` row must have a leg. Both directions, so neither a
    dropped leg nor an aspirational row survives.
  * **the filesystem**, for `tests/<target>.rs`. A row naming a target that
    does not exist is a phantom.

and one ratchet:

  * **`UNCOVERED_MAX`** — how many rows say `ci: false`. It may only SHRINK. A
    new live suite added tomorrow with no CI leg pushes the count up and reds
    here, which is the whole point: without it a new live suite is
    *default-uncovered* (`NV-3`) and nothing says so.

Exit 0 clean · 1 finding · 2 misuse (the gate could not do its job).
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "contracts" / "testing" / "live-suites.yaml"
WORKFLOW = REPO / ".github" / "workflows" / "foundation-ci.yml"

# The ratchet. Measured 2026-08-14: 21 live targets, CI provisions a database
# for 6. It may only go DOWN — lower it in the same commit that adds a leg.
UNCOVERED_MAX = 15

# A dev database name must announce itself as disposable. Same list the
# fixtures' own `guarded()` uses; these fixtures seed and truncate.
THROWAWAY_MARKERS = ("test", "smoke", "scratch", "throwaway", "sandbox")

CI_LEG = re.compile(
    r"cargo test\s+-p\s+(?P<pkg>[a-z0-9_-]+)"
    r"(?:\s+--features\s+(?P<feat>[a-z0-9_,-]+))?"
    r"\s+--test\s+(?P<target>[a-z0-9_]+)"
)


def load_yaml(path: Path):
    try:
        import yaml  # type: ignore
    except ImportError:
        print("live-suite-registry-gate: MISUSE — pyyaml is not installed", file=sys.stderr)
        sys.exit(2)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def ci_legs(text: str) -> dict[tuple[str, str], set[str]]:
    """`(package, target) -> the set of database names its step's env names`.

    A leg's databases are read from the `LOREWEAVE_*_URL:` lines in the same
    step, which sit ABOVE the `run:` in the workflow — so the scan walks
    backwards from each match to the step boundary rather than forwards.
    """
    lines = text.splitlines()
    legs: dict[tuple[str, str], set[str]] = {}
    for i, line in enumerate(lines):
        m = CI_LEG.search(line)
        if not m:
            continue
        dbs: set[str] = set()
        for j in range(i, max(-1, i - 12), -1):
            if j != i and re.match(r"\s*- name:", lines[j]):
                break
            for dsn in re.findall(r"postgres://[^/\s]+/([A-Za-z0-9_]+)", lines[j]):
                dbs.add(dsn)
        legs[(m.group("pkg"), m.group("target"))] = dbs
    return legs


SKIP_ANNOUNCE = re.compile(r'(eprintln!|println!)\s*\(\s*"?\s*(SKIP|\[skip\])', re.IGNORECASE)


def announces_skip(target_file: Path) -> bool:
    """Does this suite SAY when it does nothing?

    Reads the target and its helper MODULES — `epoch_activation_live` skips
    through `epoch_live_common::dsns()`, so the announcement is not in the
    target's own bytes.

    Helper modules only: `tests/<dir>/**.rs`, never the sibling `tests/*.rs`.
    The first version globbed the whole `tests/` directory, so ONE suite's
    `[skip]` vouched for every other target in the same crate — the check
    passed for a file that says nothing. Its own self-test arm caught it, which
    is the argument for writing the arm.
    """
    text = target_file.read_text(encoding="utf-8", errors="replace")
    for helper_dir in (p for p in target_file.parent.iterdir() if p.is_dir()):
        for sib in helper_dir.rglob("*.rs"):
            text += sib.read_text(encoding="utf-8", errors="replace")
    return bool(SKIP_ANNOUNCE.search(text))


def package_dir(pkg: str) -> Path | None:
    for base in ("crates", "services"):
        p = REPO / base / pkg
        if (p / "Cargo.toml").is_file():
            return p
    return None


def check(reg: dict, workflow_text: str) -> list[str]:
    findings: list[str] = []
    suites = reg.get("suites") or []
    if not suites:
        print("live-suite-registry-gate: MISUSE — the registry lists no suites", file=sys.stderr)
        sys.exit(2)

    legs = ci_legs(workflow_text)
    if not legs:
        print(
            "live-suite-registry-gate: MISUSE — no `cargo test -p X --test Y` leg found in the\n"
            "  workflow. Either it was restructured or the pattern stopped matching; either way a\n"
            "  clean result here would mean nothing.",
            file=sys.stderr,
        )
        sys.exit(2)

    seen_ids: set[str] = set()
    uncovered = 0
    claimed: set[tuple[str, str]] = set()

    for s in suites:
        sid = s.get("id", "<no id>")
        if sid in seen_ids:
            findings.append(f"duplicate id `{sid}`")
        seen_ids.add(sid)

        pkg, target = s.get("package"), s.get("target")
        pdir = package_dir(pkg or "")
        if pdir is None:
            findings.append(f"`{sid}`: no crate or service named `{pkg}`")
        elif not (pdir / "tests" / f"{target}.rs").is_file():
            findings.append(
                f"`{sid}`: names target `{target}` but "
                f"{pdir.relative_to(REPO)}/tests/{target}.rs does not exist — a phantom row"
            )
        elif not announces_skip(pdir / "tests" / f"{target}.rs"):
            # A live suite that skips SILENTLY is indistinguishable from one
            # that ran: both exit 0 and print `test result: ok`. The runner
            # reports SKIPPED as not-a-pass, and it can only do that if the
            # suite says so. This is checking a KNOWN list, not discovering one
            # — the registry names the file, so no grep is deciding scope.
            findings.append(
                f"`{sid}`: {target}.rs never announces a skip. Print `SKIP …` (or `[skip] …`) "
                f"on the no-DSN path, or a run where it did nothing is reported as a pass."
            )

        needs = s.get("needs") or []
        if not needs:
            findings.append(f"`{sid}`: declares no backing store, so it is not a live suite")
        for n in needs:
            if n.get("kind") in ("postgres", "postgres-admin") and n.get("schema") is None:
                findings.append(f"`{sid}`: `{n.get('env')}` has no `schema`")

        if s.get("ci"):
            claimed.add((pkg, target))
            if (pkg, target) not in legs:
                findings.append(
                    f"`{sid}`: claims `ci: true` but foundation-ci.yml has no "
                    f"`cargo test -p {pkg} --test {target}` leg"
                )
            else:
                want = {n["ci_db"] for n in needs if "ci_db" in n}
                got = legs[(pkg, target)]
                if want != got:
                    findings.append(
                        f"`{sid}`: CI databases disagree — registry says {sorted(want) or '[]'}, "
                        f"the workflow step names {sorted(got) or '[]'}"
                    )
        else:
            uncovered += 1
            if not (s.get("ci_absent_reason") or "").strip():
                findings.append(
                    f"`{sid}`: `ci: false` with no `ci_absent_reason`. "
                    f'"nobody got to it" is an honest reason; blank is not.'
                )

    for pkg, target in sorted(legs):
        if (pkg, target) not in claimed:
            findings.append(
                f"foundation-ci.yml runs `-p {pkg} --test {target}` and the registry has no "
                f"`ci: true` row for it — CI drifted ahead of the registry"
            )

    if uncovered > UNCOVERED_MAX:
        findings.append(
            f"{uncovered} suite(s) have no CI leg, and the ratchet is {UNCOVERED_MAX}. "
            f"A new live suite with no CI leg is default-uncovered: it is green in "
            f"`cargo test --workspace` because it SKIPPED. Add a leg, or raise this "
            f"deliberately with the reason in the commit."
        )
    if uncovered < UNCOVERED_MAX:
        findings.append(
            f"only {uncovered} suite(s) are uncovered but the ratchet still says "
            f"{UNCOVERED_MAX} — lower it. A ratchet that does not tighten stops meaning anything."
        )
    return findings


def selftest() -> int:
    """Each rule, bitten. A gate is not trusted about the tree until it is."""
    import yaml  # already proven importable by load_yaml's caller path

    ok_wf = """
      - name: run it
        env:
          LOREWEAVE_TEST_PG_URL: postgres://u:p@localhost:5432/real_smoke
        run: cargo test -p dp-kernel --test integration_event_store
"""

    def reg(**over):
        base = {
            "version": 1,
            "suites": [
                {
                    "id": "covered",
                    "package": "dp-kernel",
                    "target": "integration_event_store",
                    "ci": True,
                    "needs": [{"env": "X", "kind": "postgres", "schema": "self",
                               "ci_db": "real_smoke"}],
                },
                {
                    "id": "uncovered",
                    "package": "dp-kernel",
                    "target": "integration_writer_lease",
                    "ci": False,
                    "ci_absent_reason": "no leg",
                    "needs": [{"env": "Y", "kind": "postgres", "schema": "per_reality"}],
                },
            ],
        }
        base.update(over)
        return base

    global UNCOVERED_MAX
    saved = UNCOVERED_MAX
    UNCOVERED_MAX = 1
    cases: list[tuple[str, dict, str, int]] = []

    cases.append(("a matching registry passes", reg(), ok_wf, 0))

    r = reg()
    r["suites"][0]["needs"][0]["ci_db"] = "wrong_smoke"
    cases.append(("a CI database name that disagrees fails", r, ok_wf, 1))

    r = reg()
    r["suites"][0]["target"] = "no_such_target"
    cases.append(("a target with no file on disk fails", r, ok_wf, 1))

    r = reg()
    r["suites"][0]["package"] = "not-a-crate"
    cases.append(("a package that does not exist fails", r, ok_wf, 1))

    r = reg()
    r["suites"][1]["ci_absent_reason"] = "   "
    cases.append(("`ci: false` with a blank reason fails", r, ok_wf, 1))

    r = reg()
    r["suites"][0]["ci"] = False
    r["suites"][0]["ci_absent_reason"] = "pretend"
    cases.append(("a leg CI runs with no `ci: true` row fails", r, ok_wf, 1))

    r = reg()
    r["suites"].append(dict(r["suites"][1], id="uncovered-2",
                            target="integration_channel_writer"))
    cases.append(("one MORE uncovered suite than the ratchet fails", r, ok_wf, 1))

    r = reg()
    r["suites"] = [r["suites"][0]]
    cases.append(("FEWER uncovered than the ratchet also fails — it must tighten", r, ok_wf, 1))

    r = reg()
    r["suites"][1]["needs"] = []
    cases.append(("a row with no backing store fails", r, ok_wf, 1))

    # A REAL target that genuinely never prints a skip line. Not a fabricated
    # file: `bulkhead_shuttle` is an ordinary dp-kernel integration test with no
    # DSN gate, so it is exactly the shape this arm must catch if someone
    # registers a live suite that skips in silence.
    r = reg()
    r["suites"][1]["target"] = "bulkhead_shuttle"
    cases.append(("a target that never announces a skip fails", r, ok_wf, 1))

    r = reg()
    r["suites"].append(dict(r["suites"][1]))
    cases.append(("a duplicate id fails", r, ok_wf, 1))

    bad = 0
    for name, registry, wf, want in cases:
        got = len(check(registry, wf))
        got = 1 if got else 0
        mark = "ok  " if got == want else "FAIL"
        if got != want:
            bad = 1
        print(f"  {mark} {name}: findings={got} (want {want})")

    # MISUSE, both shapes — a gate that cannot see its subject must say so.
    for name, registry, wf in (
        ("an empty registry is misuse, not a pass", {"suites": []}, ok_wf),
        ("a workflow with no cargo leg is misuse", reg(), "jobs:\n  build:\n    steps: []\n"),
    ):
        try:
            check(registry, wf)
        except SystemExit as e:
            print(f"  {'ok  ' if e.code == 2 else 'FAIL'} {name}: rc={e.code} (want 2)")
            if e.code != 2:
                bad = 1
        else:
            print(f"  FAIL {name}: it returned instead of refusing")
            bad = 1

    UNCOVERED_MAX = saved
    if bad:
        print("live-suite-registry-gate --self-test: FAIL")
        return 2
    print("live-suite-registry-gate --self-test: every rule bites, and none cries wolf")
    return 0


def main() -> int:
    if not REGISTRY.is_file():
        print(f"live-suite-registry-gate: MISUSE — no registry at {REGISTRY}", file=sys.stderr)
        return 2
    if not WORKFLOW.is_file():
        print(f"live-suite-registry-gate: MISUSE — no workflow at {WORKFLOW}", file=sys.stderr)
        return 2

    rc = selftest()
    if rc:
        return rc
    if "--self-test" in sys.argv:
        return 0

    reg = load_yaml(REGISTRY)
    findings = check(reg, WORKFLOW.read_text(encoding="utf-8"))

    # The throwaway-marker rule is about the RUNNER's derived names, so it is
    # checked here against the id rather than against a field nobody sets.
    for s in reg.get("suites") or []:
        dev_db = f"ls_{str(s.get('id', '')).replace('-', '_')}_smoke"
        if not any(m in dev_db for m in THROWAWAY_MARKERS):
            findings.append(f"`{s.get('id')}`: derived dev database `{dev_db}` carries no marker")

    if findings:
        print(f"live-suite-registry-gate: {len(findings)} finding(s)\n")
        for f in findings:
            print(f"  {f}")
        print(
            "\nThe registry is the only complete list of live suites — a grep cannot build it.\n"
            "If it drifts from CI, the thing that says which suites actually run is wrong."
        )
        return 1

    total = len(reg["suites"])
    covered = sum(1 for s in reg["suites"] if s.get("ci"))
    print(
        f"live-suite-registry-gate: OK — {total} live suite(s); {covered} have a CI leg whose "
        f"databases match, {total - covered} do not and each says why (ratchet {UNCOVERED_MAX})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
